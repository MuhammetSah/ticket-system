import unittest
from collections import Counter
from datetime import date

from baselines import greedy_first_fit
from scheduler import (
    AUTO,
    CHRONOLOGICAL,
    MOST_CONSTRAINED,
    generate_schedule,
    ideal_sum_squares,
)


def employee(id, max_shifts_per_month=None, unavailable_weekdays=None, unavailable_dates=None, allowed_shift_types=None):
    return {
        'id': id,
        'max_shifts_per_month': max_shifts_per_month,
        'unavailable_weekdays': set(unavailable_weekdays or []),
        'unavailable_dates': set(unavailable_dates or []),
        'allowed_shift_types': set(allowed_shift_types) if allowed_shift_types else None,
    }


def shift_type(id, required_every_day=1):
    return {'id': id, 'requirements': {wd: required_every_day for wd in range(7)}}


class BacktrackingBeatsGreedy(unittest.TestCase):
    def test_reconsiders_earlier_choice_to_avoid_a_gap(self):
        # 2026-08-03 is a Monday. Shift type 1 can be worked by X or Y; shift
        # type 2 can only be worked by X. A greedy pass that commits to the
        # first workable candidate for shift 1 (X, lowest id) would strand
        # shift 2 with no one left that day. Real backtracking should instead
        # discover "Y takes shift 1, X takes shift 2" and leave nothing unfilled.
        employees = [
            employee(id=1, allowed_shift_types=None),                    # X: can work anything
            employee(id=2, allowed_shift_types=[10]),                    # Y: only shift type 10
        ]
        shift_types = [
            {'id': 10, 'requirements': {0: 1}},  # Monday only, 1 slot - X or Y eligible
            {'id': 20, 'requirements': {0: 1}},  # Monday only, 1 slot - only X eligible
        ]

        result = generate_schedule(2026, 8, employees, shift_types)

        self.assertEqual(result['unfilled_count'], 0, 'backtracking should find the zero-gap solution')
        self.assertTrue(result['complete'])

        by_shift = {a['shift_type_id']: a['employee_id'] for a in result['assignments']}
        self.assertEqual(by_shift[20], 1, 'only X (id 1) is eligible for shift type 20')
        self.assertEqual(by_shift[10], 2, 'Y must take shift type 10 so X is free for shift type 20')

        # A literal greedy baseline (first eligible candidate, never reconsidered,
        # availability reset each day) would leave one gap per Monday - confirm
        # that's actually the inferior result this test guards against, so the
        # comparison isn't just asserted by name.
        by_date = {}
        for a in result['assignments']:
            by_date.setdefault(a['date'], []).append(a)

        greedy_unfilled = 0
        for day_assignments in by_date.values():
            used_today = set()
            for slot in sorted(day_assignments, key=lambda a: a['shift_type_id']):
                candidates = [
                    e for e in employees
                    if e['id'] not in used_today
                    and (e['allowed_shift_types'] is None or slot['shift_type_id'] in e['allowed_shift_types'])
                ]
                if candidates:
                    used_today.add(candidates[0]['id'])
                else:
                    greedy_unfilled += 1
        self.assertEqual(greedy_unfilled, len(by_date), 'sanity check: greedy-first-fit leaves one gap per Monday')


class HardConstraints(unittest.TestCase):
    def test_unavailable_weekday_is_never_assigned(self):
        wednesday = 2
        employees = [employee(id=1, unavailable_weekdays=[wednesday])]
        shift_types = [shift_type(id=1, required_every_day=1)]

        result = generate_schedule(2026, 8, employees, shift_types)

        for a in result['assignments']:
            d = date.fromisoformat(a['date'])
            if d.weekday() == wednesday:
                self.assertIsNone(a['employee_id'], f'{a["date"]} is a Wednesday and should be unfilled')
            else:
                self.assertEqual(a['employee_id'], 1)

    def test_unavailable_date_is_never_assigned(self):
        employees = [employee(id=1, unavailable_dates=['2026-08-10'])]
        shift_types = [shift_type(id=1, required_every_day=1)]

        result = generate_schedule(2026, 8, employees, shift_types)

        by_date = {a['date']: a['employee_id'] for a in result['assignments']}
        self.assertIsNone(by_date['2026-08-10'])

    def test_allowed_shift_types_restriction_is_respected(self):
        # Employee 1 may only work shift type 1 ("nur Frühschicht").
        employees = [
            employee(id=1, allowed_shift_types=[1]),
            employee(id=2),
        ]
        shift_types = [shift_type(id=1, required_every_day=1), shift_type(id=2, required_every_day=1)]

        result = generate_schedule(2026, 8, employees, shift_types)

        for a in result['assignments']:
            if a['shift_type_id'] == 2:
                self.assertNotEqual(a['employee_id'], 1, 'employee 1 is restricted to shift type 1')

    def test_no_employee_double_booked_same_day(self):
        employees = [employee(id=1), employee(id=2)]
        shift_types = [shift_type(id=1, required_every_day=1), shift_type(id=2, required_every_day=1)]

        result = generate_schedule(2026, 8, employees, shift_types)

        by_date = {}
        for a in result['assignments']:
            by_date.setdefault(a['date'], []).append(a['employee_id'])
        for d, emp_ids in by_date.items():
            assigned = [e for e in emp_ids if e is not None]
            self.assertEqual(len(assigned), len(set(assigned)), f'{d} double-books an employee')

    def test_max_shifts_per_month_cap_is_respected(self):
        employees = [employee(id=1, max_shifts_per_month=2), employee(id=2)]
        shift_types = [shift_type(id=1, required_every_day=1)]

        result = generate_schedule(2026, 8, employees, shift_types)

        counts = Counter(a['employee_id'] for a in result['assignments'] if a['employee_id'] is not None)
        self.assertLessEqual(counts[1], 2)


class GracefulUnderStaffing(unittest.TestCase):
    def test_no_employees_reports_gaps_without_crashing(self):
        result = generate_schedule(2026, 8, [], [shift_type(id=1, required_every_day=1)])

        self.assertFalse(result['complete'])
        self.assertEqual(result['unfilled_count'], result['total_slots'])
        self.assertTrue(all(a['employee_id'] is None for a in result['assignments']))

    def test_impossible_requirement_minimizes_gaps_rather_than_leaving_everyone_unfilled(self):
        # Only 1 employee available but 2 people required per day - each day
        # must end up with exactly 1 gap, not 2, and the rest of the month
        # should still be handled.
        employees = [employee(id=1)]
        shift_types = [shift_type(id=1, required_every_day=2)]

        result = generate_schedule(2026, 8, employees, shift_types)

        self.assertEqual(result['unfilled_count'], result['total_slots'] // 2)


class Fairness(unittest.TestCase):
    """v1.3: spread the workload evenly once every shift that can be staffed is."""

    def test_workload_is_balanced_where_a_naive_pass_piles_it_on_one_person(self):
        employees = [employee(id=i) for i in range(1, 6)]
        shift_types = [shift_type(id=1, required_every_day=1)]

        naive = greedy_first_fit(2026, 8, employees, shift_types)
        planned = generate_schedule(2026, 8, employees, shift_types)

        # First-fit always grabs the same (lowest-id) person, so one employee
        # works the whole month while the rest work nothing.
        self.assertEqual(naive['fairness']['spread'], 31)
        # 31 days over 5 people cannot come out better than 7/6/6/6/6.
        self.assertEqual(planned['fairness']['spread'], 1)
        self.assertEqual(sorted(planned['fairness']['loads'].values()), [6, 6, 6, 6, 7])

    def test_balanced_plan_is_reported_as_proven_optimal(self):
        employees = [employee(id=i) for i in range(1, 5)]
        shift_types = [shift_type(id=1, required_every_day=2)]

        result = generate_schedule(2026, 8, employees, shift_types)

        self.assertEqual(result['unfilled_count'], 0)
        self.assertTrue(result['proven_optimal'])
        self.assertEqual(result['fairness']['sum_squares'],
                         ideal_sum_squares(result['total_slots'], len(employees)))

    def test_fairness_never_costs_a_staffed_shift(self):
        # Employee 2 can only work shift type 2, so a perfectly even split is
        # impossible - filling every shift must still win over balancing them.
        employees = [employee(id=1), employee(id=2, allowed_shift_types=[2])]
        shift_types = [shift_type(id=1, required_every_day=1), shift_type(id=2, required_every_day=1)]

        result = generate_schedule(2026, 8, employees, shift_types)

        self.assertEqual(result['unfilled_count'], 0)

    def test_weekend_weight_evens_out_weekend_duty(self):
        employees = [employee(id=i) for i in range(1, 5)]
        # Weekends need fewer people than weekdays, so weekend duty is the scarce
        # thing that can quietly land on the same few people every month.
        shift_types = [{'id': 1, 'requirements': {wd: (3 if wd < 5 else 1) for wd in range(7)}}]

        without = generate_schedule(2026, 8, employees, shift_types, weekend_weight=0)
        with_weight = generate_schedule(2026, 8, employees, shift_types, weekend_weight=5)

        self.assertLessEqual(with_weight['fairness']['weekend_spread'],
                             without['fairness']['weekend_spread'])
        # Weekend equity must not come at the price of leaving shifts unstaffed.
        self.assertEqual(with_weight['unfilled_count'], 0)


class SlotOrdering(unittest.TestCase):
    """v1.2: the order slots are filled in, and the adaptive choice between them."""

    UNDERSTAFFED_EMPLOYEES = [
        employee(id=1, allowed_shift_types=[1]),
        employee(id=2, allowed_shift_types=[1], unavailable_weekdays=[5, 6]),
        employee(id=3, allowed_shift_types=[2]),
        employee(id=4, max_shifts_per_month=6),
        employee(id=5, unavailable_weekdays=[0, 1, 2]),
    ]
    UNDERSTAFFED_SHIFTS = [shift_type(id=1, required_every_day=2), shift_type(id=2, required_every_day=2)]

    def test_most_constrained_first_leaves_fewer_gaps_when_staff_are_short(self):
        chronological = generate_schedule(
            2026, 8, self.UNDERSTAFFED_EMPLOYEES, self.UNDERSTAFFED_SHIFTS, ordering=CHRONOLOGICAL)
        constrained = generate_schedule(
            2026, 8, self.UNDERSTAFFED_EMPLOYEES, self.UNDERSTAFFED_SHIFTS, ordering=MOST_CONSTRAINED)

        self.assertLess(constrained['unfilled_count'], chronological['unfilled_count'])

    def test_auto_falls_back_to_the_harder_search_when_gaps_appear(self):
        auto = generate_schedule(
            2026, 8, self.UNDERSTAFFED_EMPLOYEES, self.UNDERSTAFFED_SHIFTS, ordering=AUTO)
        constrained = generate_schedule(
            2026, 8, self.UNDERSTAFFED_EMPLOYEES, self.UNDERSTAFFED_SHIFTS, ordering=MOST_CONSTRAINED)

        self.assertEqual(auto['unfilled_count'], constrained['unfilled_count'])

    def test_auto_keeps_the_balanced_chronological_plan_when_nothing_is_short(self):
        # A comfortably staffed month: the cheap first pass fills everything, so
        # AUTO must not fall back to the ordering that scrambles the balance.
        employees = [employee(id=i) for i in range(1, 7)]
        shift_types = [shift_type(id=1, required_every_day=2)]

        auto = generate_schedule(2026, 8, employees, shift_types, ordering=AUTO)

        self.assertEqual(auto['unfilled_count'], 0)
        self.assertEqual(auto['ordering_used'], CHRONOLOGICAL)
        self.assertEqual(auto['fairness']['spread'], 1)

    def test_orderings_agree_on_a_comfortably_staffed_month(self):
        employees = [employee(id=i) for i in range(1, 7)]
        shift_types = [shift_type(id=1, required_every_day=2)]

        for ordering in (CHRONOLOGICAL, MOST_CONSTRAINED, AUTO):
            result = generate_schedule(2026, 8, employees, shift_types, ordering=ordering)
            self.assertEqual(result['unfilled_count'], 0, f'{ordering} left gaps')


if __name__ == '__main__':
    unittest.main()
