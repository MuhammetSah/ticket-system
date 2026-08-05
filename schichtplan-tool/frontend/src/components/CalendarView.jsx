import { WEEKDAY_LABELS } from '../api'

/**
 * The month as a wall calendar: one column per weekday, one row per week.
 *
 * Each day cell lists its shift types, and under each one every person working
 * it - a shift needing three people simply shows three names. Read-only by
 * design; editing lives in the table view, which has room for the controls.
 */
function CalendarView({ schedule, shiftTypes, highlightEmployeeId }) {
  const byDate = new Map()
  for (const a of schedule.assignments) {
    if (!byDate.has(a.date)) byDate.set(a.date, [])
    byDate.get(a.date).push(a)
  }
  if (!schedule.year || !schedule.month) return null

  // Lay the grid out from the calendar month itself, not from the dates that
  // happen to have shifts. An employee only sees the days they work, so driving
  // the layout off the data would slide every date into the wrong weekday.
  const { year, month } = schedule
  const daysInMonth = new Date(year, month, 0).getDate()
  const allDates = Array.from(
    { length: daysInMonth },
    (_, i) => `${year}-${String(month).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`
  )

  // Pad so the first row starts on a Monday and the last row ends on a Sunday.
  const leadingBlanks = (new Date(year, month - 1, 1).getDay() + 6) % 7
  const trailingBlanks = 6 - ((new Date(year, month - 1, daysInMonth).getDay() + 6) % 7)

  const cells = [
    ...Array(leadingBlanks).fill(null),
    ...allDates,
    ...Array(trailingBlanks).fill(null),
  ]

  const weeks = []
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7))
  }

  const shiftOrder = new Map(shiftTypes.map((st, i) => [st.id, i]))

  function dayNumber(iso) {
    return Number(iso.slice(8, 10))
  }

  return (
    <div className="calendar">
      <div className="calendar-head">
        {WEEKDAY_LABELS.map(label => (
          <div key={label} className="calendar-head-cell">{label}</div>
        ))}
      </div>

      {weeks.map((week, weekIndex) => (
        <div key={weekIndex} className="calendar-week">
          {week.map((iso, dayIndex) => {
            if (!iso) {
              return <div key={`blank-${dayIndex}`} className="calendar-day calendar-day-empty" />
            }

            const dayAssignments = byDate.get(iso) || []
            const groups = new Map()
            for (const a of dayAssignments) {
              if (!groups.has(a.shift_type_id)) groups.set(a.shift_type_id, [])
              groups.get(a.shift_type_id).push(a)
            }
            const orderedGroups = [...groups.entries()].sort(
              (a, b) => (shiftOrder.get(a[0]) ?? 0) - (shiftOrder.get(b[0]) ?? 0)
            )
            const isWeekend = dayIndex >= 5
            const hasGap = dayAssignments.some(a => a.employee_id === null)

            return (
              <div key={iso} className={`calendar-day ${isWeekend ? 'calendar-day-weekend' : ''}`}>
                <div className="calendar-day-header">
                  <span className="calendar-day-number">{dayNumber(iso)}</span>
                  {hasGap && <span className="calendar-gap-dot" title="Unbesetzte Schicht" />}
                </div>

                {orderedGroups.map(([shiftTypeId, slots]) => (
                  <div key={shiftTypeId} className="calendar-shift">
                    <div className="calendar-shift-name">
                      <span className="badge-dot" style={{ backgroundColor: slots[0].shift_type_color }} />
                      {slots[0].shift_type_name}
                      <span
                        className={`calendar-shift-time ${slots[0].time_overridden ? 'calendar-shift-time-changed' : ''}`}
                        title={slots[0].time_overridden
                          ? `Nur an diesem Tag ${slots[0].start_time}–${slots[0].end_time} statt ${slots[0].default_start_time}–${slots[0].default_end_time}`
                          : undefined}
                      >
                        {slots[0].start_time}–{slots[0].end_time}{slots[0].time_overridden ? ' *' : ''}
                      </span>
                    </div>
                    <ul className="calendar-people">
                      {slots
                        .slice()
                        .sort((a, b) => a.slot_index - b.slot_index)
                        .map(slot => (
                          <li
                            key={slot.id}
                            className={[
                              'calendar-person',
                              slot.employee_id === null ? 'calendar-person-unfilled' : '',
                              highlightEmployeeId && slot.employee_id === highlightEmployeeId ? 'calendar-person-me' : '',
                            ].join(' ').trim()}
                          >
                            {slot.employee_name || 'unbesetzt'}
                          </li>
                        ))}
                    </ul>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

export default CalendarView
