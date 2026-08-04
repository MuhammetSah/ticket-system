import { useEffect, useState } from 'react'
import { api, WEEKDAY_LABELS, WEEKDAY_NAMES } from '../api'

const emptyForm = {
  id: null,
  name: '',
  email: '',
  active: true,
  max_shifts_per_month: '',
  unavailable_weekdays: [],
  allowed_shift_types: [],
  unavailable_dates: [],
}

function Employees({ setFlash }) {
  const [employees, setEmployees] = useState([])
  const [shiftTypes, setShiftTypes] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [newDate, setNewDate] = useState('')

  async function load() {
    try {
      const [emps, types] = await Promise.all([api.get('/employees'), api.get('/shift-types')])
      setEmployees(emps)
      setShiftTypes(types)
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Mount-only fetch; setState happens after the awaits inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  function startCreate() {
    setForm(emptyForm)
    setShowForm(true)
  }

  function startEdit(emp) {
    setForm({
      id: emp.id,
      name: emp.name,
      email: emp.email || '',
      active: emp.active,
      max_shifts_per_month: emp.max_shifts_per_month ?? '',
      unavailable_weekdays: emp.unavailable_weekdays,
      allowed_shift_types: emp.allowed_shift_types,
      unavailable_dates: emp.unavailable_dates,
    })
    setShowForm(true)
  }

  function toggleWeekday(wd) {
    setForm(f => ({
      ...f,
      unavailable_weekdays: f.unavailable_weekdays.includes(wd)
        ? f.unavailable_weekdays.filter(x => x !== wd)
        : [...f.unavailable_weekdays, wd],
    }))
  }

  function toggleShiftType(id) {
    setForm(f => ({
      ...f,
      allowed_shift_types: f.allowed_shift_types.includes(id)
        ? f.allowed_shift_types.filter(x => x !== id)
        : [...f.allowed_shift_types, id],
    }))
  }

  function addUnavailableDate() {
    if (!newDate || form.unavailable_dates.some(d => d.date === newDate)) return
    setForm(f => ({ ...f, unavailable_dates: [...f.unavailable_dates, { date: newDate, reason: '' }] }))
    setNewDate('')
  }

  function removeUnavailableDate(date) {
    setForm(f => ({ ...f, unavailable_dates: f.unavailable_dates.filter(d => d.date !== date) }))
  }

  async function submitForm(e) {
    e.preventDefault()
    const payload = {
      name: form.name,
      email: form.email || null,
      active: form.active,
      max_shifts_per_month: form.max_shifts_per_month === '' ? null : Number(form.max_shifts_per_month),
      unavailable_weekdays: form.unavailable_weekdays,
      allowed_shift_types: form.allowed_shift_types,
      unavailable_dates: form.unavailable_dates,
    }
    try {
      if (form.id) {
        await api.put(`/employees/${form.id}`, payload)
        setFlash({ type: 'success', text: 'Mitarbeiter aktualisiert.' })
      } else {
        await api.post('/employees', payload)
        setFlash({ type: 'success', text: 'Mitarbeiter angelegt.' })
      }
      setShowForm(false)
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteEmployee(id) {
    if (!confirm('Diesen Mitarbeiter wirklich löschen?')) return
    try {
      await api.delete(`/employees/${id}`)
      setFlash({ type: 'success', text: 'Mitarbeiter gelöscht.' })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  function shiftTypeName(id) {
    return shiftTypes.find(s => s.id === id)?.name || `#${id}`
  }

  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <h2>Mitarbeiter</h2>
          <button onClick={startCreate}>+ Neuer Mitarbeiter</button>
        </div>

        {employees.length === 0 ? (
          <p className="empty-state">Noch keine Mitarbeiter angelegt.</p>
        ) : (
          <ul className="item-list">
            {employees.map(emp => (
              <li key={emp.id} className="item-row">
                <div className="item-main">
                  <span className="item-title">{emp.name}{!emp.active && ' (inaktiv)'}</span>
                  <div className="item-meta">
                    {emp.email && <span className="badge">{emp.email}</span>}
                    {emp.max_shifts_per_month != null && <span className="badge">max. {emp.max_shifts_per_month}/Monat</span>}
                    {emp.unavailable_weekdays.map(wd => (
                      <span key={wd} className="badge">nicht {WEEKDAY_NAMES[wd]}</span>
                    ))}
                    {emp.allowed_shift_types.length > 0 && (
                      <span className="badge">nur {emp.allowed_shift_types.map(shiftTypeName).join(', ')}</span>
                    )}
                    {emp.unavailable_dates.length > 0 && (
                      <span className="badge">{emp.unavailable_dates.length} freie Tage</span>
                    )}
                  </div>
                </div>
                <div className="item-actions">
                  <button className="btn-secondary btn-small" onClick={() => startEdit(emp)}>Bearbeiten</button>
                  <button className="btn-danger btn-small" onClick={() => deleteEmployee(emp.id)}>Löschen</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showForm && (
        <div className="panel">
          <h3>{form.id ? 'Mitarbeiter bearbeiten' : 'Neuer Mitarbeiter'}</h3>
          <form onSubmit={submitForm}>
            <div className="field">
              <label htmlFor="emp-name">Name</label>
              <input id="emp-name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
            </div>
            <div className="field">
              <label htmlFor="emp-email">E-Mail (optional)</label>
              <input id="emp-email" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="emp-max">Maximale Schichten pro Monat (optional)</label>
              <input id="emp-max" type="number" min="0" value={form.max_shifts_per_month} onChange={e => setForm(f => ({ ...f, max_shifts_per_month: e.target.value }))} />
            </div>
            <div className="field checkbox-field">
              <input id="emp-active" type="checkbox" checked={form.active} onChange={e => setForm(f => ({ ...f, active: e.target.checked }))} />
              <label htmlFor="emp-active">Aktiv (wird bei der Planung berücksichtigt)</label>
            </div>
            <div className="field">
              <label>Arbeitet nicht an</label>
              <div className="weekday-picker">
                {WEEKDAY_LABELS.map((label, wd) => (
                  <button
                    type="button"
                    key={wd}
                    className={`weekday-chip ${form.unavailable_weekdays.includes(wd) ? 'selected' : ''}`}
                    onClick={() => toggleWeekday(wd)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {shiftTypes.length > 0 && (
              <div className="field">
                <label>Nur folgende Schichtarten (leer = alle erlaubt)</label>
                <div className="weekday-picker">
                  {shiftTypes.map(st => (
                    <button
                      type="button"
                      key={st.id}
                      className={`weekday-chip ${form.allowed_shift_types.includes(st.id) ? 'selected' : ''}`}
                      onClick={() => toggleShiftType(st.id)}
                    >
                      {st.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="field">
              <label htmlFor="emp-date-off">Einzelne freie Tage (Urlaub, Krankheit, ...)</label>
              <div className="toolbar">
                <input id="emp-date-off" type="date" value={newDate} onChange={e => setNewDate(e.target.value)} />
                <button type="button" className="btn-secondary" onClick={addUnavailableDate}>Hinzufügen</button>
              </div>
              {form.unavailable_dates.length > 0 && (
                <div className="item-meta mt-sm">
                  {form.unavailable_dates.map(d => (
                    <span key={d.date} className="badge">
                      {d.date}
                      <button type="button" className="badge-remove" onClick={() => removeUnavailableDate(d.date)}>×</button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="toolbar">
              <button type="submit">{form.id ? 'Speichern' : 'Anlegen'}</button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Abbrechen</button>
            </div>
          </form>
        </div>
      )}
    </>
  )
}

export default Employees
