import { useEffect, useState } from 'react'
import { api, MONTH_NAMES } from '../api'
import ScheduleGrid from '../components/ScheduleGrid'
import CalendarView from '../components/CalendarView'
import Distribution from '../components/Distribution'

function currentMonthKey() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function SchedulePage({ setFlash, user }) {
  const [ym, setYm] = useState(currentMonthKey())
  const [schedule, setSchedule] = useState(null)
  const [employees, setEmployees] = useState([])
  const [shiftTypes, setShiftTypes] = useState([])
  const [loading, setLoading] = useState(true)
  const [warnings, setWarnings] = useState([])
  const [swapSelection, setSwapSelection] = useState(null)
  const [view, setView] = useState('calendar')

  const [year, month] = ym.split('-').map(Number)
  // Employee accounts read the plan; only HR may change it.
  const canEdit = user?.role === 'hr'

  async function loadStaticData() {
    try {
      const [emps, types] = await Promise.all([api.get('/employees'), api.get('/shift-types')])
      setEmployees(emps)
      setShiftTypes(types)
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function fetchSchedule() {
    try {
      return await api.get(`/schedules/${year}/${month}`)
    } catch {
      return null
    }
  }

  async function refreshSchedule() {
    setSchedule(await fetchSchedule())
  }

  // Mount-only fetch; setState happens after the await inside loadStaticData(), not synchronously.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { loadStaticData() }, [])

  // Loading/warnings/selection are reset in handleMonthChange (the event that
  // causes them), so this effect only ever sets state inside the .then().
  useEffect(() => {
    let cancelled = false
    fetchSchedule().then(data => {
      if (!cancelled) {
        setSchedule(data)
        setLoading(false)
      }
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ym])

  function handleMonthChange(newYm) {
    setYm(newYm)
    setLoading(true)
    setWarnings([])
    setSwapSelection(null)
  }

  async function generate() {
    if (shiftTypes.length === 0) {
      setFlash({ type: 'error', text: 'Bitte zuerst mindestens eine Schichtart anlegen.' })
      return
    }
    if (schedule && !confirm('Für diesen Monat existiert bereits ein Plan. Neu generieren und manuelle Änderungen überschreiben?')) {
      return
    }
    try {
      const data = await api.post('/schedules/generate', { year, month })
      setSchedule(data)
      setWarnings([])
      setFlash({
        type: data.unfilled_count > 0 ? 'error' : 'success',
        text: data.unfilled_count > 0
          ? `Plan erstellt, aber ${data.unfilled_count} Schicht(en) konnten nicht besetzt werden.`
          : 'Plan erfolgreich erstellt - alle Schichten besetzt.',
      })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function deleteSchedule() {
    if (!confirm('Plan für diesen Monat wirklich löschen?')) return
    try {
      await api.delete(`/schedules/${year}/${month}`)
      setSchedule(null)
      setFlash({ type: 'success', text: 'Plan gelöscht.' })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function reassign(assignmentId, employeeIdRaw) {
    const employeeId = employeeIdRaw === '' ? null : Number(employeeIdRaw)
    try {
      const result = await api.put(`/assignments/${assignmentId}`, { employee_id: employeeId })
      setWarnings(result.warnings || [])
      await refreshSchedule()
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function doSwap(idA, idB) {
    try {
      const result = await api.post('/assignments/swap', { assignment_id_a: idA, assignment_id_b: idB })
      setWarnings(result.warnings || [])
      await refreshSchedule()
      setFlash({ type: 'success', text: 'Schichten getauscht.' })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function setTimes(date, shiftTypeId, startTime, endTime) {
    try {
      const result = await api.put(`/schedules/${year}/${month}/shift-times`, {
        date,
        shift_type_id: shiftTypeId,
        start_time: startTime,
        end_time: endTime,
      })
      await refreshSchedule()
      setFlash({ type: 'success', text: result.message })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function addSlot(date, shiftTypeId) {
    try {
      await api.post(`/schedules/${year}/${month}/slots`, { date, shift_type_id: shiftTypeId })
      await refreshSchedule()
      setFlash({ type: 'success', text: 'Platz hinzugefügt - jetzt jemanden zuweisen.' })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  async function removeSlot(assignmentId) {
    try {
      await api.delete(`/assignments/${assignmentId}`)
      await refreshSchedule()
      setFlash({ type: 'success', text: 'Platz entfernt.' })
    } catch (err) {
      setFlash({ type: 'error', text: err.message })
    }
  }

  function toggleSwapSelect(assignmentId) {
    if (swapSelection === assignmentId) {
      setSwapSelection(null)
    } else if (swapSelection === null) {
      setSwapSelection(assignmentId)
    } else {
      doSwap(swapSelection, assignmentId)
      setSwapSelection(null)
    }
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Dienstplan</h2>
        <div className="toolbar">
          <div className="field">
            <label htmlFor="month-picker">Monat</label>
            <input id="month-picker" type="month" value={ym} onChange={e => handleMonthChange(e.target.value)} />
          </div>
          {canEdit && (
            <>
              <button onClick={generate}>{schedule ? 'Neu generieren' : 'Plan generieren'}</button>
              {schedule && <button type="button" className="btn-danger" onClick={deleteSchedule}>Plan löschen</button>}
            </>
          )}
        </div>
      </div>

      {schedule && (
        <div className="toolbar">
          <div className="view-toggle">
            <button
              type="button"
              className={view === 'calendar' ? 'active' : ''}
              onClick={() => setView('calendar')}
            >
              Kalender
            </button>
            <button
              type="button"
              className={view === 'table' ? 'active' : ''}
              onClick={() => setView('table')}
            >
              Tabelle
            </button>
          </div>
        </div>
      )}

      {loading && <p className="hint">Lade …</p>}

      {!loading && !schedule && (
        <p className="empty-state">
          Für {MONTH_NAMES[month - 1]} {year} wurde noch kein Plan generiert.
          {!canEdit && ' Sobald die Personalabteilung den Plan erstellt hat, erscheint er hier.'}
        </p>
      )}

      {!loading && schedule && (
        <>
          <div className="schedule-summary">
            <span className="badge">
              {schedule.scope === 'own'
                ? `${schedule.assignments.length} eigene Schichten`
                : `${schedule.assignments.length} Schichten insgesamt`}
            </span>
            {schedule.scope !== 'own' && (
              schedule.unfilled_count > 0 ? (
                <span className="badge badge-inactive">{schedule.unfilled_count} unbesetzt</span>
              ) : (
                <span className="badge">Vollständig besetzt</span>
              )
            )}
            {schedule.distribution && (
              <>
                <span className="badge">Differenz {schedule.distribution.spread} Schichten</span>
                <span className="badge">Wochenende ±{schedule.distribution.weekend_spread}</span>
              </>
            )}
          </div>

          {schedule.distribution && <Distribution distribution={schedule.distribution} />}

          {warnings.length > 0 && (
            <div className="warning-list">
              Hinweis zur letzten Änderung:
              <ul>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}

          {schedule.scope === 'own' && (
            <p className="hint">Ihre eigenen Schichten in {MONTH_NAMES[month - 1]} {year}.</p>
          )}

          {view === 'table' && canEdit && (
            <p className="hint">
              Umbesetzen über die Auswahlfelder, ⇄ tauscht zwei Schichten, ✎ ändert die Zeiten nur an diesem Tag,
              „+ Platz“ und ✕ fügen an einem Tag eine Besetzung hinzu oder entfernen sie
              {swapSelection && ' — 1 Schicht ausgewählt, jetzt eine zweite anklicken'}.
            </p>
          )}

          {view === 'calendar' ? (
            <div className="calendar-wrap">
              <CalendarView
                schedule={schedule}
                shiftTypes={shiftTypes}
                highlightEmployeeId={user?.employee_id ?? null}
              />
            </div>
          ) : (
            <ScheduleGrid
              schedule={schedule}
              employees={employees}
              shiftTypes={shiftTypes}
              readOnly={!canEdit}
              onReassign={reassign}
              swapSelection={swapSelection}
              onToggleSwap={toggleSwapSelect}
              onSetTimes={setTimes}
              onAddSlot={addSlot}
              onRemoveSlot={removeSlot}
            />
          )}
        </>
      )}
    </div>
  )
}

export default SchedulePage
