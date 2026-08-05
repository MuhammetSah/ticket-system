import os
from datetime import date
from functools import wraps

from flask import Flask, jsonify, request, session
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db_connection, init_db, WEEKDAYS
from scheduler import generate_schedule

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'schichtplan-local-dev')

if os.environ.get('FLASK_ENV') == 'production':
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True

# supports_credentials is required for the session cookie to survive the
# cross-origin hop from the Vite dev server to this API.
CORS(
    app,
    supports_credentials=True,
    origins=[
        origin.strip()
        for origin in os.environ.get(
            'ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:5174'
        ).split(',')
        if origin.strip()
    ],
)

init_db()


# ---------- authentication ----------

def current_user_id():
    return session.get('user_id')


def login_required(view):
    """Every route that touches staff data sits behind this.

    Employees never log in - this guards the HR side of the tool, which is the
    only side there is. Without it the whole roster, including names, emails and
    booked time off, is readable by anyone who can reach the API.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user_id():
            return jsonify({'message': 'Nicht angemeldet'}), 401
        return view(*args, **kwargs)

    return wrapped


def count_users(cursor):
    cursor.execute('SELECT COUNT(*) AS n FROM users')
    return cursor.fetchone()['n']


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'message': 'Benutzername und Passwort sind erforderlich'}), 400
    if len(password) < 8:
        return jsonify({'message': 'Das Passwort muss mindestens 8 Zeichen lang sein'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    # The first account sets the tool up; after that, only someone already logged
    # in may add colleagues. Otherwise anyone finding the URL could sign
    # themselves up and read the entire roster.
    if count_users(cursor) > 0 and not current_user_id():
        connection.close()
        return jsonify({'message': 'Neue Konten kann nur ein angemeldeter Benutzer anlegen'}), 403

    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Benutzername ist bereits vergeben'}), 400

    cursor.execute(
        'INSERT INTO users (username, hash) VALUES (?, ?)',
        (username, generate_password_hash(password)),
    )
    user_id = cursor.lastrowid
    connection.commit()
    connection.close()

    # Signing in the very first user saves them an immediate second step; an
    # existing user adding a colleague must stay logged in as themselves.
    if not current_user_id():
        session['user_id'] = user_id

    return jsonify({'id': user_id, 'username': username}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    connection.close()

    # Same message either way, so the response cannot be used to find out which
    # usernames exist.
    if not user or not check_password_hash(user['hash'], password):
        return jsonify({'message': 'Benutzername oder Passwort ist falsch'}), 401

    session.clear()
    session['user_id'] = user['id']
    return jsonify({'id': user['id'], 'username': user['username']}), 200


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Abgemeldet'}), 200


@app.route('/me', methods=['GET'])
def me():
    user_id = current_user_id()
    connection = get_db_connection()
    cursor = connection.cursor()

    # The frontend uses this on load both to restore a session and to find out
    # whether this is a fresh install that still needs its first account.
    setup_required = count_users(cursor) == 0

    if not user_id:
        connection.close()
        return jsonify({'message': 'Nicht angemeldet', 'setup_required': setup_required}), 401

    cursor.execute('SELECT id, username FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    connection.close()

    if not user:
        # The account was deleted while the cookie was still around.
        session.clear()
        return jsonify({'message': 'Nicht angemeldet', 'setup_required': setup_required}), 401

    return jsonify({'id': user['id'], 'username': user['username'], 'setup_required': False}), 200


# ---------- serialization helpers ----------

def parse_int_list(value):
    if not value:
        return []
    return [int(v) for v in value]


def serialize_employee(cursor, row):
    employee_id = row['id']
    cursor.execute('SELECT weekday FROM employee_unavailable_weekdays WHERE employee_id = ? ORDER BY weekday', (employee_id,))
    unavailable_weekdays = [r['weekday'] for r in cursor.fetchall()]

    cursor.execute('SELECT date, reason FROM employee_unavailable_dates WHERE employee_id = ? ORDER BY date', (employee_id,))
    unavailable_dates = [{'date': r['date'], 'reason': r['reason']} for r in cursor.fetchall()]

    cursor.execute('SELECT shift_type_id FROM employee_allowed_shift_types WHERE employee_id = ? ORDER BY shift_type_id', (employee_id,))
    allowed_shift_types = [r['shift_type_id'] for r in cursor.fetchall()]

    return {
        'id': employee_id,
        'name': row['name'],
        'email': row['email'],
        'active': bool(row['active']),
        'max_shifts_per_month': row['max_shifts_per_month'],
        'unavailable_weekdays': unavailable_weekdays,
        'unavailable_dates': unavailable_dates,
        'allowed_shift_types': allowed_shift_types,
    }


def replace_employee_constraints(connection, employee_id, data):
    cursor = connection.cursor()

    cursor.execute('DELETE FROM employee_unavailable_weekdays WHERE employee_id = ?', (employee_id,))
    for weekday in parse_int_list(data.get('unavailable_weekdays')):
        if not 0 <= weekday <= 6:
            raise ValueError('Wochentag muss zwischen 0 (Montag) und 6 (Sonntag) liegen')
        cursor.execute('INSERT INTO employee_unavailable_weekdays (employee_id, weekday) VALUES (?, ?)', (employee_id, weekday))

    cursor.execute('DELETE FROM employee_unavailable_dates WHERE employee_id = ?', (employee_id,))
    for entry in data.get('unavailable_dates') or []:
        iso_date = entry['date'] if isinstance(entry, dict) else entry
        reason = entry.get('reason') if isinstance(entry, dict) else None
        try:
            date.fromisoformat(iso_date)
        except (TypeError, ValueError):
            raise ValueError(f'Ungültiges Datum: {iso_date}')
        cursor.execute('INSERT INTO employee_unavailable_dates (employee_id, date, reason) VALUES (?, ?, ?)', (employee_id, iso_date, reason))

    cursor.execute('DELETE FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
    for shift_type_id in parse_int_list(data.get('allowed_shift_types')):
        cursor.execute('INSERT INTO employee_allowed_shift_types (employee_id, shift_type_id) VALUES (?, ?)', (employee_id, shift_type_id))


def serialize_shift_type(cursor, row):
    shift_type_id = row['id']
    cursor.execute('SELECT weekday, required_count FROM shift_requirements WHERE shift_type_id = ?', (shift_type_id,))
    by_weekday = {r['weekday']: r['required_count'] for r in cursor.fetchall()}
    requirements = [by_weekday.get(wd, 0) for wd in range(7)]

    return {
        'id': shift_type_id,
        'name': row['name'],
        'start_time': row['start_time'],
        'end_time': row['end_time'],
        'color': row['color'],
        'requirements': requirements,
    }


def replace_shift_requirements(connection, shift_type_id, requirements):
    if requirements is None:
        requirements = [0] * 7
    if len(requirements) != 7:
        raise ValueError('Der Bedarf muss genau 7 Einträge enthalten (Montag bis Sonntag)')

    cursor = connection.cursor()
    cursor.execute('DELETE FROM shift_requirements WHERE shift_type_id = ?', (shift_type_id,))
    for weekday, count in enumerate(requirements):
        count = int(count)
        if count < 0:
            raise ValueError('Der benötigte Personalbedarf darf nicht negativ sein')
        cursor.execute('INSERT INTO shift_requirements (shift_type_id, weekday, required_count) VALUES (?, ?, ?)', (shift_type_id, weekday, count))


# ---------- employees ----------

@app.route('/employees', methods=['GET'])
@login_required
def list_employees():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM employees ORDER BY name')
    employees = [serialize_employee(cursor, row) for row in cursor.fetchall()]
    connection.close()
    return jsonify(employees)


@app.route('/employees', methods=['POST'])
@login_required
def create_employee():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'message': 'Name ist erforderlich'}), 400

    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO employees (name, email, active, max_shifts_per_month) VALUES (?, ?, ?, ?)',
            (name, data.get('email'), 1 if data.get('active', True) else 0, data.get('max_shifts_per_month')),
        )
        employee_id = cursor.lastrowid
        replace_employee_constraints(connection, employee_id, data)
        connection.commit()
        cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
        employee = serialize_employee(cursor, cursor.fetchone())
    except ValueError as e:
        connection.close()
        return jsonify({'message': str(e)}), 400
    connection.close()
    return jsonify(employee), 201


@app.route('/employees/<int:employee_id>', methods=['GET'])
@login_required
def get_employee(employee_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    row = cursor.fetchone()
    if not row:
        connection.close()
        return jsonify({'message': 'Mitarbeiter nicht gefunden'}), 404
    employee = serialize_employee(cursor, row)
    connection.close()
    return jsonify(employee)


@app.route('/employees/<int:employee_id>', methods=['PUT'])
@login_required
def update_employee(employee_id):
    data = request.get_json(silent=True) or {}
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    if not cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Mitarbeiter nicht gefunden'}), 404

    name = (data.get('name') or '').strip()
    if not name:
        connection.close()
        return jsonify({'message': 'Name ist erforderlich'}), 400

    try:
        cursor.execute(
            'UPDATE employees SET name = ?, email = ?, active = ?, max_shifts_per_month = ? WHERE id = ?',
            (name, data.get('email'), 1 if data.get('active', True) else 0, data.get('max_shifts_per_month'), employee_id),
        )
        replace_employee_constraints(connection, employee_id, data)
        connection.commit()
        cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
        employee = serialize_employee(cursor, cursor.fetchone())
    except ValueError as e:
        connection.close()
        return jsonify({'message': str(e)}), 400
    connection.close()
    return jsonify(employee)


@app.route('/employees/<int:employee_id>', methods=['DELETE'])
@login_required
def delete_employee(employee_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM employees WHERE id = ?', (employee_id,))
    if not cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Mitarbeiter nicht gefunden'}), 404
    cursor.execute('DELETE FROM employees WHERE id = ?', (employee_id,))
    connection.commit()
    connection.close()
    return jsonify({'message': 'Mitarbeiter gelöscht'}), 200


# ---------- shift types ----------

@app.route('/shift-types', methods=['GET'])
@login_required
def list_shift_types():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_types ORDER BY start_time')
    shift_types = [serialize_shift_type(cursor, row) for row in cursor.fetchall()]
    connection.close()
    return jsonify(shift_types)


@app.route('/shift-types', methods=['POST'])
@login_required
def create_shift_type():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    if not name or not start_time or not end_time:
        return jsonify({'message': 'Name, Beginn und Ende sind erforderlich'}), 400

    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO shift_types (name, start_time, end_time, color) VALUES (?, ?, ?, ?)',
            (name, start_time, end_time, data.get('color') or '#0d9488'),
        )
        shift_type_id = cursor.lastrowid
        replace_shift_requirements(connection, shift_type_id, data.get('requirements'))
        connection.commit()
        cursor.execute('SELECT * FROM shift_types WHERE id = ?', (shift_type_id,))
        shift_type = serialize_shift_type(cursor, cursor.fetchone())
    except ValueError as e:
        connection.close()
        return jsonify({'message': str(e)}), 400
    connection.close()
    return jsonify(shift_type), 201


@app.route('/shift-types/<int:shift_type_id>', methods=['PUT'])
@login_required
def update_shift_type(shift_type_id):
    data = request.get_json(silent=True) or {}
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_types WHERE id = ?', (shift_type_id,))
    if not cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Schichtart nicht gefunden'}), 404

    name = (data.get('name') or '').strip()
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    if not name or not start_time or not end_time:
        connection.close()
        return jsonify({'message': 'Name, Beginn und Ende sind erforderlich'}), 400

    try:
        cursor.execute(
            'UPDATE shift_types SET name = ?, start_time = ?, end_time = ?, color = ? WHERE id = ?',
            (name, start_time, end_time, data.get('color') or '#0d9488', shift_type_id),
        )
        replace_shift_requirements(connection, shift_type_id, data.get('requirements'))
        connection.commit()
        cursor.execute('SELECT * FROM shift_types WHERE id = ?', (shift_type_id,))
        shift_type = serialize_shift_type(cursor, cursor.fetchone())
    except ValueError as e:
        connection.close()
        return jsonify({'message': str(e)}), 400
    connection.close()
    return jsonify(shift_type)


@app.route('/shift-types/<int:shift_type_id>', methods=['DELETE'])
@login_required
def delete_shift_type(shift_type_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM shift_types WHERE id = ?', (shift_type_id,))
    if not cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Schichtart nicht gefunden'}), 404

    cursor.execute('SELECT COUNT(*) AS n FROM shift_assignments WHERE shift_type_id = ?', (shift_type_id,))
    if cursor.fetchone()['n'] > 0:
        connection.close()
        return jsonify({'message': 'Schichtart wird in einem bestehenden Plan verwendet und kann nicht gelöscht werden'}), 400

    cursor.execute('DELETE FROM shift_types WHERE id = ?', (shift_type_id,))
    connection.commit()
    connection.close()
    return jsonify({'message': 'Schichtart gelöscht'}), 200


# ---------- schedules ----------

def load_employees_for_scheduling(cursor):
    cursor.execute('SELECT * FROM employees WHERE active = 1')
    employees = []
    for row in cursor.fetchall():
        employee_id = row['id']
        cursor.execute('SELECT weekday FROM employee_unavailable_weekdays WHERE employee_id = ?', (employee_id,))
        unavailable_weekdays = {r['weekday'] for r in cursor.fetchall()}
        cursor.execute('SELECT date FROM employee_unavailable_dates WHERE employee_id = ?', (employee_id,))
        unavailable_dates = {r['date'] for r in cursor.fetchall()}
        cursor.execute('SELECT shift_type_id FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
        allowed = {r['shift_type_id'] for r in cursor.fetchall()}
        employees.append({
            'id': employee_id,
            'max_shifts_per_month': row['max_shifts_per_month'],
            'unavailable_weekdays': unavailable_weekdays,
            'unavailable_dates': unavailable_dates,
            'allowed_shift_types': allowed if allowed else None,
        })
    return employees


def load_shift_types_for_scheduling(cursor):
    cursor.execute('SELECT * FROM shift_types')
    shift_types = []
    for row in cursor.fetchall():
        cursor.execute('SELECT weekday, required_count FROM shift_requirements WHERE shift_type_id = ?', (row['id'],))
        requirements = {r['weekday']: r['required_count'] for r in cursor.fetchall()}
        shift_types.append({'id': row['id'], 'requirements': requirements})
    return shift_types


def fetch_schedule(year, month):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM schedules WHERE year = ? AND month = ?', (year, month))
    schedule = cursor.fetchone()
    if not schedule:
        connection.close()
        return None

    cursor.execute('''
        SELECT sa.id, sa.date, sa.shift_type_id, sa.slot_index, sa.employee_id, sa.manually_edited,
               st.name AS shift_type_name, st.color AS shift_type_color, st.start_time, st.end_time,
               e.name AS employee_name
        FROM shift_assignments sa
        JOIN shift_types st ON st.id = sa.shift_type_id
        LEFT JOIN employees e ON e.id = sa.employee_id
        WHERE sa.schedule_id = ?
        ORDER BY sa.date, st.start_time, sa.slot_index
    ''', (schedule['id'],))
    assignments = []
    for row in cursor.fetchall():
        a = dict(row)
        a['manually_edited'] = bool(a['manually_edited'])
        assignments.append(a)

    cursor.execute('SELECT id, name FROM employees WHERE active = 1 ORDER BY name')
    active_employees = cursor.fetchall()

    connection.close()
    return {
        'id': schedule['id'],
        'year': schedule['year'],
        'month': schedule['month'],
        'status': schedule['status'],
        'unfilled_count': schedule['unfilled_count'],
        'generated_at': schedule['generated_at'],
        'assignments': assignments,
        'distribution': build_distribution(assignments, active_employees),
    }


def build_distribution(assignments, active_employees):
    """Shifts per employee for the month, recomputed from what is actually stored.

    Deriving this from the saved assignments rather than from the generator means
    it stays honest after HR reassigns or swaps shifts by hand.
    """
    totals = {row['id']: {'employee_id': row['id'], 'name': row['name'], 'total': 0, 'weekend': 0}
              for row in active_employees}

    for a in assignments:
        employee_id = a['employee_id']
        if employee_id is None:
            continue
        entry = totals.setdefault(
            employee_id,
            # An employee who was deactivated after the plan was generated still
            # holds shifts in it, so they belong in the distribution.
            {'employee_id': employee_id, 'name': a['employee_name'] or f'#{employee_id}', 'total': 0, 'weekend': 0},
        )
        entry['total'] += 1
        if date.fromisoformat(a['date']).weekday() >= 5:
            entry['weekend'] += 1

    rows = sorted(totals.values(), key=lambda r: (-r['total'], r['name']))
    counts = [r['total'] for r in rows]
    weekend_counts = [r['weekend'] for r in rows]

    return {
        'per_employee': rows,
        'spread': (max(counts) - min(counts)) if counts else 0,
        'weekend_spread': (max(weekend_counts) - min(weekend_counts)) if weekend_counts else 0,
    }


@app.route('/schedules/generate', methods=['POST'])
@login_required
def generate_schedule_route():
    data = request.get_json(silent=True) or {}
    try:
        year = int(data['year'])
        month = int(data['month'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'message': 'Jahr und Monat sind als Zahl erforderlich'}), 400
    if not 1 <= month <= 12:
        return jsonify({'message': 'Monat muss zwischen 1 und 12 liegen'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    shift_types = load_shift_types_for_scheduling(cursor)
    if not shift_types:
        connection.close()
        return jsonify({'message': 'Bitte zuerst mindestens eine Schichtart anlegen'}), 400

    employees = load_employees_for_scheduling(cursor)

    try:
        result = generate_schedule(year, month, employees, shift_types)
    except ValueError:
        connection.close()
        return jsonify({'message': 'Ungültiges Jahr oder Monat'}), 400

    cursor.execute('SELECT id FROM schedules WHERE year = ? AND month = ?', (year, month))
    existing = cursor.fetchone()
    if existing:
        schedule_id = existing['id']
        cursor.execute('DELETE FROM shift_assignments WHERE schedule_id = ?', (schedule_id,))
        cursor.execute(
            "UPDATE schedules SET status = 'generated', unfilled_count = ?, generated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (result['unfilled_count'], schedule_id),
        )
    else:
        cursor.execute(
            "INSERT INTO schedules (year, month, status, unfilled_count, generated_at) VALUES (?, ?, 'generated', ?, CURRENT_TIMESTAMP)",
            (year, month, result['unfilled_count']),
        )
        schedule_id = cursor.lastrowid

    for a in result['assignments']:
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, employee_id) VALUES (?, ?, ?, ?, ?)',
            (schedule_id, a['date'], a['shift_type_id'], a['slot_index'], a['employee_id']),
        )

    connection.commit()
    connection.close()
    return jsonify(fetch_schedule(year, month)), 201


@app.route('/schedules/<int:year>/<int:month>', methods=['GET'])
@login_required
def get_schedule(year, month):
    schedule = fetch_schedule(year, month)
    if not schedule:
        return jsonify({'message': 'Für diesen Monat wurde noch kein Plan generiert'}), 404
    return jsonify(schedule)


@app.route('/schedules/<int:year>/<int:month>', methods=['DELETE'])
@login_required
def delete_schedule(year, month):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM schedules WHERE year = ? AND month = ?', (year, month))
    row = cursor.fetchone()
    if not row:
        connection.close()
        return jsonify({'message': 'Für diesen Monat wurde kein Plan gefunden'}), 404
    cursor.execute('DELETE FROM schedules WHERE id = ?', (row['id'],))
    connection.commit()
    connection.close()
    return jsonify({'message': 'Plan gelöscht'}), 200


# ---------- manual editing (reassign / swap) ----------

def constraint_warnings(cursor, employee_id, assignment_date, shift_type_id, schedule_id, exclude_assignment_id=None):
    if employee_id is None:
        return []
    warnings = []
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    employee = cursor.fetchone()
    if not employee:
        return ['Mitarbeiter nicht gefunden']

    weekday = date.fromisoformat(assignment_date).weekday()
    cursor.execute('SELECT 1 FROM employee_unavailable_weekdays WHERE employee_id = ? AND weekday = ?', (employee_id, weekday))
    if cursor.fetchone():
        warnings.append(f'{employee["name"]} arbeitet normalerweise nicht {WEEKDAYS[weekday]}s')

    cursor.execute('SELECT 1 FROM employee_unavailable_dates WHERE employee_id = ? AND date = ?', (employee_id, assignment_date))
    if cursor.fetchone():
        warnings.append(f'{employee["name"]} ist am {assignment_date} als nicht verfügbar eingetragen')

    cursor.execute('SELECT 1 FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
    if cursor.fetchone():
        cursor.execute('SELECT 1 FROM employee_allowed_shift_types WHERE employee_id = ? AND shift_type_id = ?', (employee_id, shift_type_id))
        if not cursor.fetchone():
            warnings.append(f'{employee["name"]} ist normalerweise auf andere Schichtarten beschränkt')

    query = 'SELECT 1 FROM shift_assignments WHERE date = ? AND employee_id = ?'
    params = [assignment_date, employee_id]
    if exclude_assignment_id is not None:
        query += ' AND id != ?'
        params.append(exclude_assignment_id)
    cursor.execute(query, params)
    if cursor.fetchone():
        warnings.append(f'{employee["name"]} ist an diesem Tag bereits einer anderen Schicht zugeteilt')

    if employee['max_shifts_per_month'] is not None:
        cursor.execute(
            'SELECT COUNT(*) AS n FROM shift_assignments WHERE employee_id = ? AND schedule_id = ? AND id != ?',
            (employee_id, schedule_id, exclude_assignment_id or -1),
        )
        if cursor.fetchone()['n'] >= employee['max_shifts_per_month']:
            warnings.append(f'{employee["name"]} hat das monatliche Limit von {employee["max_shifts_per_month"]} Schichten bereits erreicht')

    return warnings


def refresh_unfilled_count(cursor, schedule_id):
    cursor.execute('SELECT COUNT(*) AS n FROM shift_assignments WHERE schedule_id = ? AND employee_id IS NULL', (schedule_id,))
    unfilled_count = cursor.fetchone()['n']
    cursor.execute('UPDATE schedules SET unfilled_count = ? WHERE id = ?', (unfilled_count, schedule_id))


@app.route('/assignments/<int:assignment_id>', methods=['PUT'])
@login_required
def update_assignment(assignment_id):
    data = request.get_json(silent=True) or {}
    employee_id = data.get('employee_id')

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_assignments WHERE id = ?', (assignment_id,))
    assignment = cursor.fetchone()
    if not assignment:
        connection.close()
        return jsonify({'message': 'Zuweisung nicht gefunden'}), 404

    if employee_id is not None:
        cursor.execute('SELECT id FROM employees WHERE id = ?', (employee_id,))
        if not cursor.fetchone():
            connection.close()
            return jsonify({'message': 'Mitarbeiter nicht gefunden'}), 404

    warnings = constraint_warnings(
        cursor, employee_id, assignment['date'], assignment['shift_type_id'], assignment['schedule_id'],
        exclude_assignment_id=assignment_id,
    )

    cursor.execute('UPDATE shift_assignments SET employee_id = ?, manually_edited = 1 WHERE id = ?', (employee_id, assignment_id))
    refresh_unfilled_count(cursor, assignment['schedule_id'])

    connection.commit()
    connection.close()
    return jsonify({'message': 'Zuweisung aktualisiert', 'warnings': warnings})


@app.route('/assignments/swap', methods=['POST'])
@login_required
def swap_assignments():
    data = request.get_json(silent=True) or {}
    id_a = data.get('assignment_id_a')
    id_b = data.get('assignment_id_b')
    if not id_a or not id_b or id_a == id_b:
        return jsonify({'message': 'Zwei unterschiedliche Zuweisungs-IDs sind erforderlich'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_assignments WHERE id IN (?, ?)', (id_a, id_b))
    rows = {row['id']: row for row in cursor.fetchall()}
    if id_a not in rows or id_b not in rows:
        connection.close()
        return jsonify({'message': 'Zuweisung nicht gefunden'}), 404

    a, b = rows[id_a], rows[id_b]
    if a['schedule_id'] != b['schedule_id']:
        connection.close()
        return jsonify({'message': 'Schichten können nur innerhalb desselben Plans getauscht werden'}), 400

    cursor.execute('UPDATE shift_assignments SET employee_id = ?, manually_edited = 1 WHERE id = ?', (b['employee_id'], a['id']))
    cursor.execute('UPDATE shift_assignments SET employee_id = ?, manually_edited = 1 WHERE id = ?', (a['employee_id'], b['id']))

    warnings = []
    warnings += constraint_warnings(cursor, b['employee_id'], a['date'], a['shift_type_id'], a['schedule_id'], exclude_assignment_id=a['id'])
    warnings += constraint_warnings(cursor, a['employee_id'], b['date'], b['shift_type_id'], b['schedule_id'], exclude_assignment_id=b['id'])

    refresh_unfilled_count(cursor, a['schedule_id'])

    connection.commit()
    connection.close()
    return jsonify({'message': 'Schichten getauscht', 'warnings': warnings})


@app.route('/')
def index():
    return jsonify({'message': 'Schichtplan-Tool API', 'status': 'ok'})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
