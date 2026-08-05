import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'

/**
 * Used twice: to create the very first account on a fresh install, and by a
 * signed-in user to add a colleague. `isSetup` tells the two apart so the
 * wording matches what the person is actually doing.
 */
function Register({ isSetup, currentUser, onLoggedIn, setFlash }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const user = await api.post('/register', { username, password })
      if (currentUser) {
        // An existing user stays signed in as themselves after adding someone.
        setFlash({ type: 'success', text: `Konto für ${user.username} angelegt.` })
        setUsername('')
        setPassword('')
      } else {
        onLoggedIn(user)
        setFlash({ type: 'success', text: `Konto angelegt. Willkommen, ${user.username}.` })
        navigate('/')
      }
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel panel-narrow">
      <h2>{currentUser ? 'Kollegin oder Kollegen hinzufügen' : 'Erstes Konto einrichten'}</h2>
      <p className="hint">
        {currentUser
          ? 'Das neue Konto hat dieselben Rechte wie Ihres.'
          : 'Dieses Konto erhält Zugriff auf alle Mitarbeiter- und Planungsdaten. Weitere Konten kann danach nur ein angemeldeter Benutzer anlegen.'}
      </p>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="register-username">Benutzername</label>
          <input
            id="register-username"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="register-password">Passwort</label>
          <input
            id="register-password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />
          <p className="hint">Mindestens 8 Zeichen.</p>
        </div>
        <button type="submit" disabled={busy}>
          {busy ? 'Speichern …' : (currentUser ? 'Konto anlegen' : 'Konto einrichten')}
        </button>
      </form>
      {!currentUser && !isSetup && (
        <p className="hint mt-md">
          Bereits registriert? <Link to="/login">Zur Anmeldung</Link>
        </p>
      )}
    </div>
  )
}

export default Register
