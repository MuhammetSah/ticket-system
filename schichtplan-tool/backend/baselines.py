"""Alternative scheduling algorithms, used to benchmark the backtracking scheduler.

None of these are used by the running app - they exist so the approach actually
chosen in scheduler.py can be measured against the obvious alternatives instead
of just being asserted to be better. See benchmark.py for the comparison run.

Every function here takes and returns the same shapes as
scheduler.generate_schedule, so the benchmark can treat them interchangeably.
"""

import random
import time

from scheduler import build_slots, fairness_stats, structurally_eligible

try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the optional dev dependency
    ORTOOLS_AVAILABLE = False


def _result(assignments, slots, employees, elapsed, **extra):
    unfilled_count = sum(1 for a in assignments if a['employee_id'] is None)
    result = {
        'assignments': assignments,
        'total_slots': len(slots),
        'unfilled_count': unfilled_count,
        'complete': unfilled_count == 0,
        'elapsed_seconds': elapsed,
        'fairness': fairness_stats(assignments, employees),
    }
    result.update(extra)
    return result


def _empty_assignments(slots):
    return [
        {
            'date': s['date'],
            'shift_type_id': s['shift_type_id'],
            'slot_index': s['slot_index'],
            'employee_id': None,
            'is_weekend': s['is_weekend'],
        }
        for s in slots
    ]


def _feasible(emp, slot, load, day_usage):
    if emp['id'] in day_usage.get(slot['date'], ()):
        return False
    if not structurally_eligible(emp, slot):
        return False
    cap = emp['max_shifts_per_month']
    if cap is not None and load[emp['id']] >= cap:
        return False
    return True


def greedy_first_fit(year, month, employees, shift_types, **_kwargs):
    """The naive approach: walk the month, take the first person who can work each slot.

    Never reconsiders a choice, so an early assignment can strand a later slot
    that only that person could have covered.
    """
    start = time.monotonic()
    slots = build_slots(year, month, shift_types)
    assignments = _empty_assignments(slots)
    load = {e['id']: 0 for e in employees}
    day_usage = {}

    for a, slot in zip(assignments, slots):
        for emp in employees:
            if _feasible(emp, slot, load, day_usage):
                a['employee_id'] = emp['id']
                day_usage.setdefault(slot['date'], set()).add(emp['id'])
                load[emp['id']] += 1
                break

    return _result(assignments, slots, employees, time.monotonic() - start)


def greedy_balanced(year, month, employees, shift_types, **_kwargs):
    """Greedy, but always picks the least-loaded eligible person.

    This isolates how much of the final quality comes from the load-balancing
    heuristic alone, versus from actually searching and backtracking.
    """
    start = time.monotonic()
    slots = build_slots(year, month, shift_types)
    assignments = _empty_assignments(slots)
    load = {e['id']: 0 for e in employees}
    day_usage = {}

    for a, slot in zip(assignments, slots):
        candidates = [e for e in employees if _feasible(e, slot, load, day_usage)]
        if not candidates:
            continue
        emp = min(candidates, key=lambda e: (load[e['id']], e['id']))
        a['employee_id'] = emp['id']
        day_usage.setdefault(slot['date'], set()).add(emp['id'])
        load[emp['id']] += 1

    return _result(assignments, slots, employees, time.monotonic() - start)


def random_restart_greedy(year, month, employees, shift_types, restarts=200, seed=12345, **_kwargs):
    """Randomised greedy, repeated, keeping the best plan seen.

    A cheap stochastic alternative to systematic search: no backtracking, but
    many rolls of the dice.
    """
    start = time.monotonic()
    slots = build_slots(year, month, shift_types)
    rng = random.Random(seed)
    best = None
    best_key = None

    for _ in range(restarts):
        assignments = _empty_assignments(slots)
        load = {e['id']: 0 for e in employees}
        day_usage = {}
        order = list(range(len(slots)))
        rng.shuffle(order)

        for i in order:
            slot = slots[i]
            candidates = [e for e in employees if _feasible(e, slot, load, day_usage)]
            if not candidates:
                continue
            lowest = min(load[e['id']] for e in candidates)
            emp = rng.choice([e for e in candidates if load[e['id']] == lowest])
            assignments[i]['employee_id'] = emp['id']
            day_usage.setdefault(slot['date'], set()).add(emp['id'])
            load[emp['id']] += 1

        unfilled = sum(1 for a in assignments if a['employee_id'] is None)
        key = (unfilled, sum(v * v for v in load.values()))
        if best_key is None or key < best_key:
            best_key, best = key, assignments

    return _result(best, slots, employees, time.monotonic() - start, restarts=restarts)


def cp_sat(year, month, employees, shift_types, time_budget_seconds=10.0, **_kwargs):
    """Constraint-programming solver (Google OR-Tools CP-SAT).

    This is the industrial-strength reference: the same hard constraints and the
    same lexicographic objective (fill shifts first, then balance the workload)
    handed to a general-purpose solver. Used to check how far the hand-written
    backtracking search lands from a proven optimum.
    """
    if not ORTOOLS_AVAILABLE:
        raise RuntimeError('ortools is not installed - see requirements-dev.txt')

    start = time.monotonic()
    slots = build_slots(year, month, shift_types)
    assignments = _empty_assignments(slots)
    model = cp_model.CpModel()

    # x[(slot, employee)] = this employee works this slot.
    x = {}
    for i, slot in enumerate(slots):
        for emp in employees:
            if structurally_eligible(emp, slot):
                x[(i, emp['id'])] = model.NewBoolVar(f'x_{i}_{emp["id"]}')

    # Each slot is filled at most once (unfilled is allowed, and penalised below).
    unfilled_vars = []
    for i, slot in enumerate(slots):
        slot_vars = [x[(i, e['id'])] for e in employees if (i, e['id']) in x]
        unfilled = model.NewBoolVar(f'unfilled_{i}')
        unfilled_vars.append(unfilled)
        model.Add(sum(slot_vars) + unfilled == 1)

    # Nobody works two shifts on the same day.
    slots_by_date = {}
    for i, slot in enumerate(slots):
        slots_by_date.setdefault(slot['date'], []).append(i)
    for indices in slots_by_date.values():
        for emp in employees:
            same_day = [x[(i, emp['id'])] for i in indices if (i, emp['id']) in x]
            if len(same_day) > 1:
                model.Add(sum(same_day) <= 1)

    # Monthly caps, and the per-employee workload used by the fairness objective.
    load_squares = []
    for emp in employees:
        emp_vars = [x[(i, emp['id'])] for i in range(len(slots)) if (i, emp['id']) in x]
        upper = len(emp_vars)
        load = model.NewIntVar(0, upper, f'load_{emp["id"]}')
        if emp_vars:
            model.Add(load == sum(emp_vars))
        else:
            model.Add(load == 0)
        cap = emp['max_shifts_per_month']
        if cap is not None:
            model.Add(load <= cap)
        square = model.NewIntVar(0, upper * upper if upper else 0, f'sq_{emp["id"]}')
        model.AddMultiplicationEquality(square, [load, load])
        load_squares.append(square)

    # Lexicographic objective: any unfilled shift costs more than the worst
    # possible imbalance, so filling shifts always dominates balancing them.
    big = (len(slots) ** 2) + 1
    model.Minimize(big * sum(unfilled_vars) + sum(load_squares))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_budget_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i, slot in enumerate(slots):
            for emp in employees:
                if (i, emp['id']) in x and solver.Value(x[(i, emp['id'])]):
                    assignments[i]['employee_id'] = emp['id']
                    break

    return _result(
        assignments, slots, employees, time.monotonic() - start,
        proven_optimal=status == cp_model.OPTIMAL,
        status=solver.StatusName(status),
    )
