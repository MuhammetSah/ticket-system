# Schichtplan-Tool

An automated shift-scheduling tool for HR teams, built with React (frontend) and Flask (backend). HR defines employees, their availability constraints, and shift types with staffing requirements; the tool generates a full monthly schedule via backtracking search and lets HR fine-tune the result by hand — including swapping shifts between employees.

This is a standalone project living alongside the Support Ticket System in this repository, and the fourth project in a portfolio (after the portfolio website, the ticket system, and a paused API-integration project).

## Grundidee

Industry-independent shift planning for HR: define employees with constraints (e.g. "never works Wednesdays", "only early shift"), define shift types with per-weekday staffing needs, then generate a month's schedule automatically. No employee accounts or login — this is an internal HR tool; employees are records, not users.

## v1 scope

- **No employee login** – pure HR tool, single internal user
- **Monthly plans** – one schedule per calendar month
- **Backtracking scheduling algorithm** – not greedy (see below)
- **Manual post-editing by HR** – reassign any slot, or swap two shifts between employees

## Features

- **Employee management** – name, optional email, optional monthly shift cap, recurring weekday unavailability (e.g. no Wednesdays), one-off unavailable dates (vacation/sick leave), and an optional allow-list restricting an employee to specific shift types (e.g. "only early shift")
- **Shift type management** – name, start/end time, color, and required headcount per weekday (weekday and weekend staffing needs are often different)
- **Automatic monthly schedule generation** via backtracking search
- **Manual editing** – reassign any shift slot to a different employee (or leave it unfilled), with non-blocking warnings if the change violates that employee's usual constraints (HR can always override)
- **Shift swapping** – pick two shifts and swap their assigned employees in one atomic action
- **Unfilled-slot reporting** – when there isn't enough eligible staff, the tool reports exactly how many/which slots couldn't be filled instead of failing silently or crashing

## The scheduling algorithm

`backend/scheduler.py` assigns employees to shifts via **chronological backtracking with branch-and-bound**, not a greedy pass.

A greedy algorithm assigns the first workable candidate to each slot and never reconsiders. That can leave avoidable gaps: if employee A is the only one who can cover a later shift, but a greedy pass already spent them on an earlier shift that someone else could equally have covered, the later shift ends up unfilled for no good reason.

This algorithm instead explores assignments slot by slot in calendar order, and **undoes (backtracks) a choice** whenever it turns out to block a later slot with no other eligible candidate. It keeps searching after finding one complete assignment, in case a different set of choices leaves fewer slots unfilled (branch-and-bound: a running best-so-far result prunes any branch that can't beat it, and search stops early once a fully-staffed solution is found). A node/time budget acts as a safety valve on pathologically understaffed inputs, so a request always returns a best-effort result instead of hanging.

Hard constraints enforced during search: an employee can't work two shifts the same day, can't be scheduled on a weekday/date they're marked unavailable, can't be scheduled outside their allowed shift types (if restricted), and can't exceed their monthly shift cap (if set).

`backend/test_scheduler.py` includes a test that constructs a scenario where a literal greedy-first-fit pass provably leaves gaps that this algorithm closes, alongside tests for each hard constraint and for graceful degradation when there isn't enough staff to fill every slot.

**Roadmap** (not yet built):
- **v1.1** – a guided shift-swap flow (the underlying swap capability already exists in v1)
- **v1.2** – "most constrained first" slot ordering (currently slots are processed in calendar order)
- **v1.3** – fairness optimization across employees (v1 only lightly tie-breaks toward whoever has fewer shifts so far)

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
│   ├── app.py              # Flask app: REST routes
│   ├── db.py                # SQLite schema + connection
│   ├── scheduler.py         # Backtracking scheduling algorithm
│   ├── test_scheduler.py    # Unit tests for the algorithm
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.jsx           # Routing & navigation
        ├── api.js            # Fetch helper + shared constants
        ├── pages/
        │   ├── Employees.jsx     # Employee CRUD + constraints
        │   ├── ShiftTypes.jsx    # Shift type CRUD + weekday requirements
        │   └── SchedulePage.jsx  # Generate / view / edit the monthly plan
        └── components/
            └── ScheduleGrid.jsx  # The schedule grid: reassign + swap UI
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
| GET    | `/schedules/<year>/<month>`      | Get a month's schedule with all assignments                       |
| DELETE | `/schedules/<year>/<month>`      | Delete a month's schedule                                           |
| PUT    | `/assignments/<id>`               | Reassign one shift slot to a different employee (or `null`)          |
| POST   | `/assignments/swap`               | Swap the employees on two shift assignments `{assignment_id_a, assignment_id_b}` |

## Status

v1 built and tested locally (unit tests + full browser walkthrough of create → generate → reassign → swap). Not yet deployed.

## About This Project

This is the "signature project" of a portfolio built while transitioning into web development — the most involved piece technically, centered on the backtracking scheduling algorithm rather than CRUD alone.
