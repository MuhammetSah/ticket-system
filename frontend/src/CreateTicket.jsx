import { useState } from 'react'

function CreateTicket({ onTicketCreated, setFlash }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [contactName, setContactName] = useState('')
  const [contactEmail, setContactEmail] = useState('')

  async function handleSubmit() {
    const response = await fetch(`${import.meta.env.VITE_API_URL}/tickets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        description: description,
        contact_name: contactName,
        contact_email: contactEmail
      }),
      credentials: 'include'
    })

    const data = await response.json()

    if (response.ok) {
      setTitle('')
      setDescription('')
      setContactName('')
      setContactEmail('')
      setFlash({ type: 'success', text: 'Ticket created successfully!' })
      onTicketCreated()
    } else {
      setFlash({ type: 'error', text: data.message || 'Something went wrong.' })
    }
  }

  return (
    <div className="create-ticket">
      <h2>Create Ticket</h2>
      <input
        type="text"
        placeholder="Title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <input
        type="text"
        placeholder="Your Name"
        value={contactName}
        onChange={(e) => setContactName(e.target.value)}
      />
      <input
        type="text"
        placeholder="Your Email"
        value={contactEmail}
        onChange={(e) => setContactEmail(e.target.value)}
      />
      <textarea
        placeholder="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <button onClick={handleSubmit}>Create Ticket</button>
    </div>
  )
}

export default CreateTicket