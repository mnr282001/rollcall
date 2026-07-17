# Rollcall

A chat assistant that answers "What is [teammate] working on these days?" by pulling
live Jira and GitHub activity for the people you ask about — tickets, commits, PRs,
and repos, combined into one conversational answer.

Each user connects their *own* Jira and GitHub accounts (OAuth), and can ask about
anyone on their team by name, including follow-ups ("what about her PRs?", "and
Sarah too?") and time-scoped questions ("what did Mike ship yesterday?").

## How it works

- **Backend** — FastAPI (Python), async throughout
  - `jira_client.py` / `github_client.py` — REST clients with retry/backoff for
    rate limits, distinct from auth failures
  - `users.py` — resolves a display name to a Jira account ID + GitHub username,
    live on first ask, cached for 24h after
  - `activity.py` — fetches one person's Jira + GitHub activity concurrently
  - `chat.py` — an OpenAI function-calling loop: the model decides when it needs
    facts about someone (via a single `get_activity_for_people` tool), and answers
    only from what that tool returns — never invents tickets, commits, or people.
    Responses stream token-by-token over SSE.
  - `oauth_github.py` / `oauth_jira.py` / `auth_routes.py` / `db.py` — per-user
    OAuth (GitHub OAuth App, Jira 3LO) with a Supabase-backed session store
- **Frontend** — React (Vite), a single chat view with per-provider connection status

See [`TRADEOFFS.md`](TRADEOFFS.md) for the reasoning behind these choices (and the
ones considered and rejected), and [`TESTING.md`](TESTING.md) for how the test
suites are organized.

## Running locally

### Prerequisites

- Python 3.9+, Node 18+
- A Supabase project (for session/message storage) with `sessions`, `messages`, and
  `team_members` tables matching the columns read/written in `backend/app/db.py`
  (there's no migrations folder in this repo yet — the schema currently only lives
  in the deployed Supabase project; see the "another week" list in `TRADEOFFS.md`)
- A GitHub OAuth App and a Jira (Atlassian) OAuth 2.0 (3LO) app, each with a
  redirect URI pointing at your backend (e.g. `http://localhost:8000/auth/github/callback`
  and `http://localhost:8000/auth/jira/callback`)
- An OpenAI API key

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```bash
# Supabase
SUPABASE_URL=
SUPABASE_SECRET_KEY=

# GitHub OAuth App
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback

# Jira OAuth 2.0 (3LO)
JIRA_OAUTH_CLIENT_ID=
JIRA_OAUTH_CLIENT_SECRET=
JIRA_OAUTH_REDIRECT_URI=http://localhost:8000/auth/jira/callback

# OpenAI
OPENAI_API_KEY=

# Frontend origin (used for CORS + cookie SameSite/Secure decisions —
# see the comment in auth_routes.py). Defaults to http://localhost:5173 if unset.
FRONTEND_URL=http://localhost:5173
```

`backend/.env.local` (git-ignored) can override any of these for local dev without
touching values meant for production.

Run it:

```bash
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

By default the frontend talks to `http://localhost:8000`. To point it elsewhere,
set `VITE_API_URL` (e.g. in `frontend/.env.local`).

### Using it

1. Open the frontend, connect Jira and GitHub (top of the page).
2. Ask something like "What is Sarah working on this week?"

## Testing

```bash
# backend — 93 tests, all mocked at the network boundary
cd backend && source .venv/bin/activate && python3 -m pytest tests/ -v

# frontend — 12 tests, jsdom + mocked fetch
cd frontend && npx vitest run
```

See [`TESTING.md`](TESTING.md) for what each suite covers.

## Deployment

Deployed on **Render** (backend) + **Vercel** (frontend); `frontend/vercel.json`
proxies `/api/*` to the Render backend so both appear same-origin to the browser.
Set the same environment variables listed above on Render, plus `FRONTEND_URL` set
to the deployed Vercel origin so CORS and cross-site cookies work correctly.

`TRADEOFFS.md` covers why Render + Vercel over the originally-planned AWS App
Runner + Amplify path, and what that trade costs (Render free tier cold-starts).
