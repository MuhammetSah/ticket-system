import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'

function Login({ onLoggedIn, setFlash }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const user = await api.post('/login', { username, password })
      onLoggedIn(user)
      setFlash({ type: 'success', text: `Willkommen zurück, ${user.username}.` })
      navigate('/')
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel panel-narrow">
      <h2>Anmelden</h2>
      <p className="hint">Interner Zugang für die Personalabteilung.</p>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="login-username">Benutzername</label>
          <input
            id="login-username"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">Passwort</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />
        </div>
        <button type="submit" disabled={busy}>{busy ? 'Anmelden …' : 'Anmelden'}</button>
      </form>
      <p className="hint mt-md">
        Noch kein Konto? <Link to="/register">Erstes Konto einrichten</Link>
      </p>
    </div>
  )
}

export default Login
