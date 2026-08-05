import hashlib
import os
import secrets
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, g, jsonify, request, session
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

import mailer
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

HR_ROLE = 'hr'
EMPLOYEE_ROLE = 'employee'


def current_user_id():
    return session.get('user_id')


def load_current_user():
    """The signed-in account, or None. Read fresh so a role change takes effect."""
    user_id = current_user_id()
    if not user_id:
        return None

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT id, username, role, employee_id FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    connection.close()
    return dict(user) if user else None


def is_hr(user):
    return bool(user) and user['role'] == HR_ROLE


def login_required(view):
    """Any signed-in account may pass: HR, or an employee reading the plan."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = load_current_user()
        if not user:
            return jsonify({'message': 'Nicht angemeldet'}), 401
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def hr_required(view):
    """Anything that changes data is HR-only.

    Employee accounts are strictly read-only: they may look at the published
    schedule and nothing else. Enforced here rather than only by hiding buttons,
    because hidden buttons stop nobody from calling the API directly.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = load_current_user()
        if not user:
            return jsonify({'message': 'Nicht angemeldet'}), 401
        if not is_hr(user):
            return jsonify({'message': 'Nur die Personalabteilung hat darauf Zugriff'}), 403
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def count_users(cursor):
    cursor.execute('SELECT COUNT(*) AS n FROM users')
    return cursor.fetchone()['n']


# ---------- password invitations ----------

INVITATION_VALID_DAYS = 7
MIN_PASSWORD_LENGTH = 8


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_invitation(cursor, user_id):
    """Replaces any open invitation, so a resend invalidates the previous link."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=INVITATION_VALID_DAYS)
    cursor.execute('DELETE FROM password_invitations WHERE user_id = ?', (user_id,))
    cursor.execute(
        'INSERT INTO password_invitations (user_id, token_hash, expires_at) VALUES (?, ?, ?)',
        (user_id, hash_token(token), expires_at.isoformat(timespec='seconds')),
    )
    return token


def load_invitation(cursor, token):
    """The account a token belongs to, or None if unknown or expired."""
    cursor.execute('''
        SELECT i.id, i.user_id, i.expires_at, u.username
        FROM password_invitations i
        JOIN users u ON u.id = i.user_id
        WHERE i.token_hash = ?
    ''', (hash_token(token),))
    invitation = cursor.fetchone()
    if not invitation:
        return None
    if datetime.fromisoformat(invitation['expires_at']) < datetime.utcnow():
        return None
    return dict(invitation)


def employee_email(cursor, employee_id):
    cursor.execute('SELECT name, email FROM employees WHERE id = ?', (employee_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def looks_like_email(value):
    if not isinstance(value, str):
        return False
    local, at, domain = value.strip().partition('@')
    return bool(local) and bool(at) and '.' in domain and not domain.startswith('.')


def invitation_recipient(cursor, account):
    """Where this account's invitation goes, and who to address it to.

    An employee account takes the address from its roster entry, so it never
    drifts from the record HR maintains; an HR account has no roster entry and
    carries its own.
    """
    if account['role'] == EMPLOYEE_ROLE:
        employee = employee_email(cursor, account['employee_id']) if account['employee_id'] else None
        if employee and employee['email']:
            return employee['email'], employee['name']
        return None, None
    if account['email']:
        return account['email'], account['username']
    return None, None


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username:
        return jsonify({'message': 'Benutzername ist erforderlich'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    first_account = count_users(cursor) == 0
    creator = load_current_user()

    # The first account sets the tool up and is always HR - someone has to be
    # able to administer it. After that only HR may create accounts, so nobody
    # can sign themselves up and read the roster.
    if not first_account and not is_hr(creator):
        connection.close()
        message = ('Nur die Personalabteilung darf Konten anlegen' if creator
                   else 'Neue Konten kann nur ein angemeldeter Benutzer anlegen')
        return jsonify({'message': message}), 403

    role = HR_ROLE if first_account else (data.get('role') or HR_ROLE)
    if role not in (HR_ROLE, EMPLOYEE_ROLE):
        connection.close()
        return jsonify({'message': 'Unbekannte Rolle'}), 400

    # Every account except the very first is created by somebody else, so it is
    # invited: the person picks a password nobody else ever sees. The bootstrap
    # account is the exception - there is no one to invite it, so it sets its
    # own password on the spot.
    invited = not first_account

    employee_id = data.get('employee_id') if role == EMPLOYEE_ROLE else None
    account_email = (data.get('email') or '').strip() or None
    recipient_email = None
    recipient_name = None

    if role == EMPLOYEE_ROLE:
        # An employee account shows that person's own shifts, so it is useless
        # until it knows whose shifts those are.
        if employee_id is None:
            connection.close()
            return jsonify({'message': 'Ein Mitarbeiter-Konto muss mit einem Mitarbeiter verknüpft werden'}), 400
        employee = employee_email(cursor, employee_id)
        if not employee:
            connection.close()
            return jsonify({'message': 'Mitarbeiter nicht gefunden'}), 404
        # The invitation is the only way this account gets a password, so
        # without an address there is nowhere to send it.
        if not employee['email']:
            connection.close()
            return jsonify({'message':
                            f'{employee["name"]} hat keine E-Mail-Adresse. '
                            'Bitte zuerst beim Mitarbeiter hinterlegen.'}), 400
        # Taken from the roster entry rather than stored again on the account.
        account_email = None
        recipient_email, recipient_name = employee['email'], employee['name']
    elif invited:
        if not account_email:
            connection.close()
            return jsonify({'message': 'E-Mail-Adresse ist erforderlich, um die Einladung zu senden'}), 400
        if not looks_like_email(account_email):
            connection.close()
            return jsonify({'message': 'Bitte eine gültige E-Mail-Adresse angeben'}), 400
        recipient_email, recipient_name = account_email, username
    else:
        # The bootstrap account. An address is optional here, but storing one
        # means this account can later be re-invited if the password is lost.
        if account_email and not looks_like_email(account_email):
            connection.close()
            return jsonify({'message': 'Bitte eine gültige E-Mail-Adresse angeben'}), 400
        if not password:
            connection.close()
            return jsonify({'message': 'Passwort ist erforderlich'}), 400
        if len(password) < MIN_PASSWORD_LENGTH:
            connection.close()
            return jsonify({'message': f'Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein'}), 400

    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Benutzername ist bereits vergeben'}), 400

    # An empty hash marks an account that cannot be signed into yet. Invited
    # accounts start that way, so nobody - the creator included - ever knows the
    # password that ends up on them.
    password_hash = '' if invited else generate_password_hash(password)
    cursor.execute(
        'INSERT INTO users (username, hash, role, employee_id, email) VALUES (?, ?, ?, ?, ?)',
        (username, password_hash, role, employee_id, account_email),
    )
    user_id = cursor.lastrowid

    invitation_sent = None
    if invited:
        token = issue_invitation(cursor, user_id)
        connection.commit()
        connection.close()
        invitation_sent = mailer.send_invitation(
            recipient_email, username, token, INVITATION_VALID_DAYS)
    else:
        connection.commit()
        connection.close()

    # Signing in the very first user saves them an immediate second step; HR
    # adding a colleague must stay logged in as themselves.
    if first_account:
        session['user_id'] = user_id

    return jsonify({
        'id': user_id,
        'username': username,
        'role': role,
        'employee_id': employee_id,
        'invitation_email': recipient_email,
        'invitation_sent': invitation_sent,
    }), 201


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

    # An invited account has no password yet. Saying so is safe - the invitation
    # went to that person's mailbox, not to whoever is guessing here - and it is
    # far more useful than "wrong password" to someone who never set one.
    if user and not user['hash']:
        return jsonify({'message':
                        'Für dieses Konto wurde noch kein Passwort vergeben. '
                        'Bitte den Link aus der Einladungs-E-Mail verwenden.'}), 403

    # Same message either way, so the response cannot be used to find out which
    # usernames exist.
    if not user or not check_password_hash(user['hash'], password):
        return jsonify({'message': 'Benutzername oder Passwort ist falsch'}), 401

    session.clear()
    session['user_id'] = user['id']
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'employee_id': user['employee_id'],
    }), 200


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Abgemeldet'}), 200


@app.route('/invitations/<token>', methods=['GET'])
def check_invitation(token):
    """Public: does this link still work? Used to greet the invitee by name."""
    connection = get_db_connection()
    cursor = connection.cursor()
    invitation = load_invitation(cursor, token)
    connection.close()

    if not invitation:
        return jsonify({'message': 'Dieser Link ist ungültig oder abgelaufen'}), 404
    return jsonify({'username': invitation['username']}), 200


@app.route('/invitations/<token>', methods=['POST'])
def redeem_invitation(token):
    """Public: the invitee sets their own password, which nobody else has seen."""
    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''

    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'message': f'Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    invitation = load_invitation(cursor, token)
    if not invitation:
        connection.close()
        return jsonify({'message': 'Dieser Link ist ungültig oder abgelaufen'}), 404

    cursor.execute('UPDATE users SET hash = ? WHERE id = ?',
                   (generate_password_hash(password), invitation['user_id']))
    # Single use: the link stops working the moment it has been redeemed.
    cursor.execute('DELETE FROM password_invitations WHERE id = ?', (invitation['id'],))
    connection.commit()
    connection.close()

    return jsonify({'username': invitation['username'],
                    'message': 'Passwort gesetzt. Sie können sich jetzt anmelden.'}), 200


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

    cursor.execute('SELECT id, username, role, employee_id FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    connection.close()

    if not user:
        # The account was deleted while the cookie was still around.
        session.clear()
        return jsonify({'message': 'Nicht angemeldet', 'setup_required': setup_required}), 401

    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'employee_id': user['employee_id'],
        'setup_required': False,
    }), 200


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
@hr_required
def list_employees():
    # HR-only: an employee account is shown its own shifts, which already carry
    # the shift name and hours, so it never needs the roster - and the roster is
    # colleagues' personal data.
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM employees ORDER BY name')
    employees = [serialize_employee(cursor, row) for row in cursor.fetchall()]
    connection.close()
    return jsonify(employees)


@app.route('/employees', methods=['POST'])
@hr_required
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
@hr_required
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
@hr_required
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
@hr_required
def delete_employee(employee_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM employees WHERE id = ?', (employee_id,))
    if not cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Mitarbeiter nicht gefunden'}), 404

    # Deleting the roster entry out from under a login would leave an account
    # that still works but can never show anything, so the account goes first.
    cursor.execute('SELECT username FROM users WHERE employee_id = ?', (employee_id,))
    linked = [row['username'] for row in cursor.fetchall()]
    if linked:
        connection.close()
        return jsonify({'message':
                        'Zuerst das verknüpfte Konto löschen: ' + ', '.join(linked)}), 400

    cursor.execute('DELETE FROM employees WHERE id = ?', (employee_id,))
    connection.commit()
    connection.close()
    return jsonify({'message': 'Mitarbeiter gelöscht'}), 200


# ---------- accounts ----------

@app.route('/accounts', methods=['GET'])
@hr_required
def list_accounts():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.role, u.employee_id, u.created_at,
               e.name AS employee_name,
               -- An employee's address lives on the roster entry, HR's on the
               -- account itself; the UI just needs to know where mail would go.
               COALESCE(e.email, u.email) AS contact_email,
               (u.hash != '') AS password_set,
               (i.id IS NOT NULL) AS invitation_pending
        FROM users u
        LEFT JOIN employees e ON e.id = u.employee_id
        LEFT JOIN password_invitations i ON i.user_id = u.id
        ORDER BY u.role, u.username
    ''')
    accounts = []
    for row in cursor.fetchall():
        account = dict(row)
        account['password_set'] = bool(account['password_set'])
        account['invitation_pending'] = bool(account['invitation_pending'])
        accounts.append(account)
    connection.close()
    return jsonify(accounts)


@app.route('/accounts/<int:account_id>/invitation', methods=['POST'])
@hr_required
def resend_invitation(account_id):
    """Send a fresh invitation, e.g. when the first one expired or went astray."""
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT id, username, role, employee_id, email, hash FROM users WHERE id = ?', (account_id,))
    account = cursor.fetchone()
    if not account:
        connection.close()
        return jsonify({'message': 'Konto nicht gefunden'}), 404

    recipient_email, _ = invitation_recipient(cursor, account)
    if not recipient_email:
        connection.close()
        return jsonify({'message': 'Für dieses Konto ist keine E-Mail-Adresse hinterlegt'}), 400

    token = issue_invitation(cursor, account_id)
    # Re-inviting also revokes the current password, so a forgotten one can be
    # replaced without HR ever setting it.
    cursor.execute("UPDATE users SET hash = '' WHERE id = ?", (account_id,))
    connection.commit()
    connection.close()

    sent = mailer.send_invitation(recipient_email, account['username'], token, INVITATION_VALID_DAYS)
    return jsonify({
        'message': f'Einladung an {recipient_email} gesendet' if sent
                   else f'Einladung für {recipient_email} erstellt (kein SMTP konfiguriert - Link steht im Server-Log)',
        'invitation_sent': sent,
    }), 200


@app.route('/accounts/<int:account_id>', methods=['DELETE'])
@hr_required
def delete_account(account_id):
    if account_id == g.user['id']:
        # Deleting the account you are signed in with would lock you out mid-session.
        return jsonify({'message': 'Das eigene Konto kann nicht gelöscht werden'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT id, username, role FROM users WHERE id = ?', (account_id,))
    account = cursor.fetchone()
    if not account:
        connection.close()
        return jsonify({'message': 'Konto nicht gefunden'}), 404

    if account['role'] == HR_ROLE:
        cursor.execute('SELECT COUNT(*) AS n FROM users WHERE role = ?', (HR_ROLE,))
        if cursor.fetchone()['n'] <= 1:
            connection.close()
            # Without an HR account nobody could administer the tool again.
            return jsonify({'message': 'Das letzte Personal-Konto kann nicht gelöscht werden'}), 400

    cursor.execute('DELETE FROM users WHERE id = ?', (account_id,))
    connection.commit()
    connection.close()
    return jsonify({'message': f'Konto {account["username"]} gelöscht'}), 200


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
@hr_required
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
@hr_required
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
@hr_required
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

    cursor.execute(
        'SELECT date, shift_type_id, start_time, end_time FROM shift_time_overrides WHERE schedule_id = ?',
        (schedule['id'],),
    )
    overrides = {(r['date'], r['shift_type_id']): dict(r) for r in cursor.fetchall()}

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
        # The shift type's hours are the default; a per-date override wins.
        override = overrides.get((a['date'], a['shift_type_id']))
        a['default_start_time'] = a['start_time']
        a['default_end_time'] = a['end_time']
        a['time_overridden'] = override is not None
        if override:
            a['start_time'] = override['start_time']
            a['end_time'] = override['end_time']
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
@hr_required
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

    if is_hr(g.user):
        schedule['scope'] = 'all'
        return jsonify(schedule)

    # An employee sees their own shifts and nothing else: not colleagues'
    # shifts, not gaps in the plan, and not the workload comparison, which is
    # a management view. Filtering happens here rather than in the browser so
    # the rest is never sent in the first place.
    linked_employee_id = g.user['employee_id']
    schedule['assignments'] = [
        a for a in schedule['assignments'] if a['employee_id'] == linked_employee_id
    ]
    schedule.pop('distribution', None)
    schedule['scope'] = 'own'
    schedule['unfilled_count'] = 0
    schedule['linked_employee_id'] = linked_employee_id

    return jsonify(schedule)


@app.route('/schedules/<int:year>/<int:month>', methods=['DELETE'])
@hr_required
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


# ---------- day-level editing (times, extra places) ----------

TIME_FORMAT_HINT = 'Zeiten müssen im Format HH:MM angegeben werden'


def valid_time(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ':':
        return False
    hours, _, minutes = value.partition(':')
    return (hours.isdigit() and minutes.isdigit()
            and 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59)


def find_schedule_id(cursor, year, month):
    cursor.execute('SELECT id FROM schedules WHERE year = ? AND month = ?', (year, month))
    row = cursor.fetchone()
    return row['id'] if row else None


@app.route('/schedules/<int:year>/<int:month>/shift-times', methods=['PUT'])
@hr_required
def set_shift_times(year, month):
    """Change the hours a shift runs on one date only.

    Sending null times clears the override, putting that date back on the shift
    type's usual hours.
    """
    data = request.get_json(silent=True) or {}
    iso_date = data.get('date')
    shift_type_id = data.get('shift_type_id')
    start_time = data.get('start_time')
    end_time = data.get('end_time')

    try:
        date.fromisoformat(iso_date)
    except (TypeError, ValueError):
        return jsonify({'message': 'Ungültiges Datum'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    schedule_id = find_schedule_id(cursor, year, month)
    if not schedule_id:
        connection.close()
        return jsonify({'message': 'Für diesen Monat wurde kein Plan gefunden'}), 404

    cursor.execute('SELECT id FROM shift_types WHERE id = ?', (shift_type_id,))
    if not cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Schichtart nicht gefunden'}), 404

    if start_time is None and end_time is None:
        cursor.execute(
            'DELETE FROM shift_time_overrides WHERE schedule_id = ? AND date = ? AND shift_type_id = ?',
            (schedule_id, iso_date, shift_type_id),
        )
        connection.commit()
        connection.close()
        return jsonify({'message': 'Zeiten auf die Standardzeiten zurückgesetzt'}), 200

    if not valid_time(start_time) or not valid_time(end_time):
        connection.close()
        return jsonify({'message': TIME_FORMAT_HINT}), 400

    cursor.execute('''
        INSERT INTO shift_time_overrides (schedule_id, date, shift_type_id, start_time, end_time)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(schedule_id, date, shift_type_id)
        DO UPDATE SET start_time = excluded.start_time, end_time = excluded.end_time
    ''', (schedule_id, iso_date, shift_type_id, start_time, end_time))

    connection.commit()
    connection.close()
    return jsonify({'message': 'Zeiten für diesen Tag geändert'}), 200


@app.route('/schedules/<int:year>/<int:month>/slots', methods=['POST'])
@hr_required
def add_slot(year, month):
    """Add one more place to a shift on a single date, initially unassigned.

    The shift type's required headcount stays as it is - this is a one-off
    change to this date, not a change to what the shift normally needs.
    """
    data = request.get_json(silent=True) or {}
    iso_date = data.get('date')
    shift_type_id = data.get('shift_type_id')

    try:
        parsed = date.fromisoformat(iso_date)
    except (TypeError, ValueError):
        return jsonify({'message': 'Ungültiges Datum'}), 400
    if (parsed.year, parsed.month) != (year, month):
        return jsonify({'message': 'Das Datum liegt nicht in diesem Monat'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    schedule_id = find_schedule_id(cursor, year, month)
    if not schedule_id:
        connection.close()
        return jsonify({'message': 'Für diesen Monat wurde kein Plan gefunden'}), 404

    cursor.execute('SELECT id FROM shift_types WHERE id = ?', (shift_type_id,))
    if not cursor.fetchone():
        connection.close()
        return jsonify({'message': 'Schichtart nicht gefunden'}), 404

    cursor.execute(
        'SELECT COALESCE(MAX(slot_index), -1) AS highest FROM shift_assignments '
        'WHERE schedule_id = ? AND date = ? AND shift_type_id = ?',
        (schedule_id, iso_date, shift_type_id),
    )
    next_index = cursor.fetchone()['highest'] + 1

    cursor.execute(
        'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, employee_id, manually_edited) '
        'VALUES (?, ?, ?, ?, NULL, 1)',
        (schedule_id, iso_date, shift_type_id, next_index),
    )
    assignment_id = cursor.lastrowid
    refresh_unfilled_count(cursor, schedule_id)

    connection.commit()
    connection.close()
    return jsonify({'id': assignment_id, 'message': 'Platz hinzugefügt'}), 201


@app.route('/assignments/<int:assignment_id>', methods=['DELETE'])
@hr_required
def delete_assignment(assignment_id):
    """Remove a place from a shift on one date."""
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT schedule_id FROM shift_assignments WHERE id = ?', (assignment_id,))
    assignment = cursor.fetchone()
    if not assignment:
        connection.close()
        return jsonify({'message': 'Zuweisung nicht gefunden'}), 404

    cursor.execute('DELETE FROM shift_assignments WHERE id = ?', (assignment_id,))
    refresh_unfilled_count(cursor, assignment['schedule_id'])

    connection.commit()
    connection.close()
    return jsonify({'message': 'Platz entfernt'}), 200


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
@hr_required
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
@hr_required
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
