import { useState } from 'react'

/**
 * Shows how the month's shifts landed across the team, so HR can see at a glance
 * whether the plan is balanced - and can spot it going lopsided as they edit.
 */
function Distribution({ distribution }) {
  const [open, setOpen] = useState(false)
  const rows = distribution.per_employee
  if (rows.length === 0) return null

  const busiest = Math.max(...rows.map(r => r.total), 1)

  return (
    <div className="distribution">
      <button type="button" className="distribution-toggle" onClick={() => setOpen(!open)}>
        {open ? '▾' : '▸'} Verteilung der Schichten
      </button>

      {open && (
        <ul className="distribution-list">
          {rows.map(row => (
            <li key={row.employee_id} className="distribution-row">
              <span className="distribution-name">{row.name}</span>
              <span className="distribution-bar-track">
                <span
                  className="distribution-bar"
                  style={{ width: `${(row.total / busiest) * 100}%` }}
                />
              </span>
              <span className="distribution-count">
                {row.total}
                {row.weekend > 0 && <em> ({row.weekend} WE)</em>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default Distribution
