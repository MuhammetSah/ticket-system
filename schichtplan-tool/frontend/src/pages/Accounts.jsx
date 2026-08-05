import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import Register from './Register'

/**
 * HR's view of who can sign in. Deleting an account is the way to revoke a
 * login - and it is also the first step before an employee can be removed from
 * the roster, since a login without a roster entry could never show anything.
 */
function Accounts({ currentUser, setFlash }) {
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      setAccounts(await api.get('/accounts'))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    } finally {
      setLoading(false)
    }
  }, [setFlash])

  // Mount-only fetch; setState happens after the await inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load() }, [load])

  async function resendInvitation(account) {
    try {
      const result = await api.post(`/accounts/${account.id}/invitation`, {})
      setFlash({ type: 'success', text: result.message })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteAccount(account) {
    if (!confirm(`Konto "${account.username}" wirklich löschen?`)) return
    try {
      const result = await api.delete(`/accounts/${account.id}`)
      setFlash({ type: 'success', text: result.message })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  return (
    <>
      <div className="panel">
        <h2>Konten</h2>
        <p className="hint">
          Personal-Konten dürfen alles bearbeiten. Mitarbeiter-Konten sehen ausschließlich ihre eigenen Schichten.
        </p>

        {loading ? (
          <p className="hint">Lade …</p>
        ) : accounts.length === 0 ? (
          <p className="empty-state">Noch keine Konten.</p>
        ) : (
          <ul className="item-list">
            {accounts.map(account => (
              <li key={account.id} className="item-row">
                <div className="item-main">
                  <span className="item-title">
                    {account.username}
                    {account.id === currentUser.id && <span className="badge">Sie</span>}
                  </span>
                  <div className="item-meta">
                    <span className="badge">
                      {account.role === 'hr' ? 'Personalabteilung' : 'Mitarbeiter'}
                    </span>
                    {account.employee_name && <span className="badge">verknüpft mit {account.employee_name}</span>}
                    {account.contact_email && <span className="badge">{account.contact_email}</span>}
                    {account.invitation_pending && (
                      <span className="badge badge-pending">Einladung offen</span>
                    )}
                    {!account.password_set && !account.invitation_pending && (
                      <span className="badge badge-inactive">Kein Passwort gesetzt</span>
                    )}
                  </div>
                </div>
                <div className="item-actions">
                  {account.contact_email && account.id !== currentUser.id && (
                    <button
                      className="btn-secondary btn-small"
                      title="Neuen Einladungslink per E-Mail schicken; ein bestehendes Passwort wird dabei ungültig"
                      onClick={() => resendInvitation(account)}
                    >
                      {account.password_set ? 'Passwort zurücksetzen' : 'Einladung erneut senden'}
                    </button>
                  )}
                  <button
                    className="btn-danger btn-small"
                    disabled={account.id === currentUser.id}
                    title={account.id === currentUser.id ? 'Das eigene Konto kann nicht gelöscht werden' : undefined}
                    onClick={() => deleteAccount(account)}
                  >
                    Löschen
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Register currentUser={currentUser} isSetup={false} setFlash={setFlash} onAccountCreated={load} />
    </>
  )
}

export default Accounts
