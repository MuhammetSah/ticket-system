import { useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import SchedulePage from './pages/SchedulePage'
import Employees from './pages/Employees'
import ShiftTypes from './pages/ShiftTypes'
import Flash from './Flash'
import './App.css'

function App() {
  const [flash, setFlash] = useState(null)

  return (
    <BrowserRouter>
      <div className="app">
        <div className="glow-bg" aria-hidden="true" />
        <nav className="navbar">
          <NavLink to="/" className="navbar-brand">Schichtplan-Tool</NavLink>
          <div className="navbar-right">
            <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>Dienstplan</NavLink>
            <NavLink to="/employees" className={({ isActive }) => isActive ? 'active' : ''}>Mitarbeiter</NavLink>
            <NavLink to="/shift-types" className={({ isActive }) => isActive ? 'active' : ''}>Schichtarten</NavLink>
          </div>
        </nav>

        <Flash flash={flash} onClose={() => setFlash(null)} />

        <main className="page page-wide">
          <Routes>
            <Route path="/" element={<SchedulePage setFlash={setFlash} />} />
            <Route path="/employees" element={<Employees setFlash={setFlash} />} />
            <Route path="/shift-types" element={<ShiftTypes setFlash={setFlash} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <footer className="footer">
          <p>2026 Muhammet Sahin. Schichtplan-Tool — internes HR-Werkzeug, kein Mitarbeiter-Login.</p>
        </footer>
      </div>
    </BrowserRouter>
  )
}

export default App
