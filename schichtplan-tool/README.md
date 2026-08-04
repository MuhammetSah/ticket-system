# Schichtplan-Tool

An automated shift-scheduling tool for HR teams, built with React (frontend) and Flask (backend). HR defines employees, their availability constraints, and shift types with staffing requirements; the tool generates a full monthly schedule via backtracking search and lets HR fine-tune the result by hand — including swapping shifts between employees.

This is a standalone project living alongside the Support Ticket System in this repository, and the fourth project in a portfolio (after the portfolio website, the ticket system, and a paused API-integration project).

## Grundidee

Industry-independent shift planning for HR: define employees with constraints (e.g. "never works Wednesdays", "only early shift"), define shift types with per-weekday staffing needs, then generate a month's schedule automatically. No employee accounts or login — this is an internal HR tool; employees are records, not users.

## Scope

- **No employee login** – pure HR tool, single internal user
- **Monthly plans** – one schedule per calendar month
- **Backtracking scheduling algorithm** – not greedy (see below)
- **Manual post-editing by HR** – reassign any slot, or swap two shifts between employees
- **Balanced workloads** – the plan spreads shifts evenly once every shift that *can* be staffed is

## Features

- **Employee management** – name, optional email, optional monthly shift cap, recurring weekday unavailability (e.g. no Wednesdays), one-off unavailable dates (vacation/sick leave), and an optional allow-list restricting an employee to specific shift types (e.g. "only early shift")
- **Shift type management** – name, start/end time, color, and required headcount per weekday (weekday and weekend staffing needs are often different)
- **Automatic monthly schedule generation** via backtracking search
- **Manual editing** – reassign any shift slot to a different employee (or leave it unfilled), with non-blocking warnings if the change violates that employee's usual constraints (HR can always override)
- **Shift swapping** – pick two shifts and swap their assigned employees in one atomic action
- **Unfilled-slot reporting** – when there isn't enough eligible staff, the tool reports exactly how many/which slots couldn't be filled instead of failing silently or crashing
- **Workload distribution panel** – shifts per employee (and weekend shifts per employee) for the month, recomputed from what's actually saved, so it stays honest as HR edits the plan by hand

## The scheduling algorithm

`backend/scheduler.py` assigns employees to shifts via **chronological backtracking with branch-and-bound**, not a greedy pass.

A greedy algorithm assigns the first workable candidate to each slot and never reconsiders. That can leave avoidable gaps: if employee A is the only one who can cover a later shift, but a greedy pass already spent them on an earlier shift that someone else could equally have covered, the later shift ends up unfilled for no good reason.

This algorithm instead explores assignments slot by slot in calendar order, and **undoes (backtracks) a choice** whenever it turns out to block a later slot with no other eligible candidate. It keeps searching after finding one complete assignment, in case a different set of choices leaves fewer slots unfilled (branch-and-bound: a running best-so-far result prunes any branch that can't beat it, and search stops early once a fully-staffed solution is found). A node/time budget acts as a safety valve on pathologically understaffed inputs, so a request always returns a best-effort result instead of hanging.

Hard constraints enforced during search: an employee can't work two shifts the same day, can't be scheduled on a weekday/date they're marked unavailable, can't be scheduled outside their allowed shift types (if restricted), and can't exceed their monthly shift cap (if set).

`backend/test_scheduler.py` includes a test that constructs a scenario where a literal greedy-first-fit pass provably leaves gaps that this algorithm closes, alongside tests for each hard constraint and for graceful degradation when there isn't enough staff to fill every slot.

### Fairness (v1.3)

The search optimizes a **lexicographic** objective:

1. minimize unfilled shifts — a fairer plan is never worth leaving a shift unstaffed
2. minimize the **sum of squared shift counts** per employee

Minimizing the sum of squares is equivalent to minimizing the variance of the workload once the number of assigned shifts is fixed, and it updates in O(1) per assignment: giving a shift to someone who already has `L` raises the cost by `2L+1`, so each extra shift for an already-busy person is penalized more than a first shift for an idle one. Both components only ever grow as the search goes deeper, so any branch whose partial cost already loses to the best complete plan can be pruned safely.

An optional `weekend_weight` applies the same idea to weekend shifts specifically — weekend duty is usually the scarce thing that quietly lands on the same few people every month.

### Slot ordering (v1.2), and why it is adaptive

The planned v1.2 feature was "most constrained first" ordering — the classic CSP minimum-remaining-values heuristic, filling the hardest-to-staff slots first so dead ends surface near the top of the search tree where backtracking is cheap.

Benchmarking it against plain calendar order produced a **result that contradicted the original plan**, and the design changed accordingly:

- On **understaffed** months it is clearly better: it left **17 shifts unstaffed where calendar order left 23**, and an exact CP-SAT solve confirmed 17 is the true minimum.
- On **comfortably staffed** months it is clearly *worse* — not for staffing (both fill everything) but for **balance**. Calendar order interleaves the days naturally, so "always pick the least-loaded eligible person" lands on an evenly balanced plan immediately. Reordering the slots scrambles that: on the 30-person hospital scenario it produced a workload spread of **9 shifts instead of 1**.

So neither ordering is right on its own, and the shipped default (`ordering='auto'`) plans chronologically first and only pays for a second, harder search if that leaves shifts unstaffed — taking whichever plan comes out better. Normal months cost one cheap pass; difficult months get the extra effort where it actually buys something.

## Comparison with other approaches

`backend/benchmark.py` runs every approach against the same seeded scenarios under identical constraints, scored on what an HR user actually cares about: unstaffed shifts, workload spread (busiest minus quietest), weekend spread, and runtime. `backend/baselines.py` contains the alternatives.

Run it with `./venv/bin/python benchmark.py` (needs `requirements-dev.txt` for the CP-SAT reference).

**Hospital ward — 30 people, 3 shifts, 372 shifts to fill:**

| approach | unfilled | spread | weekend | time |
|---|---|---|---|---|
| greedy first-fit | 0 | 31 | 10 | 0.002s |
| greedy, least-loaded | 0 | 1 | 5 | 0.004s |
| random-restart greedy (200×) | 0 | 1 | 6 | 0.849s |
| most-constrained-first only | 0 | 9 | 7 | 0.009s |
| **this tool (v1.3 auto)** | **0** | **1** | **5** | **0.006s** ✓ |
| this tool + weekend equity | 0 | 2 | **2** | 0.416s |
| CP-SAT (OR-Tools, exact) | 0 | 1 | 7 | 5.398s ✓ |

**Understaffed month — 5 heavily restricted people, 124 shifts to fill:**

| approach | unfilled | time |
|---|---|---|
| greedy, least-loaded | 25 | 0.000s |
| greedy first-fit | 18 | 0.001s |
| random-restart greedy (200×) | 17 | 0.084s |
| calendar order only | 23 | 0.380s |
| **this tool (v1.3 auto)** | **17** | 0.693s |
| CP-SAT (OR-Tools, exact) | 17 | 0.037s ✓ |

✓ = proven optimal for staffing *and* balance together.

**What the comparison actually shows:**

- **Naive greedy is not viable.** First-fit hands one person all 31 days of the month while colleagues get nothing (spread 31).
- **Greedy with a least-loaded tie-break is a surprisingly strong baseline** — it matches the optimum on easy months. Its weakness is understaffed ones, where it left 25 shifts unstaffed against the true minimum of 17. This is worth stating plainly: most of the everyday quality comes from that one heuristic, and search earns its keep specifically when staffing is tight.
- **This tool matches CP-SAT's proven optimum on unstaffed shifts in every scenario tested**, and matches it on workload spread in all but one — at ~900× the speed on the largest scenario (0.006s vs 5.4s).
- **CP-SAT is the better tool for a harder problem, not this one.** It proves optimality, which the hand-written search generally cannot, and it would absorb genuinely complex rules (rest periods between shifts, skill mixes, labor-law constraints) that would be painful to hand-code. The tradeoffs against it here are a ~100MB native dependency and a solve time that grows steeply with the roster. For monthly plans at this scale, a ~250-line dependency-free search gets the same answers fast enough to feel instant in the UI.
- **Fairness dimensions genuinely trade off.** Optimizing only total shifts can leave weekend duty lopsided (weekend spread 5 while total spread is optimal); turning on weekend equity cut it to 2 at the cost of one shift of total spread. There is no single "fair", so it's a setting rather than a hardcoded rule.

**Roadmap** (not yet built):
- **v1.1** – a guided shift-swap flow (the underlying swap capability already exists)
- Rest periods between consecutive shifts (e.g. no late shift followed by an early shift)
- Skill/qualification matching, so a shift can require a specific certification

## Tech Stack

**Frontend**
- React (with Vite)
- React Router

**Backend**
- Flask
- SQLite
- Flask-CORS

## Project Structure

```
schichtplan-tool/
├── backend/
│   ├── app.py                 # Flask app: REST routes
│   ├── db.py                   # SQLite schema + connection
│   ├── scheduler.py            # Backtracking scheduler (ordering + fairness)
│   ├── baselines.py            # Alternative algorithms, for comparison only
│   ├── benchmark.py            # Head-to-head comparison run
│   ├── test_scheduler.py       # Unit tests for the algorithm
│   ├── requirements.txt
│   └── requirements-dev.txt    # + ortools, only needed for the benchmark
└── frontend/
    └── src/
        ├── App.jsx           # Routing & navigation
        ├── api.js            # Fetch helper + shared constants
        ├── pages/
        │   ├── Employees.jsx     # Employee CRUD + constraints
        │   ├── ShiftTypes.jsx    # Shift type CRUD + weekday requirements
        │   └── SchedulePage.jsx  # Generate / view / edit the monthly plan
        └── components/
            ├── ScheduleGrid.jsx  # The schedule grid: reassign + swap UI
            └── Distribution.jsx  # Shifts-per-employee balance panel
```

## Local Setup

### Backend

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py
```

Runs by default on `http://localhost:5001` (chosen so it doesn't collide with the ticket-system backend on port 5000 if both run locally at once). Uses a local SQLite file (`schichtplan.db`, gitignored); the schema is created automatically on first run.

Run the scheduler's unit tests with:

```bash
./venv/bin/python -m unittest test_scheduler -v
```

To run the algorithm comparison (installs OR-Tools for the exact CP-SAT reference):

```bash
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python benchmark.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs by default on `http://localhost:5173`.

Create a `.env` file in the `frontend` folder with:

```
VITE_API_URL=http://localhost:5001
```

## API Endpoints

| Method | Route                          | Description                                              |
|--------|----------------------------------|------------------------------------------------------------|
| GET    | `/employees`                    | List employees (with their constraints)                    |
| POST   | `/employees`                    | Create an employee                                          |
| GET    | `/employees/<id>`               | Get one employee                                             |
| PUT    | `/employees/<id>`                | Update an employee (replaces constraints)                    |
| DELETE | `/employees/<id>`                | Delete an employee                                            |
| GET    | `/shift-types`                  | List shift types (with per-weekday requirements)              |
| POST   | `/shift-types`                  | Create a shift type                                            |
| PUT    | `/shift-types/<id>`               | Update a shift type                                             |
| DELETE | `/shift-types/<id>`               | Delete a shift type (blocked if used by an existing schedule)   |
| POST   | `/schedules/generate`            | Generate (or regenerate) a month's schedule `{year, month}`      |
| GET    | `/schedules/<year>/<month>`      | Get a month's schedule, its assignments, and the workload distribution |
| DELETE | `/schedules/<year>/<month>`      | Delete a month's schedule                                           |
| PUT    | `/assignments/<id>`               | Reassign one shift slot to a different employee (or `null`)          |
| POST   | `/assignments/swap`               | Swap the employees on two shift assignments `{assignment_id_a, assignment_id_b}` |

## Status

Built and tested locally through v1.3: 16 unit tests, a benchmark against four alternative algorithms plus an exact solver, and a full browser walkthrough of create → generate → reassign → swap → check balance. Not yet deployed.

## About This Project

This is the "signature project" of a portfolio built while transitioning into web development — the most involved piece technically, centered on the scheduling algorithm rather than CRUD alone.

The part worth reading is `backend/scheduler.py` together with `backend/benchmark.py`: the benchmark is what turned the planned v1.2 heuristic from "obviously an improvement" into a measured tradeoff, and changed the design from a fixed ordering to an adaptive one.
