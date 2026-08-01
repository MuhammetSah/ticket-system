import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

function Register({ onLoginSuccess, setFlash }) {
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const navigate = useNavigate()

    async function handleRegister() {
        const response = await fetch(`${import.meta.env.VITE_API_URL}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username, password: password }),
            credentials: 'include'
        })

        const data = await response.json()

        if (response.ok) {
            onLoginSuccess()
            setFlash({ type: 'success', text: 'Account created successfully!' })
            navigate('/')
        } else {
            setFlash({ type: 'error', text: data.message || 'Registration failed.' })
        }
    }

    return (
        <div className="register">
            <h2>Register</h2>
            <input
                type="text"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)} />
            <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)} />
            <button onClick={handleRegister}>Register</button>
        </div>
    )
}

export default Register