"""Head-to-head comparison of the scheduling approaches.

Run with:  ./venv/bin/python benchmark.py

Each strategy solves the same seeded scenarios under the same hard constraints,
and is scored on what actually matters to an HR user:

  unfilled  - shifts nobody was assigned to (lower is better; dominates everything)
  spread    - busiest employee's shift count minus the quietest (lower is fairer)
  wknd      - the same spread measured over weekend shifts only
  time      - wall-clock seconds to produce the plan

CP-SAT (OR-Tools) is included as a proven-optimal reference point, not as a
candidate implementation: it is a heavy dependency for what this tool needs.
"""

import random

import baselines
from scheduler import CHRONOLOGICAL, MOST_CONSTRAINED, generate_schedule


def employee(id, max_shifts_per_month=None, unavailable_weekdays=None, unavailable_dates=None, allowed_shift_types=None):
    return {
        'id': id,
        'max_shifts_per_month': max_shifts_per_month,
        'unavailable_weekdays': set(unavailable_weekdays or []),
        'unavailable_dates': set(unavailable_dates or []),
        'allowed_shift_types': set(allowed_shift_types) if allowed_shift_types else None,
    }


def scenario_small_team():
    """A cafe: 6 people, two shifts a day, a couple of fixed days off."""
    employees = [
        employee(1), employee(2),
        employee(3, unavailable_weekdays=[2]),
        employee(4, unavailable_weekdays=[5, 6]),
        employee(5, allowed_shift_types=[1]),
        employee(6, max_shifts_per_month=10),
    ]
    shift_types = [
        {'id': 1, 'requirements': {wd: 1 for wd in range(7)}},
        {'id': 2, 'requirements': {wd: 1 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_realistic_shop():
    """A retail shop: 14 people, three shifts, weekday-heavy staffing."""
    rng = random.Random(7)
    employees = []
    for i in range(1, 15):
        employees.append(employee(
            i,
            max_shifts_per_month=rng.choice([None, None, None, 15, 18]),
            unavailable_weekdays=rng.sample(range(7), k=rng.choice([0, 0, 1, 1, 2])),
            allowed_shift_types=rng.choice([None, None, None, [1], [1, 2]]),
        ))
    shift_types = [
        {'id': 1, 'requirements': {wd: (3 if wd < 5 else 2) for wd in range(7)}},
        {'id': 2, 'requirements': {wd: (2 if wd < 5 else 1) for wd in range(7)}},
        {'id': 3, 'requirements': {wd: 1 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_tight():
    """Barely enough staff: heavy restrictions, little slack. Where greedy hurts."""
    employees = [
        employee(1, allowed_shift_types=[1]),
        employee(2, allowed_shift_types=[1]),
        employee(3, allowed_shift_types=[2]),
        employee(4, unavailable_weekdays=[0, 1]),
        employee(5, unavailable_weekdays=[5, 6], max_shifts_per_month=12),
        employee(6, max_shifts_per_month=8),
        employee(7),
    ]
    shift_types = [
        {'id': 1, 'requirements': {wd: 2 for wd in range(7)}},
        {'id': 2, 'requirements': {wd: 1 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_large_hospital():
    """A ward: 30 people, three round-the-clock shifts, vacation blocks."""
    rng = random.Random(99)
    employees = []
    for i in range(1, 31):
        vacation_start = rng.randint(1, 20)
        employees.append(employee(
            i,
            max_shifts_per_month=rng.choice([None, 20, 22]),
            unavailable_weekdays=rng.sample(range(7), k=rng.choice([0, 1, 1, 2])),
            unavailable_dates=[f'2026-08-{day:02d}' for day in range(vacation_start, vacation_start + rng.choice([0, 0, 5]))],
            allowed_shift_types=rng.choice([None, None, None, [1, 2], [3]]),
        ))
    shift_types = [
        {'id': 1, 'requirements': {wd: 5 for wd in range(7)}},
        {'id': 2, 'requirements': {wd: 4 for wd in range(7)}},
        {'id': 3, 'requirements': {wd: 3 for wd in range(7)}},
    ]
    return employees, shift_types


def scenario_understaffed():
    """Genuinely too few people for the demand: the plan will have gaps whatever
    you do, so the only question is how many. This is where search earns its keep."""
    employees = [
        employee(1, allowed_shift_types=[1]),
        employee(2, allowed_shift_types=[1], unavailable_weekdays=[5, 6]),
        employee(3, allowed_shift_types=[2]),
        employee(4, max_shifts_per_month=6),
        employee(5, unavailable_weekdays=[0, 1, 2]),
    ]
    shift_types = [
        {'id': 1, 'requirements': {wd: 2 for wd in range(7)}},
        {'id': 2, 'requirements': {wd: 2 for wd in range(7)}},
    ]
    return employees, shift_types


# (label, callable, optimises_fairness) - the last flag decides whether a proven
# result may be marked optimal on *both* axes the table reports.
STRATEGIES = [
    ('greedy first-fit', lambda *a: baselines.greedy_first_fit(*a), False),
    ('greedy balanced', lambda *a: baselines.greedy_balanced(*a), False),
    ('random-restart greedy', lambda *a: baselines.random_restart_greedy(*a), False),
    ('v1   chronological', lambda *a: generate_schedule(*a, ordering=CHRONOLOGICAL, fairness=False), False),
    ('v1.2 constrained-first', lambda *a: generate_schedule(*a, ordering=MOST_CONSTRAINED, fairness=False), False),
    ('v1.3 fairness (chrono)', lambda *a: generate_schedule(*a, ordering=CHRONOLOGICAL, fairness=True), True),
    ('v1.3 fairness (constr.)', lambda *a: generate_schedule(*a, ordering=MOST_CONSTRAINED, fairness=True), True),
    ('v1.3 AUTO (production)', lambda *a: generate_schedule(*a), True),
    ('v1.3 AUTO + weekend eq.', lambda *a: generate_schedule(*a, weekend_weight=3), True),
]

if baselines.ORTOOLS_AVAILABLE:
    STRATEGIES.append(('CP-SAT (reference)', lambda *a: baselines.cp_sat(*a), True))


SCENARIOS = [
    ('Small team (6 people, 2 shifts)', scenario_small_team),
    ('Retail shop (14 people, 3 shifts)', scenario_realistic_shop),
    ('Tight staffing (7 people, heavy limits)', scenario_tight),
    ('Hospital ward (30 people, 3 shifts)', scenario_large_hospital),
    ('Understaffed (5 people, gaps unavoidable)', scenario_understaffed),
]


def run():
    import time as _time
    year, month = 2026, 8

    for title, build in SCENARIOS:
        employees, shift_types = build()
        print(f'\n{title}')
        print(f'{"strategy":<26} {"unfilled":>9} {"spread":>7} {"wknd":>5} {"time":>10}')
        print('-' * 62)

        for name, strategy, optimises_fairness in STRATEGIES:
            start = _time.monotonic()
            result = strategy(year, month, employees, shift_types)
            elapsed = result.get('elapsed_seconds', _time.monotonic() - start)
            f = result['fairness']
            proven = result.get('proven_optimal') and optimises_fairness
            print(f'{name:<26} {result["unfilled_count"]:>9} {f["spread"]:>7} '
                  f'{f["weekend_spread"]:>5} {elapsed:>9.3f}s{" *" if proven else ""}')

        print(f'  total slots: {result["total_slots"]}   '
              f'* = proven optimal for gaps and balance together')


if __name__ == '__main__':
    run()
