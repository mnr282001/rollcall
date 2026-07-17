# Team Activity Monitor — Build Checklist

A 2-day sprint to build a chatbot that answers **"What is [member] working on these days?"** using JIRA + GitHub data.

**Guiding principle:** build a thin end-to-end slice first (one API → one hardcoded name → a printed answer), then widen it. Don't perfect one integration before starting the other, and don't build UI before the core works.

**Key decisions (settled for this build):**
- [x] Backend: **FastAPI** (Python) — async lets you fetch JIRA + GitHub concurrently
- [x] Frontend: **React** — build CLI first, then layer React on top
- [x] Response generation: **templates** first, then flipped to **LLM function-calling**
      (`chat.py`) once templates couldn't handle follow-ups/pronouns — see `TRADEOFFS.md`
- [x] Deploy target: **Render (backend) + Vercel (frontend)** — pivoted from the
      original AWS App Runner/Amplify plan to stay inside the time-box; see `TRADEOFFS.md`
- [x] Guardrail: if AWS setup eats >~half a day, ship on a fallback and narrate the tradeoff in the demo

---

## Phase 0 — Setup (~1 hour)

- [x] Pick stack and commit to it
- [x] Initialize repo with the target folder structure (see below)
- [x] Create `.env` for secrets
- [x] Add `.env` to `.gitignore` **before writing any API code**
- [x] Verify JIRA URL + token work with a single `curl`
- [ ] ~~Verify GitHub token works with a single `curl`~~ — superseded, see auth pivot note below
- [x] Install dependencies and confirm the project runs (empty entrypoint is fine)

> **Architecture pivot (post-Phase-1):** mid-build we upgraded from a single shared
> service-account credential to **real per-user OAuth** for both providers, since a
> real FDE-style tool needs each user authenticating with their own Jira/GitHub
> identity, not one shared token. This is a bigger scope item than the original
> checklist assumed — see `backend/app/oauth_jira.py`, `backend/app/oauth_github.py`,
> `backend/app/auth_routes.py`, and `backend/app/db.py` (SQLite session store).
> Phase 2's "personal access token" line is now stale; GitHub auth is OAuth too.

## Phase 1 — JIRA integration, in isolation (Day 1 morning)

- [x] Authenticate to JIRA (~~API token / basic auth~~ → **OAuth 2.0 3LO**, per-user)
- [x] Make one successful API call
- [x] Fetch assigned issues for a **hardcoded** username (now: hardcoded `account_id`, real value tested end-to-end)
- [x] Extract only needed fields: issue key, summary, status, last updated
- [x] Print raw result and sanity-check it
- [x] Wrap in a clean function (`get_jira_issues(session_id, account_id)`)
- [x] *(added, not originally listed)* OAuth login/callback routes, SQLite session store, CSRF `state` cookie
- [x] *(added, not originally listed)* Automatic refresh-token handling — proactively checks the JWT `exp` claim before each call, since Jira's search endpoint silently returns empty results for a stale token instead of `401`ing

## Phase 2 — GitHub integration, in isolation (Day 1 afternoon)

- [x] Authenticate to GitHub (~~personal access token~~ → **OAuth App**, per-user) — login/callback already built in `backend/app/oauth_github.py` / `auth_routes.py`, confirmed working live
- [x] Make one successful API call fetching real user data (beyond the OAuth token exchange itself)
- [x] Fetch recent commits for a hardcoded username
- [x] Fetch open pull requests
- [x] Fetch recently contributed-to repositories
- [x] Extract useful fields and print them
- [x] **Day 1 goal:** two separate modules, each returning clean data for a known user

## Phase 3 — Wire them together (Day 2 morning)

- [x] Build query parser: extract a name from "What is John working on?"
- [x] Handle multiple question phrasings (e.g. "Show me Sarah's current issues")
- [x] Map display name → JIRA account ID + GitHub username (small lookup dict)
- [x] Build response generator (start with templates)
- [x] Combine JIRA + GitHub data into one coherent, conversational answer
- [x] (Stretch) Swap template for LLM API call — done; templates (`response_generator.py`,
      `query_parser.py`) fully replaced by `chat.py`'s OpenAI function-calling loop

## Phase 4 — Interface (Day 2 afternoon)

- [x] Build CLI loop: read question → print answer (proves the core works)
- [x] Expose a FastAPI endpoint (e.g. `POST /ask`) returning the answer as JSON
- [x] Build React frontend: input box + answer area (Vite is fine; keep it minimal)
- [x] Wire frontend → backend endpoint
- [x] Configure CORS on FastAPI to allow the frontend origin

## Phase 5 — Error handling

- [x] Handle **user not found** gracefully
- [x] Handle **user with no recent activity** gracefully
- [x] Handle API/network failures without crashing

## Phase 6 — Polish & demo prep (end of Day 2)

- [ ] Run all required test cases end to end (see below)
- [ ] Write `README.md`: setup steps, adding tokens, how to run
- [ ] Remove debug prints; tidy comments
- [ ] Confirm no secrets are committed
- [ ] Prepare demo: 3 min code walkthrough / 7 min live queries / 3 min challenges / 2 min Q&A
- [ ] Capture backup screenshots or a recording in case live APIs flake

## Phase 7 — Deploy (only after the app works locally)

> Deploying to a real URL is the "stand out" move. Originally planned as AWS App
> Runner + Amplify (enterprise-realistic — customers are overwhelmingly AWS shops),
> but pivoted to **Render (backend) + Vercel (frontend)** to stay inside the
> time-box — no Dockerfile/ECR/IAM plumbing needed. See `TRADEOFFS.md` for the
> full reasoning; the AWS path is still the right answer to cite if asked how this
> would look for a real enterprise customer.

**Backend — Render:**
- [x] Deploy the FastAPI app to Render; confirm the live URL responds
  (`rollcall-backend-m9hv.onrender.com`)
- [x] Set JIRA/GitHub/Supabase/OpenAI secrets as Render environment variables
  (never baked into the image)

**Frontend — Vercel:**
- [x] Connect the repo to Vercel; confirm the auto-build succeeds
- [x] Proxy `/api/*` to the Render backend (`frontend/vercel.json` rewrite) so
  frontend and backend appear same-origin to the browser
- [x] Update backend CORS/cookie settings (`FRONTEND_URL`, `SameSite=None; Secure`
  once cross-site) to allow the deployed frontend origin
- [ ] (Bonus) Attach a custom domain

**Known cost of this path:** Render's free tier cold-starts after inactivity — see
`TRADEOFFS.md`.

---

## Required test cases

- [ ] "What is John working on these days?"
- [ ] "Show me recent activity for Sarah"
- [ ] "What has Mike been working on this week?"
- [ ] User with no recent activity
- [ ] User not found

## Bonus points (only after core works)

- [ ] Multiple question formats supported
- [ ] Nice UI design
- [ ] Extra insights (time estimates, priority levels)
- [ ] Performance (caching, concurrent requests)

---

## Actual folder structure

(Superseded the original planned layout above — `query_parser.py`/`response_generator.py`
were replaced by `chat.py`'s LLM function-calling, `cli.py` was dropped once the FastAPI
+ React path worked end to end, and OAuth/session-store modules were added mid-build —
see the architecture pivot note above.)

```
rollcall/
├── backend/
│   ├── app/
│   │   ├── jira_client.py       # JIRA API integration (+ retry/backoff)
│   │   ├── github_client.py     # GitHub API integration (+ retry/backoff)
│   │   ├── activity.py          # Concurrent Jira+GitHub fetch for one person
│   │   ├── chat.py              # OpenAI function-calling loop, streaming
│   │   ├── users.py             # Name → Jira/GitHub identifier resolution + cache
│   │   ├── db.py                # Supabase-backed sessions/messages/team_members
│   │   ├── oauth_github.py      # GitHub OAuth App flow
│   │   ├── oauth_jira.py        # Jira 3LO OAuth flow
│   │   └── auth_routes.py       # Login/callback/logout/me routes
│   ├── main.py                  # FastAPI app + /chat, /admin routes
│   ├── tests/                   # pytest, mocked network boundaries
│   ├── requirements.txt
│   └── .env / .env.local        # Secrets — never commit
├── frontend/                    # React app (Vite)
│   ├── src/
│   └── vercel.json              # Proxies /api/* to the Render backend
├── TRADEOFFS.md                 # Design decisions and what we'd change
├── TESTING.md                   # How the test suites are organized
├── .gitignore                   # Must include .env
└── README.md                    # Setup + deployment notes
```

## Evaluation weighting (keep these in view)

- Technical implementation — 50% (working integrations, clean structure, config management, no hardcoded secrets)
- Functionality — 30% (answers core question, handles errors, readable output)
- Problem-solving & efficiency — 20% (good use of the timeline, clear technical decisions)

---

## Decisions log (keep as you build — this IS your demo script)

For a forward deployed engineer role, the *reasoning* about tradeoffs is worth as much as the
code. The demo has explicit slots for "technical challenges" and "technical decisions" — win
them by being able to crisply justify each call and say when you'd choose differently. Jot a
line for each as you go:

- [ ] **Shared token vs. per-user OAuth** — pivoted from one service-account credential to real Jira 3LO + GitHub OAuth App per-user auth, since an FDE tool needs to represent each user's own identity; cost real time (external app registration, SQLite session store, a Jira scope propagation quirk, proactive JWT-expiry checking since Jira's search endpoint silently returns empty results instead of 401ing on a stale token) — worth it for correctness but a good "technical challenge" story
- [ ] **Templates vs. LLM** — why you chose it, and when you'd flip
- [ ] **App Runner vs. Lambda** — chose App Runner to avoid API Gateway/IAM plumbing eating the sprint; would move to Lambda for scale-to-zero cost or an existing serverless footprint
- [ ] **Concurrent vs. sequential fetches** — why (latency, and it's a listed bonus)
- [ ] **Name → identifier mapping** — how you handled JIRA vs. GitHub using different usernames
- [ ] **What you'd do with another week** — caching, auth, more query formats, tests
- [ ] **Biggest challenge hit + how you solved it** — have one concrete story ready

## FDE-flavored polish (what this role screens for)

- [ ] The output reads like something a real user would actually want (clean, conversational)
- [ ] "User not found" and "no recent activity" fail gracefully, not with a stack trace
- [ ] README explains how someone *else* would run it in *their* environment (tokens, config)
- [ ] You can explain the whole system top-to-bottom in ~3 minutes without notes
- [ ] Live on a real URL if AWS cooperated — otherwise a working fallback + a clear porting story