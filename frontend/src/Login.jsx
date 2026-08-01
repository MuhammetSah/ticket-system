import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

function Login({ onLoginSuccess, setFlash }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  async function handleLogin() {
    const response = await fetch(`${import.meta.env.VITE_API_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, password: password }),
      credentials: 'include'
    })

    const data = await response.json()

    if (response.ok) {
      onLoginSuccess()
      setFlash({ type: 'success', text: 'Login successful!' })
      navigate('/')
    } else {
      setFlash({ type: 'error', text: data.message || 'Login failed.' })
    }
  }

  return (
    <div className="login">
      <h2>Login</h2>
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
      <button onClick={handleLogin}>Login</button>
    </div>
  )
}
export default Login