import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetchStatus()
    fetchHistory()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function fetchStatus() {
    try {
      const response = await fetch(`${API_URL}/auth/me`, { credentials: 'include' })
      const data = await response.json()
      setStatus(data)
    } catch {
      setStatus({ authenticated: false, github_connected: false, jira_connected: false })
    }
  }

  async function fetchHistory() {
    try {
      const response = await fetch(`${API_URL}/chat/history`, { credentials: 'include' })
      if (!response.ok) return
      const data = await response.json()
      setMessages(data.messages)
    } catch {
      // history is best-effort — an empty thread just means starting fresh
    }
  }

  async function disconnect(provider) {
    try {
      await fetch(`${API_URL}/auth/${provider}/logout`, { method: 'POST', credentials: 'include' })
    } finally {
      fetchStatus()
    }
  }

  async function resetChat() {
    setError('')
    try {
      const response = await fetch(`${API_URL}/chat/history`, { method: 'DELETE', credentials: 'include' })
      if (!response.ok) {
        setError(`Could not reset chat (${response.status}).`)
        return
      }
      setMessages([])
    } catch {
      setError('Could not reach the backend.')
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const message = input.trim()
    if (!message || sending) return

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: message },
      { role: 'assistant', content: '', streaming: true },
    ])
    setInput('')
    setSending(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })

      if (response.status === 401) {
        setError('Not logged in. Log in with Jira and GitHub first, then try again.')
        setMessages((prev) => prev.slice(0, -1))
        return
      }
      if (!response.ok || !response.body) {
        setError(`Request failed (${response.status}).`)
        setMessages((prev) => prev.slice(0, -1))
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          next[next.length - 1] = { ...last, content: last.content + chunk }
          return next
        })
      }
      const finalChunk = decoder.decode()
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        next[next.length - 1] = { ...last, content: last.content + finalChunk, streaming: false }
        return next
      })
    } catch {
      setError('Could not reach the backend.')
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        return last?.streaming && !last.content ? prev.slice(0, -1) : prev
      })
    } finally {
      setSending(false)
    }
  }

  return (
    <main className="app">
      <div className="header-row">
        <h1>Rollcall</h1>
        {messages.length > 0 && (
          <button type="button" className="reset-button" onClick={resetChat}>
            Reset chat
          </button>
        )}
      </div>

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

      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="hint">Try: "What is Nayab working on these days?"</p>
        )}
        {messages.map((message, i) => (
          <ChatMessage
            key={i}
            role={message.role}
            content={message.content}
            streaming={message.streaming}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {error && <p className="error">{error}</p>}

      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="What is Nayab working on these days?"
        />
        <button type="submit" disabled={sending}>
          {sending ? 'Sending…' : 'Send'}
        </button>
      </form>
    </main>
  )
}

function ChatMessage({ role, content, streaming = false }) {
  if (role === 'user') {
    return <div className={`message message-${role}`}>{content}</div>
  }

  return (
    <div className={`message message-${role}`}>
      {content ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      ) : streaming ? (
        <span className="streaming-status" role="status">
          Looking up activity<span className="streaming-dots" aria-hidden="true">…</span>
        </span>
      ) : null}
    </div>
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
