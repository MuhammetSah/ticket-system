import { useState } from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Login from './Login'
import Register from './Register'
import CreateTicket from './CreateTicket'
import Tickets from './Tickets'
import TicketDetail from './TicketDetail'
import Flash from './Flash'
import './App.css'

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [flash, setFlash] = useState(null)

  async function handleLogout() {
    await fetch(`${import.meta.env.VITE_API_URL}/logout`, {
      method: 'POST',
      credentials: 'include'
    })
    setIsLoggedIn(false)
    setFlash({ type: 'success', text: 'Logged out successfully.' })
  }

  return (
    <BrowserRouter>
      <nav className="navbar">
        <Link to="/">Index</Link>
        <div className="navbar-right">
          {isLoggedIn ? (
            <button onClick={handleLogout}>Logout</button>
          ) : (
            <>
              <Link to="/register">Register</Link>
              <Link to="/login">Login</Link>
            </>
          )}
        </div>
      </nav>

      <Flash flash={flash} onClose={() => setFlash(null)} />

      <Routes>
        <Route path="/" element={
          isLoggedIn ? (
            <>
              <CreateTicket
                onTicketCreated={() => setRefreshKey(refreshKey + 1)}
                setFlash={setFlash}
              />
              <Tickets refreshKey={refreshKey} />
            </>
          ) : (
            <p>Please log in or register.</p>
          )
        } />
        <Route path="/login" element={
          <Login onLoginSuccess={() => setIsLoggedIn(true)} setFlash={setFlash} />
        } />
        <Route path="/register" element={
          <Register onLoginSuccess={() => setIsLoggedIn(true)} setFlash={setFlash} />
        } />
        <Route path="/tickets/:id" element={<TicketDetail setFlash={setFlash} />} />
      </Routes>
      <footer className="footer">
        <p>2026 Muhammet Sahin. All rights reserved. Contact: muhammet.sahin@gmx.net</p>
      </footer>
    </BrowserRouter>
  )
}

export default App