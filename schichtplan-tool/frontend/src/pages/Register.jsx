import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'

/**
 * Used twice: to create the very first account on a fresh install, and by a
 * signed-in user to add a colleague. `isSetup` tells the two apart so the
 * wording matches what the person is actually doing.
 */
function Register({ isSetup, currentUser, onLoggedIn, setFlash, onAccountCreated }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('employee')
  const [employeeId, setEmployeeId] = useState('')
  const [employees, setEmployees] = useState([])
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  // Only HR can link a new read-only account to a roster entry.
  useEffect(() => {
    if (!currentUser) return
    let cancelled = false
    api.get('/employees')
      .then(list => { if (!cancelled) setEmployees(list) })
      .catch(() => { /* the link is optional, so a failure here is not fatal */ })
    return () => { cancelled = true }
  }, [currentUser])

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const payload = { username, password }
      if (currentUser) {
        payload.role = role
        if (role === 'employee' && employeeId) {
          payload.employee_id = Number(employeeId)
        }
      }
      const user = await api.post('/register', payload)
      if (currentUser) {
        // An existing user stays signed in as themselves after adding someone.
        setFlash({ type: 'success', text: `Konto für ${user.username} angelegt.` })
        setUsername('')
        setPassword('')
        setEmployeeId('')
        onAccountCreated?.()
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
    <div className={`panel ${currentUser ? '' : 'panel-narrow'}`}>
      <h2>{currentUser ? 'Kollegin oder Kollegen hinzufügen' : 'Erstes Konto einrichten'}</h2>
      <p className="hint">
        {currentUser
          ? 'Personal-Konten dürfen alles bearbeiten. Mitarbeiter-Konten können den Dienstplan nur ansehen.'
          : 'Dieses Konto erhält Zugriff auf alle Mitarbeiter- und Planungsdaten. Weitere Konten kann danach nur die Personalabteilung anlegen.'}
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
        {currentUser && (
          <>
            <div className="field">
              <label htmlFor="register-role">Rolle</label>
              <select id="register-role" value={role} onChange={e => setRole(e.target.value)}>
                <option value="employee">Mitarbeiter — darf den Dienstplan nur ansehen</option>
                <option value="hr">Personalabteilung — darf alles bearbeiten</option>
              </select>
            </div>
            {role === 'employee' && (
              <div className="field">
                <label htmlFor="register-employee">Mit Mitarbeiter verknüpfen</label>
                <select
                  id="register-employee"
                  value={employeeId}
                  onChange={e => setEmployeeId(e.target.value)}
                  required
                >
                  <option value="">— bitte auswählen —</option>
                  {employees.map(emp => (
                    <option key={emp.id} value={emp.id}>{emp.name}</option>
                  ))}
                </select>
                <p className="hint">Legt fest, wessen Schichten dieses Konto sieht.</p>
              </div>
            )}
          </>
        )}
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
