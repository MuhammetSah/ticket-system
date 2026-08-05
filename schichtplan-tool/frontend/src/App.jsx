import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom'
import SchedulePage from './pages/SchedulePage'
import Employees from './pages/Employees'
import ShiftTypes from './pages/ShiftTypes'
import Login from './pages/Login'
import Register from './pages/Register'
import Flash from './Flash'
import { api, UnauthorizedError } from './api'
import './App.css'

function RequireAuth({ user, setupRequired, children }) {
  const location = useLocation()
  if (!user) {
    // On a brand new install there is nobody to log in as yet, so send the
    // first visitor to set up an account rather than to a login form.
    return (
      <Navigate
        to={setupRequired ? '/register' : '/login'}
        replace
        state={{ from: location.pathname }}
      />
    )
  }
  return children
}

function App() {
  const [flash, setFlash] = useState(null)
  const [user, setUser] = useState(null)
  const [setupRequired, setSetupRequired] = useState(false)
  const [checkingSession, setCheckingSession] = useState(true)

  // Restores an existing session on load, and detects a fresh install that has
  // no accounts yet so the first visit lands on setup instead of a login wall.
  useEffect(() => {
    let cancelled = false
    api.get('/me')
      .then(me => {
        if (!cancelled) {
          setUser(me)
          setSetupRequired(false)
        }
      })
      .catch(err => {
        if (cancelled) return
        setUser(null)
        if (err instanceof UnauthorizedError) {
          setSetupRequired(Boolean(err.data?.setup_required))
        }
      })
      .finally(() => {
        if (!cancelled) setCheckingSession(false)
      })
    return () => { cancelled = true }
  }, [])

  function handleLoggedIn(loggedInUser) {
    setUser(loggedInUser)
    setSetupRequired(false)
  }

  async function handleLogout() {
    try {
      await api.post('/logout', {})
    } catch {
      // Clearing local state matters more than the response here.
    }
    setUser(null)
    setFlash({ type: 'success', text: 'Abgemeldet.' })
  }

  return (
    <BrowserRouter>
      <div className="app">
        <div className="glow-bg" aria-hidden="true" />
        <nav className="navbar">
          <NavLink to="/" className="navbar-brand">Schichtplan-Tool</NavLink>
          <div className="navbar-right">
            {user ? (
              <>
                <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>Dienstplan</NavLink>
                <NavLink to="/employees" className={({ isActive }) => isActive ? 'active' : ''}>Mitarbeiter</NavLink>
                <NavLink to="/shift-types" className={({ isActive }) => isActive ? 'active' : ''}>Schichtarten</NavLink>
                <NavLink to="/register" className={({ isActive }) => isActive ? 'active' : ''}>Konten</NavLink>
                <button onClick={handleLogout}>Abmelden ({user.username})</button>
              </>
            ) : (
              <NavLink to="/login" className={({ isActive }) => isActive ? 'active' : ''}>Anmelden</NavLink>
            )}
          </div>
        </nav>

        <Flash flash={flash} onClose={() => setFlash(null)} />

        <main className={`page ${user ? 'page-wide' : ''}`}>
          {checkingSession ? (
            <p className="hint">Lade …</p>
          ) : (
            <Routes>
              <Route path="/" element={
                <RequireAuth user={user} setupRequired={setupRequired}><SchedulePage setFlash={setFlash} /></RequireAuth>
              } />
              <Route path="/employees" element={
                <RequireAuth user={user} setupRequired={setupRequired}><Employees setFlash={setFlash} /></RequireAuth>
              } />
              <Route path="/shift-types" element={
                <RequireAuth user={user} setupRequired={setupRequired}><ShiftTypes setFlash={setFlash} /></RequireAuth>
              } />
              <Route path="/login" element={
                user ? <Navigate to="/" replace />
                     : <Login onLoggedIn={handleLoggedIn} setFlash={setFlash} />
              } />
              <Route path="/register" element={
                // Open to everyone only while no account exists yet; afterwards
                // it is how a signed-in user adds a colleague.
                (user || setupRequired)
                  ? <Register isSetup={setupRequired} currentUser={user} onLoggedIn={handleLoggedIn} setFlash={setFlash} />
                  : <Navigate to="/login" replace />
              } />
              <Route path="*" element={<Navigate to={user ? '/' : (setupRequired ? '/register' : '/login')} replace />} />
            </Routes>
          )}
        </main>
        <footer className="footer">
          <p>2026 Muhammet Sahin. Schichtplan-Tool — internes HR-Werkzeug, kein Mitarbeiter-Login.</p>
        </footer>
      </div>
    </BrowserRouter>
  )
}

export default App
