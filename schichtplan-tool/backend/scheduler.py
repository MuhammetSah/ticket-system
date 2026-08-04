import calendar
import time
from datetime import date

# Safety valves so a pathological/understaffed month can't hang the request forever.
NODE_BUDGET = 300_000
TIME_BUDGET_SECONDS = 8.0


class _BudgetExceeded(Exception):
    pass


def generate_schedule(year, month, employees, shift_types):
    """Assign employees to shifts for one month via chronological backtracking.

    employees: [{id, max_shifts_per_month, unavailable_weekdays: set[int],
                 unavailable_dates: set[str ISO date], allowed_shift_types: set[int] or None}]
    shift_types: [{id, requirements: {weekday(0-6): required_count}}]

    This is deliberately *not* greedy: a greedy pass assigns the first workable
    candidate to each slot and never reconsiders. Here, whenever a choice earlier
    in the month turns out to make a later slot unfillable, the search undoes
    (backtracks) that choice and tries another - see `_backtrack` below. Search is
    branch-and-bound: it keeps exploring after finding a complete assignment, in
    case a different set of choices leaves fewer slots unfilled, and prunes any
    branch that already can't beat the best found so far.

    Slots are processed in calendar order (v1). Ordering slots by how constrained
    they are ("most constrained first") is planned for v1.2; balancing load fairly
    across employees beyond the simple tie-break below is planned for v1.3.
    """
    days_in_month = calendar.monthrange(year, month)[1]
    dates = [date(year, month, d) for d in range(1, days_in_month + 1)]

    slots = []
    for d in dates:
        weekday = d.weekday()
        for shift_type in shift_types:
            required_count = shift_type['requirements'].get(weekday, 0)
            for slot_index in range(required_count):
                slots.append({
                    'date': d.isoformat(),
                    'weekday': weekday,
                    'shift_type_id': shift_type['id'],
                    'slot_index': slot_index,
                })

    total_slots = len(slots)
    assignment = [None] * total_slots
    day_usage = {}
    load = {emp['id']: 0 for emp in employees}

    best = {'assignment': None, 'unfilled': total_slots + 1}
    state = {'nodes': 0, 'start': time.monotonic()}

    def eligible_candidates(slot):
        used_today = day_usage.get(slot['date'], set())
        candidates = []
        for emp in employees:
            eid = emp['id']
            if eid in used_today:
                continue
            if slot['weekday'] in emp['unavailable_weekdays']:
                continue
            if slot['date'] in emp['unavailable_dates']:
                continue
            allowed = emp['allowed_shift_types']
            if allowed and slot['shift_type_id'] not in allowed:
                continue
            cap = emp['max_shifts_per_month']
            if cap is not None and load[eid] >= cap:
                continue
            candidates.append(emp)
        # Tie-break toward whoever has fewer shifts so far this search branch, just to
        # avoid obviously lopsided results by default - real fairness balancing is v1.3.
        candidates.sort(key=lambda e: (load[e['id']], e['id']))
        return candidates

    def check_budget():
        state['nodes'] += 1
        if state['nodes'] > NODE_BUDGET:
            raise _BudgetExceeded()
        if state['nodes'] % 2000 == 0 and time.monotonic() - state['start'] > TIME_BUDGET_SECONDS:
            raise _BudgetExceeded()

    def backtrack(i, unfilled_so_far):
        check_budget()

        if best['unfilled'] == 0:
            return
        if unfilled_so_far >= best['unfilled']:
            return  # can't possibly beat the best solution found so far - prune

        if i == total_slots:
            best['unfilled'] = unfilled_so_far
            best['assignment'] = assignment.copy()
            return

        slot = slots[i]
        d = slot['date']

        for emp in eligible_candidates(slot):
            eid = emp['id']
            assignment[i] = eid
            day_usage.setdefault(d, set()).add(eid)
            load[eid] += 1

            backtrack(i + 1, unfilled_so_far)

            day_usage[d].discard(eid)
            load[eid] -= 1
            assignment[i] = None

            if best['unfilled'] == 0:
                return

        # Last resort: leave this slot unfilled and keep going, in case the rest
        # of the month can still be completed (or at least minimized).
        assignment[i] = None
        backtrack(i + 1, unfilled_so_far + 1)

    budget_exceeded = False
    try:
        backtrack(0, 0)
    except _BudgetExceeded:
        budget_exceeded = True

    if best['assignment'] is not None:
        result_assignment = best['assignment']
        unfilled_count = best['unfilled']
    else:
        # Budget ran out before a single complete assignment was found; fall back
        # to whatever the search had committed to at that point.
        result_assignment = [assignment[i] if i < len(assignment) else None for i in range(total_slots)]
        unfilled_count = sum(1 for v in result_assignment if v is None)

    assignments = [
        {
            'date': slot['date'],
            'shift_type_id': slot['shift_type_id'],
            'slot_index': slot['slot_index'],
            'employee_id': emp_id,
        }
        for slot, emp_id in zip(slots, result_assignment)
    ]

    return {
        'assignments': assignments,
        'total_slots': total_slots,
        'unfilled_count': unfilled_count,
        'complete': unfilled_count == 0,
        'budget_exceeded': budget_exceeded,
    }
