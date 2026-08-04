import unittest
from collections import Counter
from datetime import date

from scheduler import generate_schedule


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


if __name__ == '__main__':
    unittest.main()
