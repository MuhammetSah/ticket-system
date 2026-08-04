import { WEEKDAY_LABELS } from '../api'

function formatDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  const weekdayIndex = (d.getDay() + 6) % 7 // JS: 0=Sunday -> ours: 0=Monday
  return `${WEEKDAY_LABELS[weekdayIndex]}, ${d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}`
}

function isWeekend(iso) {
  const day = new Date(iso + 'T00:00:00').getDay()
  return day === 0 || day === 6
}

function ScheduleGrid({ schedule, employees, shiftTypes, onReassign, swapSelection, onToggleSwap }) {
  const byDate = new Map()
  for (const a of schedule.assignments) {
    if (!byDate.has(a.date)) byDate.set(a.date, new Map())
    const byShift = byDate.get(a.date)
    if (!byShift.has(a.shift_type_id)) byShift.set(a.shift_type_id, [])
    byShift.get(a.shift_type_id).push(a)
  }
  const dates = [...byDate.keys()].sort()

  function employeeOptions(currentEmployeeId) {
    return employees
      .filter(e => e.active || e.id === currentEmployeeId)
      .sort((a, b) => a.name.localeCompare(b.name))
  }

  return (
    <div className="schedule-table-wrap">
      <table className="schedule-table">
        <thead>
          <tr>
            <th>Datum</th>
            {shiftTypes.map(st => <th key={st.id}>{st.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {dates.map(date => (
            <tr key={date} className={isWeekend(date) ? 'weekend' : ''}>
              <td className="date-cell">{formatDate(date)}</td>
              {shiftTypes.map(st => {
                const slots = (byDate.get(date).get(st.id) || []).sort((a, b) => a.slot_index - b.slot_index)
                return (
                  <td key={st.id}>
                    {slots.length === 0 ? (
                      <span className="hint">—</span>
                    ) : (
                      slots.map(slot => (
                        <div
                          key={slot.id}
                          className={`slot-cell ${slot.employee_id ? '' : 'unfilled'} ${swapSelection === slot.id ? 'swap-selected' : ''}`}
                        >
                          <select value={slot.employee_id ?? ''} onChange={e => onReassign(slot.id, e.target.value)}>
                            <option value="">— unbesetzt —</option>
                            {employeeOptions(slot.employee_id).map(e => (
                              <option key={e.id} value={e.id}>{e.name}</option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className={`swap-toggle ${swapSelection === slot.id ? 'active' : ''}`}
                            title="Für Tausch auswählen"
                            onClick={() => onToggleSwap(slot.id)}
                          >
                            ⇄
                          </button>
                        </div>
                      ))
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ScheduleGrid
