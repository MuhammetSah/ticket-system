import { useState } from 'react'

/**
 * One shift on one date: the hours it runs that day, everyone working it, and
 * (for HR) the controls to change any of that.
 *
 * Times are edited per date here, not per person - if the early shift finishes
 * early on one day it finishes early for everyone on it, so the whole cell
 * shares one pair of inputs.
 */
function ShiftCell({
  date,
  shiftType,
  slots,
  employees,
  readOnly,
  swapSelection,
  onReassign,
  onToggleSwap,
  onSetTimes,
  onAddSlot,
  onRemoveSlot,
}) {
  const [editingTimes, setEditingTimes] = useState(false)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  if (slots.length === 0) {
    return readOnly ? (
      <span className="hint">—</span>
    ) : (
      <button type="button" className="cell-add" onClick={() => onAddSlot(date, shiftType.id)}>
        + Platz
      </button>
    )
  }

  const sorted = slots.slice().sort((a, b) => a.slot_index - b.slot_index)
  const sample = sorted[0]

  function startEditing() {
    setStart(sample.start_time)
    setEnd(sample.end_time)
    setEditingTimes(true)
  }

  function employeeOptions(currentEmployeeId) {
    return employees
      .filter(e => e.active || e.id === currentEmployeeId)
      .sort((a, b) => a.name.localeCompare(b.name))
  }

  return (
    <div className="shift-cell">
      {editingTimes ? (
        <div className="cell-time-edit">
          <input type="time" value={start} onChange={e => setStart(e.target.value)} aria-label="Beginn" />
          <input type="time" value={end} onChange={e => setEnd(e.target.value)} aria-label="Ende" />
          <button
            type="button"
            className="btn-small"
            onClick={() => { onSetTimes(date, shiftType.id, start, end); setEditingTimes(false) }}
          >
            OK
          </button>
          {sample.time_overridden && (
            <button
              type="button"
              className="btn-secondary btn-small"
              title={`Zurück auf ${sample.default_start_time}–${sample.default_end_time}`}
              onClick={() => { onSetTimes(date, shiftType.id, null, null); setEditingTimes(false) }}
            >
              Standard
            </button>
          )}
          <button type="button" className="btn-secondary btn-small" onClick={() => setEditingTimes(false)}>
            ✕
          </button>
        </div>
      ) : (
        <div className={`cell-times ${sample.time_overridden ? 'cell-times-overridden' : ''}`}>
          <span title={sample.time_overridden
            ? `Abweichend von ${sample.default_start_time}–${sample.default_end_time}`
            : undefined}>
            {sample.start_time}–{sample.end_time}{sample.time_overridden ? ' *' : ''}
          </span>
          {!readOnly && (
            <button type="button" className="cell-icon" title="Zeiten für diesen Tag ändern" onClick={startEditing}>
              ✎
            </button>
          )}
        </div>
      )}

      {sorted.map(slot => (
        <div
          key={slot.id}
          className={`slot-cell ${slot.employee_id ? '' : 'unfilled'} ${swapSelection === slot.id ? 'swap-selected' : ''}`}
        >
          {readOnly ? (
            <span className={slot.employee_id ? '' : 'calendar-person-unfilled'}>
              {slot.employee_name || 'unbesetzt'}
            </span>
          ) : (
            <>
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
              <button
                type="button"
                className="cell-icon cell-icon-danger"
                title="Diesen Platz an diesem Tag entfernen"
                onClick={() => onRemoveSlot(slot.id)}
              >
                ✕
              </button>
            </>
          )}
        </div>
      ))}

      {!readOnly && (
        <button type="button" className="cell-add" onClick={() => onAddSlot(date, shiftType.id)}>
          + Platz
        </button>
      )}
    </div>
  )
}

export default ShiftCell
