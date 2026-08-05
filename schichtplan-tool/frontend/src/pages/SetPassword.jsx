import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'

/**
 * Where an invited employee chooses their own password.
 *
 * Reachable without signing in - the token from the email is the credential -
 * and it is the only way an employee account ever gets a password, so HR never
 * knows it.
 */
function SetPassword({ setFlash }) {
  const [params] = useSearchParams()
  const token = params.get('token')

  const [username, setUsername] = useState(null)
  // A link with no token at all is known-bad up front, so there is nothing to check.
  const [checking, setChecking] = useState(Boolean(token))
  const [invalid, setInvalid] = useState(!token)
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!token) return
    let cancelled = false
    api.get(`/invitations/${token}`)
      .then(data => { if (!cancelled) setUsername(data.username) })
      .catch(() => { if (!cancelled) setInvalid(true) })
      .finally(() => { if (!cancelled) setChecking(false) })
    return () => { cancelled = true }
  }, [token])

  async function handleSubmit(e) {
    e.preventDefault()
    if (password !== repeat) {
      setFlash({ type: 'error', text: 'Die Passwörter stimmen nicht überein.' })
      return
    }
    setBusy(true)
    try {
      const result = await api.post(`/invitations/${token}`, { password })
      setFlash({ type: 'success', text: result.message })
      navigate('/login')
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  if (checking) {
    return <div className="panel panel-narrow"><p className="hint">Link wird geprüft …</p></div>
  }

  if (invalid) {
    return (
      <div className="panel panel-narrow">
        <h2>Link ungültig</h2>
        <p className="hint">
          Dieser Einladungslink ist abgelaufen oder wurde bereits verwendet.
          Bitte wenden Sie sich an die Personalabteilung, um eine neue Einladung zu erhalten.
        </p>
        <Link to="/login">Zur Anmeldung</Link>
      </div>
    )
  }

  return (
    <div className="panel panel-narrow">
      <h2>Passwort festlegen</h2>
      <p className="hint">
        Konto <strong>{username}</strong> — bitte vergeben Sie Ihr eigenes Passwort.
        Es ist nur Ihnen bekannt.
      </p>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="new-password">Neues Passwort</label>
          <input
            id="new-password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />
          <p className="hint">Mindestens 8 Zeichen.</p>
        </div>
        <div className="field">
          <label htmlFor="repeat-password">Passwort wiederholen</label>
          <input
            id="repeat-password"
            type="password"
            autoComplete="new-password"
            value={repeat}
            onChange={e => setRepeat(e.target.value)}
            required
          />
        </div>
        <button type="submit" disabled={busy}>{busy ? 'Speichern …' : 'Passwort speichern'}</button>
      </form>
    </div>
  )
}

export default SetPassword
