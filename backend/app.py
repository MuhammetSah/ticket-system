import os
import sqlite3
from flask import Flask, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

app = Flask(__name__) 
app.secret_key = 'project-portfolio'

if os.environ.get('FLASK_ENV') == 'production':
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True

CORS(app, supports_credentials=True, origins=["https://ticket-system-two-ivory.vercel.app", "http://localhost:5173"])

connection = sqlite3.connect('tickets.db')
cursor = connection.cursor()

# CREATE TABLE for SQL 
# TABLE for users
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        hash TEXT NOT NULL
    )
''')

# TABLE for tickets
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tickets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        contact_name TEXT NOT NULL,
        contact_email TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        solution TEXT,
        status TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
''')

connection.commit()
connection.close()

# Get all tickets
@app.route('/tickets', methods=['GET'])
def get_tickets():
    connection = sqlite3.connect('tickets.db') # Connect to the database
    connection.row_factory = sqlite3.Row # Set the row factory to sqlite3.Row to access columns by name
    cursor = connection.cursor()  # Create a cursor object to execute SQL queries
    cursor.execute('SELECT * FROM tickets') # Query to select all tickets
    tickets = cursor.fetchall() # Fetch all tickets from the database
    connection.close() # Close the database connection
    return jsonify([dict(ticket) for ticket in tickets]) # Convert the tickets to a list of dictionaries and return as JSON

# Get a specific ticket by ID
@app.route('/tickets/<int:ticket_id>', methods=['GET'])
def get_ticket(ticket_id):
    connection = sqlite3.connect('tickets.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)) # Query to select the ticket with the given ID
    ticket = cursor.fetchone() # Fetch the ticket from the database
    connection.close()
    if ticket:
        return jsonify(dict(ticket)) # Convert the ticket to a dictionary and return as JSON
    else:
        return jsonify({'message': 'Ticket not found'}), 404 # Return a 404 Not Found response with an error message if the ticket does not exist
    

# Create a new ticket
@app.route('/tickets', methods=['POST'])
def create_ticket():
    user_id = session.get('user_id') # Get the user_id from the session to check if the user is logged in
    if not user_id: # If the user is not logged in, return a 401 Unauthorized response
        return jsonify({'message': 'User not logged in'}), 401

    data = request.get_json() # Get the JSON data from the request body
    contact_name = data.get('contact_name') # Get the contact name from the JSON data
    contact_email = data.get('contact_email') # Get the contact email from the JSON data
    title = data.get('title') # Get the title of the ticket from the JSON data
    description = data.get('description') # Get the description of the ticket from the JSON data
    connection = sqlite3.connect('tickets.db') 
    cursor = connection.cursor() 
    cursor.execute('INSERT INTO tickets (user_id, contact_name, contact_email, title, description, status) VALUES (?, ?, ?, ?, ?, ?)', (user_id, contact_name, contact_email, title, description, 'open'))
    connection.commit()
    connection.close()
    return jsonify({'message': 'Ticket created successfully'}), 201 # Return a 201 Created response with a success message

# User registration
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    connection = sqlite3.connect('tickets.db')
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    existing_user = cursor.fetchone()
    if existing_user:
        connection.close()
        return jsonify({'message': 'Username already exists'}), 400

    hashed_password = generate_password_hash(password)
    cursor.execute('INSERT INTO users (username, hash) VALUES (?, ?)', (username, hashed_password))
    connection.commit()

    session['user_id'] = cursor.lastrowid

    connection.close()
    return jsonify({'message': 'User created successfully'}), 201

# User login
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    connection = sqlite3.connect('tickets.db')
    connection.row_factory = sqlite3.Row # Set the row factory to sqlite3.Row to access columns by name
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,)) # Query to select the user with the given username
    existing_user = cursor.fetchone() 
    if not existing_user: # If the user does not exist, return a 401 Unauthorized response with an error message
        connection.close()
        return jsonify({'message': 'Invalid username or password'}), 401

    if not check_password_hash(existing_user['hash'], password): # If the password does not match the hashed password in the database, return a 401 Unauthorized response with an error message
        connection.close()
        return jsonify({'message': 'Invalid username or password'}), 401
    
    session['user_id'] = existing_user['id'] # Store the user_id in the session to keep the user logged in
    connection.close()
    return jsonify({'message': 'Login successful'}), 200 

# User logout
@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None) # Remove the user_id from the session to log the user out
    return jsonify({'message': 'Logout successful'}), 200

# Change ticket status
@app.route('/tickets/<int:ticket_id>', methods=['PATCH'])
def update_ticket(ticket_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'User not logged in'}), 401

    connection = sqlite3.connect('tickets.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()

    if not ticket:
        connection.close()
        return jsonify({'message': 'Ticket not found'}), 404

    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    current_user = cursor.fetchone()

    if not current_user:
            connection.close()
            return jsonify({'message': 'User not found'}), 404

    data = request.get_json()

    if 'status' in data and ticket['user_id'] != user_id and current_user['role'] != 'admin':
        connection.close()
        return jsonify({'message': 'Not authorized to change status'}), 403

    if 'solution' in data and current_user['role'] != 'admin':
        connection.close()
        return jsonify({'message': 'Only admin can set a solution'}), 403

    status = data.get('status', ticket['status'])
    solution = data.get('solution', ticket['solution'])

    cursor.execute('UPDATE tickets SET status = ?, solution = ? WHERE id = ?', (status, solution, ticket_id))
    connection.commit()
    connection.close()
    return jsonify({'message': 'Ticket updated successfully'}), 200

@app.route('/me', methods=['GET'])
def me():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'Not logged in'}), 401

    connection = sqlite3.connect('tickets.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    connection.close()

    return jsonify({'user_id': user['id'], 'username': user['username'], 'role': user['role']}), 200

# Delete a ticket
@app.route('/tickets/<int:ticket_id>', methods=['DELETE'])
def delete_ticket(ticket_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'User not logged in'}), 401

    connection = sqlite3.connect('tickets.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()

    if not ticket: 
        connection.close()
        return jsonify({'message': 'Ticket not found'}), 404


    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    current_user = cursor.fetchone()

    if not current_user:
        connection.close()
        return jsonify({'message': 'User not found'}), 404

    if ticket['user_id'] != user_id and current_user['role'] != 'admin':
        connection.close()
        return jsonify({'message': 'Not authorized to delete this ticket'}), 403

    cursor.execute('DELETE FROM tickets WHERE id = ?', (ticket_id,))
    connection.commit()
    connection.close()
    return jsonify({'message': 'Ticket deleted successfully'}), 200


if __name__ == '__main__':
    app.run(debug=True)
