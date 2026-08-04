import calendar
import time
from datetime import date

# Safety valves so a pathological/understaffed month can't hang the request forever.
DEFAULT_NODE_BUDGET = 300_000
DEFAULT_TIME_BUDGET_SECONDS = 8.0

# Slot ordering strategies.
CHRONOLOGICAL = 'chronological'          # v1: plan the month day by day
MOST_CONSTRAINED = 'most_constrained'    # v1.2: hardest-to-staff slots first
AUTO = 'auto'                            # v1.3: chronological, retried harder only if shifts go unfilled


class _BudgetExceeded(Exception):
    pass


def build_slots(year, month, shift_types):
    """Expand shift requirements into one entry per person-shift that must be staffed."""
    days_in_month = calendar.monthrange(year, month)[1]
    slots = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        weekday = d.weekday()
        for shift_type in shift_types:
            required_count = shift_type['requirements'].get(weekday, 0)
            for slot_index in range(required_count):
                slots.append({
                    'date': d.isoformat(),
                    'weekday': weekday,
                    'shift_type_id': shift_type['id'],
                    'slot_index': slot_index,
                    'is_weekend': weekday >= 5,
                })
    return slots


def structurally_eligible(employee, slot):
    """Constraints that depend only on the employee and the slot, not on other assignments."""
    if slot['weekday'] in employee['unavailable_weekdays']:
        return False
    if slot['date'] in employee['unavailable_dates']:
        return False
    allowed = employee['allowed_shift_types']
    if allowed and slot['shift_type_id'] not in allowed:
        return False
    return True


def order_slots(slots, employees, ordering):
    """v1.2: decide the order the search fills slots in.

    Filling the hardest slots first ("most constrained first", the classic CSP
    minimum-remaining-values heuristic) means a dead end is hit near the top of
    the search tree, where backtracking is cheap, instead of after committing to
    hundreds of assignments. Chronological order is kept so the two can be
    compared - see benchmark.py.
    """
    if ordering == CHRONOLOGICAL:
        return list(slots)
    if ordering != MOST_CONSTRAINED:
        raise ValueError(f'unknown ordering: {ordering}')

    def sort_key(slot):
        eligible_count = sum(1 for e in employees if structurally_eligible(e, slot))
        # Date/shift tie-breakers only exist to keep the ordering deterministic.
        return (eligible_count, slot['date'], slot['shift_type_id'], slot['slot_index'])

    return sorted(slots, key=sort_key)


def ideal_sum_squares(total, count):
    """Lowest achievable sum of squared loads: spread `total` shifts over `count` people."""
    if count == 0:
        return 0
    base, remainder = divmod(total, count)
    return remainder * (base + 1) ** 2 + (count - remainder) * base ** 2


def fairness_stats(assignments, employees):
    loads = {e['id']: 0 for e in employees}
    weekend_loads = {e['id']: 0 for e in employees}
    for a in assignments:
        if a['employee_id'] is None:
            continue
        loads[a['employee_id']] = loads.get(a['employee_id'], 0) + 1
        if a.get('is_weekend'):
            weekend_loads[a['employee_id']] = weekend_loads.get(a['employee_id'], 0) + 1

    values = list(loads.values())
    if not values:
        return {'loads': {}, 'weekend_loads': {}, 'spread': 0, 'sum_squares': 0, 'weekend_spread': 0}

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    weekend_values = list(weekend_loads.values())

    return {
        'loads': loads,
        'weekend_loads': weekend_loads,
        'spread': max(values) - min(values),
        'weekend_spread': max(weekend_values) - min(weekend_values),
        'sum_squares': sum(v * v for v in values),
        'stdev': round(variance ** 0.5, 3),
        'min': min(values),
        'max': max(values),
    }


def _search(
    year,
    month,
    employees,
    shift_types,
    ordering,
    fairness,
    weekend_weight,
    node_budget,
    time_budget_seconds,
):
    """Run one backtracking search with a fixed slot ordering.

    This is deliberately *not* greedy: a greedy pass assigns the first workable
    candidate to each slot and never reconsiders. Here, whenever a choice earlier
    in the search makes a later slot unfillable, the search undoes (backtracks)
    that choice and tries another - see `backtrack` below.

    Search is branch-and-bound over a lexicographic objective:
      1. minimise unfilled slots (never trade a staffed shift for a fairer plan)
      2. minimise the sum of squared shift counts per employee (v1.3 fairness)

    Minimising the sum of squares is equivalent to minimising the variance of the
    workload once the number of assigned shifts is fixed, and it updates in O(1)
    per assignment: giving a shift to someone who already has L raises it by 2L+1,
    so each additional shift for an already-busy person is penalised more than a
    first shift for an idle one. Both objective components only ever grow as the
    search goes deeper, so a branch whose partial cost already loses to the best
    complete plan can be pruned safely.
    """
    raw_slots = build_slots(year, month, shift_types)
    slots = order_slots(raw_slots, employees, ordering)

    total_slots = len(slots)
    assignment = [None] * total_slots
    day_usage = {}
    load = {emp['id']: 0 for emp in employees}
    weekend_load = {emp['id']: 0 for emp in employees}

    # Cost is compared lexicographically as (unfilled, fairness_cost).
    best = {'assignment': None, 'unfilled': total_slots + 1, 'cost': 0}
    state = {'nodes': 0, 'start': time.monotonic(), 'exhausted': True}

    ideal_cost = ideal_sum_squares(total_slots, len(employees)) if employees else 0

    def check_budget():
        state['nodes'] += 1
        if state['nodes'] > node_budget:
            raise _BudgetExceeded()
        if state['nodes'] % 2000 == 0 and time.monotonic() - state['start'] > time_budget_seconds:
            raise _BudgetExceeded()

    def eligible_candidates(slot):
        used_today = day_usage.get(slot['date'], ())
        candidates = []
        for emp in employees:
            eid = emp['id']
            if eid in used_today:
                continue
            if not structurally_eligible(emp, slot):
                continue
            cap = emp['max_shifts_per_month']
            if cap is not None and load[eid] >= cap:
                continue
            candidates.append(emp)

        # Try the least-loaded people first. With the fairness objective this
        # makes the very first complete plan the search finds already close to
        # balanced, which in turn prunes most of the remaining search tree.
        if weekend_weight and slot['is_weekend']:
            candidates.sort(key=lambda e: (weekend_load[e['id']], load[e['id']], e['id']))
        else:
            candidates.sort(key=lambda e: (load[e['id']], e['id']))
        return candidates

    def is_worse_or_equal(unfilled, cost):
        if unfilled != best['unfilled']:
            return unfilled > best['unfilled']
        return cost >= best['cost']

    def backtrack(i, unfilled_so_far, cost_so_far):
        check_budget()

        # Both objective components only grow deeper in the tree, so a partial
        # plan that already ties or loses can never win.
        if best['assignment'] is not None and is_worse_or_equal(unfilled_so_far, cost_so_far):
            return

        if i == total_slots:
            best['unfilled'] = unfilled_so_far
            best['cost'] = cost_so_far
            best['assignment'] = assignment.copy()
            return

        slot = slots[i]
        d = slot['date']

        for emp in eligible_candidates(slot):
            eid = emp['id']
            added = 0
            if fairness:
                added = 2 * load[eid] + 1
                if weekend_weight and slot['is_weekend']:
                    added += weekend_weight * (2 * weekend_load[eid] + 1)

            assignment[i] = eid
            day_usage.setdefault(d, set()).add(eid)
            load[eid] += 1
            if slot['is_weekend']:
                weekend_load[eid] += 1

            backtrack(i + 1, unfilled_so_far, cost_so_far + added)

            day_usage[d].discard(eid)
            load[eid] -= 1
            if slot['is_weekend']:
                weekend_load[eid] -= 1
            assignment[i] = None

            # A perfectly even, fully staffed plan cannot be beaten - stop early.
            if best['assignment'] is not None and best['unfilled'] == 0:
                if not fairness or best['cost'] <= ideal_cost:
                    return

        # Last resort: leave this slot unfilled and carry on, in case the rest of
        # the month can still be completed (or at least have fewer gaps).
        assignment[i] = None
        backtrack(i + 1, unfilled_so_far + 1, cost_so_far)

    budget_exceeded = False
    try:
        backtrack(0, 0, 0)
    except _BudgetExceeded:
        budget_exceeded = True
        state['exhausted'] = False

    if best['assignment'] is not None:
        result_assignment = best['assignment']
        unfilled_count = best['unfilled']
    else:
        # Budget ran out before a single complete plan was found; fall back to
        # whatever the search had committed to at that point.
        result_assignment = list(assignment)
        unfilled_count = sum(1 for v in result_assignment if v is None)

    assignments = [
        {
            'date': slot['date'],
            'shift_type_id': slot['shift_type_id'],
            'slot_index': slot['slot_index'],
            'employee_id': emp_id,
            'is_weekend': slot['is_weekend'],
        }
        for slot, emp_id in zip(slots, result_assignment)
    ]
    # Emit in calendar order regardless of the order the search used internally.
    assignments.sort(key=lambda a: (a['date'], a['shift_type_id'], a['slot_index']))

    hit_ideal = fairness and unfilled_count == 0 and best['cost'] <= ideal_cost

    return {
        'assignments': assignments,
        'total_slots': total_slots,
        'unfilled_count': unfilled_count,
        'cost': best['cost'] if best['assignment'] is not None else float('inf'),
        'complete': unfilled_count == 0,
        'budget_exceeded': budget_exceeded,
        # True only with respect to the objective this run was configured with:
        # with fairness off, "optimal" means no avoidable gaps and says nothing
        # about how evenly the work is spread.
        'proven_optimal': state['exhausted'] or hit_ideal,
        'nodes_explored': state['nodes'],
        'ordering_used': ordering,
    }


def generate_schedule(
    year,
    month,
    employees,
    shift_types,
    ordering=AUTO,
    fairness=True,
    weekend_weight=0,
    node_budget=DEFAULT_NODE_BUDGET,
    time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
):
    """Build a month's schedule, choosing a search strategy to suit the month.

    employees: [{id, max_shifts_per_month, unavailable_weekdays: set[int],
                 unavailable_dates: set[str ISO date], allowed_shift_types: set[int] or None}]
    shift_types: [{id, requirements: {weekday(0-6): required_count}}]

    Benchmarking the two slot orderings against each other (see benchmark.py)
    showed they win in different situations, so neither is right on its own:

      * Chronological order interleaves the days naturally, so always picking the
        least-loaded eligible person lands on an evenly balanced plan straight
        away - often provably the most balanced one possible - in roughly one
        node per shift.
      * Most-constrained-first is far better when there genuinely are not enough
        people: on an understaffed test month it left 17 shifts unstaffed, which
        an exact CP-SAT solve confirmed is the true minimum, where chronological
        order left 23. But it scrambles the day order, which costs balance on
        months that were comfortably staffable anyway.

    So AUTO plans chronologically first, and only if that leaves shifts unstaffed
    does it pay for a second, harder search - taking whichever plan comes out
    better. Normal months therefore cost one cheap pass, and difficult months get
    the extra effort where it actually buys something.
    """
    def run(order):
        return _search(year, month, employees, shift_types, order, fairness,
                       weekend_weight, node_budget, time_budget_seconds)

    if ordering != AUTO:
        result = run(ordering)
    else:
        result = run(CHRONOLOGICAL)
        if result['unfilled_count'] > 0:
            alternative = run(MOST_CONSTRAINED)
            nodes = result['nodes_explored'] + alternative['nodes_explored']
            if (alternative['unfilled_count'], alternative['cost']) < (result['unfilled_count'], result['cost']):
                result = alternative
            result['nodes_explored'] = nodes

    result['fairness'] = fairness_stats(result['assignments'], employees)
    return result
