import { useEffect, useState } from 'react'
import { api, WEEKDAY_LABELS } from '../api'

const emptyForm = {
  id: null,
  name: '',
  start_time: '08:00',
  end_time: '16:00',
  color: '#0d9488',
  requirements: [1, 1, 1, 1, 1, 1, 1],
}

function ShiftTypes({ setFlash }) {
  const [shiftTypes, setShiftTypes] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)

  async function load() {
    try {
      setShiftTypes(await api.get('/shift-types'))
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  // Mount-only fetch; setState happens after the await inside load(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  function startCreate() {
    setForm(emptyForm)
    setShowForm(true)
  }

  function startEdit(st) {
    setForm({ id: st.id, name: st.name, start_time: st.start_time, end_time: st.end_time, color: st.color, requirements: [...st.requirements] })
    setShowForm(true)
  }

  function setRequirement(wd, value) {
    const count = Math.max(0, Number(value) || 0)
    setForm(f => {
      const requirements = [...f.requirements]
      requirements[wd] = count
      return { ...f, requirements }
    })
  }

  async function submitForm(e) {
    e.preventDefault()
    const payload = { name: form.name, start_time: form.start_time, end_time: form.end_time, color: form.color, requirements: form.requirements }
    try {
      if (form.id) {
        await api.put(`/shift-types/${form.id}`, payload)
        setFlash({ type: 'success', text: 'Schichtart aktualisiert.' })
      } else {
        await api.post('/shift-types', payload)
        setFlash({ type: 'success', text: 'Schichtart angelegt.' })
      }
      setShowForm(false)
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteShiftType(id) {
    if (!confirm('Diese Schichtart wirklich löschen?')) return
    try {
      await api.delete(`/shift-types/${id}`)
      setFlash({ type: 'success', text: 'Schichtart gelöscht.' })
      load()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <h2>Schichtarten</h2>
          <button onClick={startCreate}>+ Neue Schichtart</button>
        </div>

        {shiftTypes.length === 0 ? (
          <p className="empty-state">Noch keine Schichtarten angelegt.</p>
        ) : (
          <ul className="item-list">
            {shiftTypes.map(st => (
              <li key={st.id} className="item-row">
                <div className="item-main">
                  <span className="item-title">
                    <span className="badge-dot" style={{ backgroundColor: st.color }} /> {st.name}
                  </span>
                  <div className="item-meta">
                    <span className="badge">{st.start_time}–{st.end_time}</span>
                    {WEEKDAY_LABELS.map((label, wd) => (
                      <span key={wd} className="badge">{label}: {st.requirements[wd]}</span>
                    ))}
                  </div>
                </div>
                <div className="item-actions">
                  <button className="btn-secondary btn-small" onClick={() => startEdit(st)}>Bearbeiten</button>
                  <button className="btn-danger btn-small" onClick={() => deleteShiftType(st.id)}>Löschen</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showForm && (
        <div className="panel">
          <h3>{form.id ? 'Schichtart bearbeiten' : 'Neue Schichtart'}</h3>
          <form onSubmit={submitForm}>
            <div className="field">
              <label htmlFor="st-name">Name</label>
              <input id="st-name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required placeholder="z. B. Frühschicht" />
            </div>
            <div className="toolbar">
              <div className="field">
                <label htmlFor="st-start">Beginn</label>
                <input id="st-start" type="time" value={form.start_time} onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} required />
              </div>
              <div className="field">
                <label htmlFor="st-end">Ende</label>
                <input id="st-end" type="time" value={form.end_time} onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} required />
              </div>
              <div className="field">
                <label htmlFor="st-color">Farbe</label>
                <input id="st-color" type="color" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} />
              </div>
            </div>
            <div className="field">
              <label>Benötigte Mitarbeiter pro Wochentag</label>
              <div className="weekday-counts">
                {WEEKDAY_LABELS.map((label, wd) => (
                  <div key={wd} className="weekday-count">
                    <label htmlFor={`req-${wd}`}>{label}</label>
                    <input id={`req-${wd}`} type="number" min="0" value={form.requirements[wd]} onChange={e => setRequirement(wd, e.target.value)} />
                  </div>
                ))}
              </div>
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

export default ShiftTypes
