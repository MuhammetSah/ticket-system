import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'

function TicketDetail({ setFlash }) {
    const { id } = useParams()
    const [ticket, setTicket] = useState(null)
    const [currentuser, setCurrentuser] = useState(null)
    const [currentsolution, setCurrentsolution] = useState('')
    const [currentUsername, setCurrentUsername] = useState(null)

    useEffect(() => {
        async function loadTicket() {
            const response = await fetch(`${import.meta.env.VITE_API_URL}/tickets/${id}`)
            const data = await response.json()
            setTicket(data)

            const user_response = await fetch(`${import.meta.env.VITE_API_URL}/me`, { credentials: 'include' })
            const user_data = await user_response.json()
            setCurrentuser(user_data.user_id)
            setCurrentUsername(user_data.username)
        }
        loadTicket()
    }, [id])

    async function handleStatusChange(newStatus) {
        const response = await fetch(`${import.meta.env.VITE_API_URL}/tickets/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
            credentials: 'include'
        })

        const data = await response.json()

        if (response.ok) {
            setTicket({ ...ticket, status: newStatus })
            setFlash({ type: 'success', text: 'Status updated.' })
        } else {
            setFlash({ type: 'error', text: data.message || 'Could not update status.' })
        }
    }

    async function handleSolutionChange(newSolution) {
        const response = await fetch(`${import.meta.env.VITE_API_URL}/tickets/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ solution: newSolution }),
            credentials: 'include'
        })

        const data = await response.json()

        if (response.ok) {
            setTicket({ ...ticket, solution: newSolution })
            setFlash({ type: 'success', text: 'Solution submitted.' })
        } else {
            setFlash({ type: 'error', text: data.message || 'Could not submit solution.' })
        }
    }

    if (!ticket) return <p>Loading...</p>

    return (
        <div className="ticket-detail">
            <h2>Ticket:{ticket.title}</h2>
            <p>Your Name: {ticket.contact_name}</p>
            <p>Your Email: {ticket.contact_email}</p>
            <p>Description: {ticket.description}</p>
            <span className={`status-badge ${ticket.status === 'solved' ? 'status-solved' : 'status-open'}`}>
                {ticket.status}
            </span>
            {currentuser === ticket.user_id || currentUsername === 'admin' ? (
                <div className="button-group">
                    <button onClick={() => handleStatusChange('solved')}>Solved</button>
                    <button onClick={() => handleStatusChange('open')}>Open</button>
                </div>
            ) : (
                <p>Please log in to change the status.</p>
            )}
            <p>Created at: {formatAlter(ticket.created_at)}</p>
            {!ticket.solution && currentUsername === 'admin' ? (
                <>
                    <textarea placeholder='Your solution here' value={currentsolution} onChange={(e) => setCurrentsolution(e.target.value)} />
                    <button onClick={() => handleSolutionChange(currentsolution)}>Submit Solution</button>
                </>
            ) : (
                <div className="solution-box">
                    <p>Solution: {ticket.solution || "No solution yet."}</p>
                </div>
            )}
        </div>
    )
}

function formatAlter(createdAt) {
    const erstellt = new Date(createdAt)
    const jetzt = new Date()
    const diffMs = jetzt - erstellt
    const diffStunden = diffMs / (1000 * 60 * 60)

    if (diffStunden < 1) {
        return "less than an hour ago"
    } else if (diffStunden < 24) {
        return ` ${Math.floor(diffStunden)} hour(s) ago`
    } else {
        const diffTage = Math.floor(diffStunden / 24)
        return ` ${diffTage} day(s) ago`
    }
}

export default TicketDetail