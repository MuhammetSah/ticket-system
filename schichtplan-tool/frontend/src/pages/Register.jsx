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

  // An employee account gets its password from the invitation email, so the
  // password field does not belong on this form at all for that role.
  const invitesByEmail = Boolean(currentUser) && role === 'employee'
  const selectedEmployee = employees.find(e => String(e.id) === String(employeeId))

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
      // Employee accounts never receive a password here - they are invited by
      // email and choose their own, so HR cannot know it.
      const payload = invitesByEmail ? { username } : { username, password }
      if (currentUser) {
        payload.role = role
        if (role === 'employee' && employeeId) {
          payload.employee_id = Number(employeeId)
        }
      }
      const user = await api.post('/register', payload)
      if (currentUser) {
        // An existing user stays signed in as themselves after adding someone.
        setFlash({
          type: 'success',
          text: user.invitation_email
            ? (user.invitation_sent
                ? `Konto angelegt. Einladung an ${user.invitation_email} gesendet.`
                : `Konto angelegt. Einladung für ${user.invitation_email} erstellt — kein SMTP konfiguriert, der Link steht im Server-Log.`)
            : `Konto für ${user.username} angelegt.`,
        })
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
        {!invitesByEmail && (
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
        )}
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
            {invitesByEmail && (
              <div className="field">
                {selectedEmployee && !selectedEmployee.email ? (
                  <p className="warning-list">
                    {selectedEmployee.name} hat keine E-Mail-Adresse hinterlegt. Bitte zuerst unter
                    „Mitarbeiter“ ergänzen — ohne Adresse kann keine Einladung verschickt werden.
                  </p>
                ) : (
                  <p className="hint">
                    Es wird kein Passwort vergeben: {selectedEmployee
                      ? <>die Person erhält eine Einladung an <strong>{selectedEmployee.email}</strong> und</>
                      : 'die Person erhält eine Einladung per E-Mail und'} setzt ihr Passwort selbst.
                  </p>
                )}
              </div>
            )}
          </>
        )}
        <button type="submit" disabled={busy || (invitesByEmail && selectedEmployee && !selectedEmployee.email)}>
          {busy ? 'Speichern …' : (invitesByEmail ? 'Konto anlegen und einladen' : (currentUser ? 'Konto anlegen' : 'Konto einrichten'))}
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
