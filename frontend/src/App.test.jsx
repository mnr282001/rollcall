import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const API_URL = 'http://localhost:8000'

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => body }
}

/** Fake SSE streaming response: each entry in `textChunks` is delivered as one `reader.read()` result. */
function sseResponse(textChunks) {
  let i = 0
  const encoder = new TextEncoder()
  return {
    ok: true,
    status: 200,
    body: {
      getReader() {
        return {
          async read() {
            if (i < textChunks.length) {
              const value = encoder.encode(textChunks[i])
              i += 1
              return { done: false, value }
            }
            return { done: true, value: undefined }
          },
        }
      },
    },
  }
}

function sseEvent(content) {
  return `data: ${JSON.stringify(content)}\n\n`
}

const defaultStatus = { authenticated: false, github_connected: false, jira_connected: false }
const defaultHistory = { messages: [] }

function mockFetch(handlers) {
  const calls = []
  global.fetch = vi.fn(async (url, options) => {
    calls.push({ url, options })
    for (const [matcher, respond] of handlers) {
      // A plain string only matches plain GETs — DELETE/POST to the same URL need an explicit function matcher.
      const matches =
        typeof matcher === 'string' ? url === matcher && (options?.method ?? 'GET') === 'GET' : matcher(url, options)
      if (matches) return respond(url, options)
    }
    throw new Error(`Unhandled fetch: ${options?.method || 'GET'} ${url}`)
  })
  return calls
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('initial load', () => {
  it('shows a hint when there is no chat history', async () => {
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
    ])

    render(<App />)

    expect(await screen.findByText(/Try: "What is Nayab working on/)).toBeInTheDocument()
  })

  it('renders prior chat history returned from the backend', async () => {
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [
        `${API_URL}/chat/history`,
        () => jsonResponse({ messages: [{ role: 'user', content: 'Hi' }, { role: 'assistant', content: 'Hello there' }] }),
      ],
    ])

    render(<App />)

    expect(await screen.findByText('Hi')).toBeInTheDocument()
    expect(await screen.findByText('Hello there')).toBeInTheDocument()
  })

  it('reflects connection status from /auth/me', async () => {
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse({ authenticated: true, github_connected: true, jira_connected: false })],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
    ])

    render(<App />)

    expect(await screen.findByText(/GitHub connected/)).toBeInTheDocument()
    expect(await screen.findByText(/Connect Jira/)).toBeInTheDocument()
  })

  it('falls back to a disconnected status if /auth/me fails', async () => {
    mockFetch([
      [`${API_URL}/auth/me`, () => { throw new Error('network down') }],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
    ])

    render(<App />)

    expect(await screen.findByText(/Connect GitHub/)).toBeInTheDocument()
    expect(await screen.findByText(/Connect Jira/)).toBeInTheDocument()
  })
})

describe('sending a message', () => {
  it('streams the assistant reply and appends it to the thread', async () => {
    const user = userEvent.setup()
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
      [
        (url, options) => url === `${API_URL}/chat` && options.method === 'POST',
        () => sseResponse([sseEvent('Hello '), sseEvent('world')]),
      ],
    ])

    render(<App />)
    await screen.findByText(/Try: "What is Nayab/)

    await user.type(screen.getByPlaceholderText(/What is Nayab working on/), 'hi there')
    await user.click(screen.getByRole('button', { name: /send/i }))

    expect(await screen.findByText('hi there')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Hello world')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /send/i })).not.toBeDisabled()
  })

  it('shows a login error and drops the optimistic reply on 401', async () => {
    const user = userEvent.setup()
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
      [
        (url, options) => url === `${API_URL}/chat` && options.method === 'POST',
        () => jsonResponse({}, { ok: false, status: 401 }),
      ],
    ])

    render(<App />)
    await screen.findByText(/Try: "What is Nayab/)

    await user.type(screen.getByPlaceholderText(/What is Nayab working on/), 'hi there')
    await user.click(screen.getByRole('button', { name: /send/i }))

    expect(await screen.findByText(/Not logged in/)).toBeInTheDocument()
    // only the empty streaming placeholder is dropped on 401 — the user's own message stays visible
    expect(screen.getByText('hi there')).toBeInTheDocument()
  })

  it('shows a generic request-failed error on other non-ok statuses', async () => {
    const user = userEvent.setup()
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
      [
        (url, options) => url === `${API_URL}/chat` && options.method === 'POST',
        () => jsonResponse({}, { ok: false, status: 500 }),
      ],
    ])

    render(<App />)
    await screen.findByText(/Try: "What is Nayab/)

    await user.type(screen.getByPlaceholderText(/What is Nayab working on/), 'hi there')
    await user.click(screen.getByRole('button', { name: /send/i }))

    expect(await screen.findByText(/Request failed \(500\)/)).toBeInTheDocument()
  })

  it('shows a network error and drops an empty optimistic reply when fetch throws', async () => {
    const user = userEvent.setup()
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
      [
        (url, options) => url === `${API_URL}/chat` && options.method === 'POST',
        () => { throw new Error('offline') },
      ],
    ])

    render(<App />)
    await screen.findByText(/Try: "What is Nayab/)

    await user.type(screen.getByPlaceholderText(/What is Nayab working on/), 'hi there')
    await user.click(screen.getByRole('button', { name: /send/i }))

    expect(await screen.findByText(/Could not reach the backend/)).toBeInTheDocument()
  })

  it('does not submit an empty message', async () => {
    const user = userEvent.setup()
    const calls = mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
    ])

    render(<App />)
    await screen.findByText(/Try: "What is Nayab/)

    await user.click(screen.getByRole('button', { name: /send/i }))

    expect(calls.some((c) => c.url === `${API_URL}/chat`)).toBe(false)
  })
})

describe('reset chat', () => {
  it('clears messages when the backend confirms the reset', async () => {
    const user = userEvent.setup()
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [`${API_URL}/chat/history`, () => jsonResponse({ messages: [{ role: 'user', content: 'Hi' }] })],
      [
        (url, options) => url === `${API_URL}/chat/history` && options?.method === 'DELETE',
        () => jsonResponse({ ok: true }),
      ],
    ])

    render(<App />)
    await screen.findByText('Hi')

    await user.click(screen.getByRole('button', { name: /reset/i }))

    await waitFor(() => expect(screen.queryByText('Hi')).not.toBeInTheDocument())
    expect(await screen.findByText(/Try: "What is Nayab/)).toBeInTheDocument()
  })

  it('shows an error when the reset request fails', async () => {
    const user = userEvent.setup()
    mockFetch([
      [`${API_URL}/auth/me`, () => jsonResponse(defaultStatus)],
      [`${API_URL}/chat/history`, () => jsonResponse({ messages: [{ role: 'user', content: 'Hi' }] })],
      [
        (url, options) => url === `${API_URL}/chat/history` && options?.method === 'DELETE',
        () => jsonResponse({}, { ok: false, status: 500 }),
      ],
    ])

    render(<App />)
    await screen.findByText('Hi')

    await user.click(screen.getByRole('button', { name: /reset/i }))

    expect(await screen.findByText(/Could not reset chat \(500\)/)).toBeInTheDocument()
    expect(screen.getByText('Hi')).toBeInTheDocument()
  })
})

describe('connection disconnect', () => {
  it('logs out and refreshes connection status', async () => {
    const user = userEvent.setup()
    let meCallCount = 0
    mockFetch([
      [
        `${API_URL}/auth/me`,
        () => {
          meCallCount += 1
          return jsonResponse(
            meCallCount === 1
              ? { authenticated: true, github_connected: true, jira_connected: false }
              : { authenticated: false, github_connected: false, jira_connected: false }
          )
        },
      ],
      [`${API_URL}/chat/history`, () => jsonResponse(defaultHistory)],
      [
        (url, options) => url === `${API_URL}/auth/github/logout` && options?.method === 'POST',
        () => jsonResponse({ github_connected: false }),
      ],
    ])

    render(<App />)
    const disconnectButton = await screen.findByRole('button', { name: /GitHub connected/ })

    await user.click(disconnectButton)

    expect(await screen.findByText(/Connect GitHub/)).toBeInTheDocument()
    expect(meCallCount).toBe(2)
  })
})
