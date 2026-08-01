# Support Ticket System

A full-stack web application for managing support tickets, built with React (frontend) and Flask (backend). Users can register, create tickets with contact details, and track their status. An admin user can add solutions to tickets.

**Live Demo:** [ticket-system-two-ivory.vercel.app](https://ticket-system-two-ivory.vercel.app)

> Note: The backend runs on a free Render plan and "spins down" after inactivity. The first request after a period of inactivity can therefore take up to 50 seconds.

## Features

- **Authentication** – Registration and login with hashed passwords (Werkzeug) and session-based authentication
- **Ticket management** – Create, view, and inspect tickets in detail (title, description, contact info, status, creation date)
- **Role-based permissions**
  - The ticket creator can change its status (open/solved)
  - Only an admin user can add a solution to a ticket
- **Live updates** – The ticket list refreshes automatically after creating a new ticket, with no page reload required
- **Flash messages** – Success and error feedback for all key actions (login, registration, ticket creation, status changes)
- **Client-side routing** – Dedicated pages for login, registration, and individual ticket detail views (React Router)

## Tech Stack

**Frontend**
- React (with Vite)
- React Router

**Backend**
- Flask
- SQLite
- Flask-CORS
- Werkzeug (password hashing)

**Deployment**
- Frontend: Vercel
- Backend: Render

## Project Structure

```
ticket-system/
├── backend/
│   ├── app.py              # Flask app: routes, database setup
│   └── requirements.txt    # Python dependencies
└── frontend/
    └── src/
        ├── App.jsx          # Routing & navigation
        ├── Login.jsx
        ├── Register.jsx
        ├── CreateTicket.jsx
        ├── Tickets.jsx      # Ticket list
        ├── TicketDetail.jsx # Ticket detail view
        └── Flash.jsx        # Success/error messages
```

## Local Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Runs by default on `http://localhost:5000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs by default on `http://localhost:5173`.

Create a `.env` file in the `frontend` folder with:

```
VITE_API_URL=http://localhost:5000
```

## API Endpoints

| Method | Route              | Description                                          |
|--------|---------------------|-------------------------------------------------------|
| POST   | `/register`         | Register a new user (logs in automatically)           |
| POST   | `/login`             | Log in                                                 |
| POST   | `/logout`            | Log out                                                |
| GET    | `/me`                | Get the currently logged-in user                      |
| GET    | `/tickets`           | Get all tickets                                        |
| GET    | `/tickets/<id>`      | Get a single ticket                                    |
| POST   | `/tickets`           | Create a new ticket (login required)                   |
| PATCH  | `/tickets/<id>`      | Change status (creator/admin) or set solution (admin only) |

## About This Project

This project is part of my portfolio as I transition into web development. It serves as a practice project for full-stack development with authentication, role-based permissions, and REST APIs.
