import { useState, useEffect } from "react"
import { Link } from "react-router-dom"

function Tickets({ refreshKey }) {
    const [tickets, setTickets] = useState([])

    useEffect(() => {
        async function loadTickets() {
            const response = await fetch('http://localhost:5000/tickets')
            const data = await response.json()
            setTickets(data)
        }
        loadTickets()
    }, [refreshKey])

    return (
        <div className="tickets">
            <h2>Tickets</h2>
            <ul>
                {tickets.map(ticket => (
                    <li key={ticket.id}>
                        <Link to={`/tickets/${ticket.id}`}>
                            {ticket.title}
                        </Link>
                    </li>
                ))}
            </ul>
        </div>
    )
}
export default Tickets