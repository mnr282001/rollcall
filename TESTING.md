# Testing

Two independent suites: `backend/tests/` (pytest) and `frontend/src/*.test.jsx`
(vitest + Testing Library). Both are pure unit/component tests against mocked
network boundaries — no real Supabase, GitHub, Jira, or OpenAI calls, and no
browser needed for the frontend suite (jsdom).

## Running

```bash
# backend
cd backend && source .venv/bin/activate
python3 -m pytest tests/ -v

# frontend
cd frontend
npx vitest run          # single run
npx vitest               # watch mode
```

`backend/pytest.ini` sets `asyncio_mode = auto` so `async def test_...`
functions run without `@pytest.mark.asyncio` boilerplate. `frontend/vite.config.js`
configures the `jsdom` test environment and `src/setupTests.js` (loads
`@testing-library/jest-dom` matchers and polyfills `scrollIntoView`, which
jsdom doesn't implement).

## Backend (`backend/tests/`, 93 tests)

Every external boundary — Supabase, GitHub's REST API, Jira's REST API, OAuth
token endpoints, OpenAI's streaming completions API — is monkeypatched at the
function level (`monkeypatch.setattr`) or via fake `httpx.Response` objects, so
nothing here makes a real network call.

### `test_github_client.py` / `test_jira_client.py`
Cover the retry/backoff logic added for rate-limit handling:
- A `403` with `X-RateLimit-Remaining: 0` (GitHub's primary limit) or a bare
  `429` (both providers' secondary/standard limit) triggers a retry, honoring
  `Retry-After` or `X-RateLimit-Reset` headers when present, falling back to
  exponential backoff (1s/2s/4s).
- Exhausting all retries raises `GitHubRateLimitError`/`JiraRateLimitError`.
- A plain `403`/`401` with no rate-limit signal still raises the auth error
  immediately, with no retry — this is the bug fix the tests guard: GitHub
  returns 403 for both "bad token" and "rate limited," and conflating them
  used to tell rate-limited users to reconnect their account.

### `test_activity.py`
`get_user_activity`: Jira-only path when there's no linked GitHub username
(skips the GitHub fetch entirely), the concurrent Jira+GitHub fetch path when
there is one, that the repo list is fetched once and threaded into both the
commits and PRs fan-out (not refetched), and that auth/rate-limit errors from
either provider propagate rather than being swallowed.

### `test_users.py`
`resolve_user`'s 24h TTL cache over the `team_members` table: a fresh cache hit
skips live resolution; a stale hit (or a miss) re-resolves against Jira/GitHub
live and re-caches; no Jira match returns `None` without even trying GitHub; and
a connection error during live re-resolution falls back to serving the stale
cached row instead of failing outright — unless there's no cached row to fall
back to, in which case the error still propagates.

### `test_db.py`
Thin wrapper functions around the Supabase client (`create_session`,
`save_github_token`, `get_team_member`, `add_message`, etc.). Since
`supabase-py`'s client is a fluent query builder (`.table().select().eq().execute()`),
these tests use a small hand-rolled fake (`_FakeQuery`/`_FakeClient` in the
test file) that records every call in the chain and returns a canned
`execute()` result, rather than mocking each chained method individually.
Verifies the right table/filter/payload is used per function, and that
"first row or `None`" lookups (`get_session`, `get_team_member`) handle both
found and not-found cases.

### `test_oauth_github.py` / `test_oauth_jira.py`
State-token generation, authorize-URL construction (query params), the
code-for-token(s) exchange, Jira's refresh-token grant, `get_cloud_id`, and
`is_token_expired` — including a locally-constructed fake JWT to test the
valid/expired/within-leeway/malformed-token cases without needing a real
Atlassian token.

### `test_auth_routes.py`
Exercises the actual FastAPI router (`auth_routes.router`) via
`fastapi.testclient.TestClient`, with `oauth_github`/`oauth_jira`/`db` calls
mocked: login redirects and sets a state cookie; callback rejects a
missing/mismatched state cookie (CSRF check) before ever calling the OAuth
exchange; a successful callback sets the session cookie and clears the state
cookie; logout endpoints clear the right token(s) only when a session cookie
is present; and `/auth/me`'s three states (no cookie, unknown session,
authenticated with a specific connection mix).

### `test_main.py`
The rest of `main.py`'s routes, same `TestClient` approach: `/admin/users` and
`/chat*` all require a valid session (401 otherwise); `/chat` returns 500 if
`OPENAI_API_KEY` isn't configured; a streaming chat response is asserted
byte-for-byte against the expected `data: "<chunk>"\n\n` SSE framing by
monkeypatching `chat.stream_message` with a fake async generator; and
`/chat/history` filters out tool-call rows and content-less assistant rows,
returning only `user`/`assistant` turns with real content.

### `test_chat.py`
The core chat logic, `stream_message` and its helpers:
- Pure helpers: timezone resolution (valid/invalid/`None` IANA names all
  handled), UTC→local timestamp conversion, seconds→hours rounding.
- `_activity_facts`: shapes a person's raw Jira/GitHub data into the
  LLM-facing structure, including the `has_linked_github: false` /
  `github_commits: None` case for someone with no GitHub account.
- `_execute_get_activity`: the empty-names short-circuit; splitting resolved
  names into `people`/`not_found`; and — parametrized across both providers —
  that `JiraAuthError`/`GitHubAuthError` → `auth_expired`,
  `*ConnectionError` → `connection`, and `*RateLimitError` → `rate_limited`,
  at both the name-resolution stage and the activity-fetch stage.
- `stream_message` itself, using hand-built fake OpenAI streaming chunks
  (`SimpleNamespace` trees matching the `chunk.choices[0].delta` shape): a
  plain answer with no tool call, a tool-call hop followed by an answer hop
  (asserting the right names reach `_execute_get_activity` and the tool
  result round-trips through `db.add_message`), an `OpenAIError` mid-stream
  falling back to the fallback answer, and hitting `_MAX_HOPS` without ever
  producing content (also falls back).

## Frontend (`frontend/src/App.test.jsx`, 12 tests)

Renders the real `<App />` with `@testing-library/react`, mocking `window.fetch`
per test (a small dispatcher matching on URL + method — a plain string matches
GETs only, so a GET and a DELETE to the same `/chat/history` URL don't collide).
Streaming responses are faked with a hand-rolled `body.getReader()` that yields
pre-encoded SSE chunks (`data: "<json>"\n\n`), rather than a real
`ReadableStream`, since only the `read()` contract matters to `App.jsx`.

- **Initial load**: renders the "no history" hint when `/chat/history` returns
  no messages; renders prior history when it doesn't; reflects
  `/auth/me`'s connected/disconnected state per provider; and falls back to a
  disconnected status (rather than crashing) if `/auth/me` itself fails.
- **Sending a message**: a full streamed reply gets appended to the thread
  incrementally; a `401` shows a "not logged in" error and drops only the
  empty streaming placeholder (the user's own message stays); a non-401
  non-OK status shows a generic "request failed (`<status>`)" error; a thrown
  `fetch` (network failure) shows "could not reach the backend"; and
  submitting an empty/whitespace message is a no-op (no request sent).
- **Reset chat**: a successful `DELETE /chat/history` clears the thread back
  to the hint state; a failed one shows an error and leaves the existing
  messages in place.
- **Disconnect**: clicking a connected provider's button calls its logout
  endpoint, then re-fetches `/auth/me` and reflects the new (disconnected)
  status.

Not covered: OAuth login itself (`ConnectionStatus`'s "Connect" link just
navigates to a backend URL — nothing to unit test), and real SSE parsing
against a genuine `ReadableStream`/network response, which would need an
integration-level test against a running backend rather than a unit test.
