# Team Activity Monitor — Build Checklist

A 2-day sprint to build a chatbot that answers **"What is [member] working on these days?"** using JIRA + GitHub data.

**Guiding principle:** build a thin end-to-end slice first (one API → one hardcoded name → a printed answer), then widen it. Don't perfect one integration before starting the other, and don't build UI before the core works.

**Key decisions (settled for this build):**
- [ ] Backend: **FastAPI** (Python) — async lets you fetch JIRA + GitHub concurrently
- [ ] Frontend: **React** — build CLI first, then layer React on top
- [ ] Response generation: **templates** first (reliable), LLM API as a stretch goal
- [ ] Deploy target: **AWS App Runner (backend) + Amplify Hosting (frontend)** — see Phase 7
- [ ] Guardrail: if AWS setup eats >~half a day, ship on a fallback and narrate the tradeoff in the demo

---

## Phase 0 — Setup (~1 hour)

- [x] Pick stack and commit to it
- [x] Initialize repo with the target folder structure (see below)
- [x] Create `.env` for secrets
- [ ] Add `.env` to `.gitignore` **before writing any API code**
- [ ] Verify JIRA URL + token work with a single `curl`
- [ ] Verify GitHub token works with a single `curl`
- [ ] Install dependencies and confirm the project runs (empty entrypoint is fine)

## Phase 1 — JIRA integration, in isolation (Day 1 morning)

- [ ] Authenticate to JIRA (API token / basic auth)
- [ ] Make one successful API call
- [ ] Fetch assigned issues for a **hardcoded** username
- [ ] Extract only needed fields: issue key, summary, status, last updated
- [ ] Print raw result and sanity-check it
- [ ] Wrap in a clean function (e.g. `get_jira_issues(username)`)

## Phase 2 — GitHub integration, in isolation (Day 1 afternoon)

- [ ] Authenticate to GitHub (personal access token)
- [ ] Make one successful API call
- [ ] Fetch recent commits for a hardcoded username
- [ ] Fetch open pull requests
- [ ] Fetch recently contributed-to repositories
- [ ] Extract useful fields and print them
- [ ] **Day 1 goal:** two separate modules, each returning clean data for a known user

## Phase 3 — Wire them together (Day 2 morning)

- [ ] Build query parser: extract a name from "What is John working on?"
- [ ] Handle multiple question phrasings (e.g. "Show me Sarah's current issues")
- [ ] Map display name → JIRA account ID + GitHub username (small lookup dict)
- [ ] Build response generator (start with templates)
- [ ] Combine JIRA + GitHub data into one coherent, conversational answer
- [ ] (Stretch) Swap template for LLM API call if time allows

## Phase 4 — Interface (Day 2 afternoon)

- [ ] Build CLI loop: read question → print answer (proves the core works)
- [ ] Expose a FastAPI endpoint (e.g. `POST /ask`) returning the answer as JSON
- [ ] Build React frontend: input box + answer area (Vite is fine; keep it minimal)
- [ ] Wire frontend → backend endpoint
- [ ] Configure CORS on FastAPI to allow the frontend origin

## Phase 5 — Error handling

- [ ] Handle **user not found** gracefully
- [ ] Handle **user with no recent activity** gracefully
- [ ] Handle API/network failures without crashing

## Phase 6 — Polish & demo prep (end of Day 2)

- [ ] Run all required test cases end to end (see below)
- [ ] Write `README.md`: setup steps, adding tokens, how to run
- [ ] Remove debug prints; tidy comments
- [ ] Confirm no secrets are committed
- [ ] Prepare demo: 3 min code walkthrough / 7 min live queries / 3 min challenges / 2 min Q&A
- [ ] Capture backup screenshots or a recording in case live APIs flake

## Phase 7 — Deploy to AWS (only after the app works locally)

> Deploying to a real URL is the "stand out" move and enterprise-realistic for an FDE role
> (customers are overwhelmingly AWS shops). But protect the deliverable: a working demo on a
> fallback beats a half-finished AWS setup with nothing to show.

**Backend — App Runner (persistent container, auto HTTPS, no timeout/cold-start pain):**
- [ ] Write a `Dockerfile` for the FastAPI app (Uvicorn on the port App Runner expects, e.g. 8080)
- [ ] Test the container locally: `docker build` + `docker run`, hit the endpoint
- [ ] Create an ECR repository and push the image
- [ ] Create an IAM role granting App Runner access to pull from ECR
- [ ] Create the App Runner service pointing at the image; confirm the live URL responds
- [ ] Set JIRA/GitHub tokens as App Runner environment variables (never bake into the image)

**Frontend — Amplify Hosting (Git-based, closest to a Vercel workflow):**
- [ ] Connect the repo to Amplify Hosting; confirm the auto-build succeeds
- [ ] Point the frontend at the App Runner backend URL (env var, not hardcoded)
- [ ] Update backend CORS to allow the deployed frontend origin
- [ ] (Bonus) Attach a custom domain — the real-URL signal is worth the few clicks

**Fallback guardrail:**
- [ ] Set a hard time-box (e.g. stop AWS debugging after ~half a day)
- [ ] If blocked, ship on a simpler host and note it in the demo as a deliberate tradeoff

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

## Target folder structure

```
project/
├── backend/
│   ├── app/
│   │   ├── jira_client.py         # JIRA API integration
│   │   ├── github_client.py       # GitHub API integration
│   │   ├── query_parser.py        # Extract user names from queries
│   │   ├── response_generator.py  # Format responses
│   │   ├── users.py               # Name → JIRA/GitHub identifier lookup
│   │   └── main.py                # FastAPI app + /ask endpoint
│   ├── cli.py                     # CLI loop (build/demo this first)
│   ├── requirements.txt
│   ├── Dockerfile                 # For App Runner
│   └── .env                       # Secrets — never commit
├── frontend/                      # React app (Vite)
│   └── src/
├── .gitignore                     # Must include .env
└── README.md                      # Setup + deployment notes
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