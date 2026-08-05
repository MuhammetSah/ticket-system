import sqlite3

DB_PATH = 'schichtplan.db'

# Weekday convention throughout this project: 0=Monday ... 6=Sunday (Python's date.weekday()).
WEEKDAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']


def get_db_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.execute('PRAGMA foreign_keys = ON')
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Accounts that can sign in. Two roles:
    #   'hr'       - full access: manages employees, shift types and schedules
    #   'employee' - read-only: may look at the published schedule, nothing else
    # Being scheduled does not require an account, so the employees table stays
    # separate; employee_id optionally links an account to its roster entry so
    # the calendar can highlight that person's own shifts.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'hr',
            employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # One open invitation per account. HR never sees the token: it goes out by
    # email, so the person sets a password only they know. Only a SHA-256 of the
    # token is stored, so a copy of the database cannot be used to claim an
    # account - the token itself is 256 bits of randomness, which is why an
    # unsalted digest is enough here.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS password_invitations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Databases created before roles existed only have the original columns.
    cursor.execute('PRAGMA table_info(users)')
    user_columns = {row['name'] for row in cursor.fetchall()}
    if 'role' not in user_columns:
        # Existing accounts predate the split and were all full-access.
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'hr'")
    if 'employee_id' not in user_columns:
        cursor.execute('ALTER TABLE users ADD COLUMN employee_id INTEGER REFERENCES employees(id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            max_shifts_per_month INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Recurring weekly unavailability, e.g. "never works Wednesdays".
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employee_unavailable_weekdays(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL,
            UNIQUE(employee_id, weekday)
        )
    ''')

    # One-off unavailability, e.g. vacation or sick leave on specific dates.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employee_unavailable_dates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            reason TEXT,
            UNIQUE(employee_id, date)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shift_types(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#0d9488',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # How many people are needed for a shift type, per weekday (weekends often differ from weekdays).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shift_requirements(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL,
            required_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(shift_type_id, weekday)
        )
    ''')

    # If an employee has no rows here, they may work any shift type (no restriction).
    # If they have rows, they may only work the listed shift types (e.g. "only Frühschicht").
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employee_allowed_shift_types(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
            UNIQUE(employee_id, shift_type_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            unfilled_count INTEGER NOT NULL DEFAULT 0,
            generated_at TIMESTAMP,
            UNIQUE(year, month)
        )
    ''')

    # Lets one date run a shift at different hours than the shift type says,
    # e.g. the early shift finishing at 14:00 on Christmas Eve. Keyed per shift
    # per date, so everyone on that shift that day shares the changed hours.
    # Deliberately survives regeneration: hours HR set for a date should stick.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shift_time_overrides(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            UNIQUE(schedule_id, date, shift_type_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shift_assignments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id),
            slot_index INTEGER NOT NULL,
            employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            manually_edited INTEGER NOT NULL DEFAULT 0
        )
    ''')

    connection.commit()
    connection.close()
