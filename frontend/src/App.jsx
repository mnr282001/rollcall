import { useEffect, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState(null)

  useEffect(() => {
    fetchStatus()
  }, [])

  async function fetchStatus() {
    try {
      const response = await fetch(`${API_URL}/auth/me`, { credentials: 'include' })
      const data = await response.json()
      setStatus(data)
    } catch {
      setStatus({ authenticated: false, github_connected: false, jira_connected: false })
    }
  }

  async function disconnect(provider) {
    try {
      await fetch(`${API_URL}/auth/${provider}/logout`, { method: 'POST', credentials: 'include' })
    } finally {
      fetchStatus()
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!question.trim()) return

    setLoading(true)
    setError('')
    setAnswer('')

    try {
      const response = await fetch(`${API_URL}/ask`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })

      if (response.status === 401) {
        setError('Not logged in. Log in with Jira and GitHub first, then try again.')
        return
      }
      if (!response.ok) {
        setError(`Request failed (${response.status}).`)
        return
      }

      const data = await response.json()
      setAnswer(data.answer)
    } catch {
      setError('Could not reach the backend.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="app">
      <h1>Team Activity Monitor</h1>
      <p className="hint">
        Try: "What is Nayab working on these days?"
      </p>

      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What is Nayab working on these days?"
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Asking…' : 'Ask'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}
      {answer && <pre className="answer">{answer}</pre>}

      <div className="connections">
        <ConnectionStatus
          label="GitHub"
          connected={status?.github_connected}
          href={`${API_URL}/auth/github/login`}
          onDisconnect={() => disconnect('github')}
        />
        <ConnectionStatus
          label="Jira"
          connected={status?.jira_connected}
          href={`${API_URL}/auth/jira/login`}
          onDisconnect={() => disconnect('jira')}
        />
      </div>
    </main>
  )
}

function ConnectionStatus({ label, connected, href, onDisconnect }) {
  if (connected === undefined || connected === null) {
    return (
      <span className="connection connection-pending">
        <span className="connection-dot" /> {label}
      </span>
    )
  }

  if (connected) {
    return (
      <button type="button" className="connection connection-connected" onClick={onDisconnect}>
        <span className="connection-dot" /> {label} connected · Disconnect
      </button>
    )
  }

  return (
    <a className="connection connection-disconnected" href={href}>
      <span className="connection-dot" /> Connect {label}
    </a>
  )
}

export default App
