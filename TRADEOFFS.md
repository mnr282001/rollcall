# Technical Decisions & Tradeoffs

Kept alongside `checklist.md` as the source for the demo's "technical decisions" and
"technical challenges" segments.

## Shared token vs. per-user OAuth

Pivoted from one shared service-account credential to real per-user OAuth for both
JIRA (3LO) and GitHub (OAuth App), because a real FDE-style tool needs each user
authenticating with their own identity, not a shared token.

**Cost:** external app registration for both providers, a SQLite session store
(`backend/app/db.py`), CSRF `state` cookies on both login flows, a JIRA scope
propagation quirk, and JIRA's proactive JWT-expiry check (its `/search/jql` endpoint
silently returns empty results for a stale token instead of `401`ing).

**Verdict:** worth it for correctness — the alternative doesn't represent multiple
real users at all. Good "technical challenge" story for the demo.

## GitHub OAuth App tokens vs. GitHub App tokens (no refresh logic needed)

Verified against GitHub's docs before assuming: classic OAuth App tokens (`gho_...`,
what `oauth_github.py` implements) do **not** expire by default and never return a
refresh token in the exchange response. Token expiration is a GitHub *App*-specific
opt-in feature (8-hour token, 6-month refresh token) — not something classic OAuth
Apps support at all.

**Verdict:** correctly skipped porting JIRA's proactive-expiry-check pattern to
`github_client.py`. If this ever migrates to a GitHub App, that logic would need to
come back.

## Repo-scoped GitHub queries vs. a global "all activity" endpoint

GitHub has no single endpoint for "everything a user worked on" across all repos.
Chose: `GET /user/repos?sort=pushed` for the top 5 recently-pushed repos, then fan
out per-repo for commits (`author=` filter) and open PRs (client-side filter, since
the PRs-list endpoint has no author param).

**Alternative considered:** GitHub's Search API (`search/commits`, `search/issues`)
for one global query per data type. Rejected for this build — separate, tighter
rate limits and indexing lag, and the per-repo approach lines up with "recently
contributed-to repositories" being a first-class piece of data we need anyway.

**Cost:** results are bounded to the top N pushed repos, so very old but still-open
PRs in a repo that hasn't been pushed to recently would be missed.

## Templates vs. LLM for response generation

Started with `response_generator.py` as plain string templates: reliable, zero
latency, zero cost, deterministic for demo/test purposes. No LLM call yet.

**When to flip:** once the template needs to handle more phrasings of "what does this
data mean" than templates can reasonably cover (e.g. summarizing *why* someone's
activity looks a certain way, or answering follow-up questions) — that's a stretch
goal in `checklist.md` Phase 3, not yet implemented.

## Concurrent vs. sequential fetches

Converted `jira_client.py` and `github_client.py` from sync `httpx.request` to
`httpx.AsyncClient`, so `activity.py` can fetch JIRA issues and the GitHub repo list
concurrently via `asyncio.gather`, then fetch commits + PRs concurrently against the
already-fetched repo list.

**Why it mattered in practice:** the naive first pass called `get_recent_repos`
three times (once directly, once inside `get_recent_commits`, once inside
`get_open_pull_requests`) even after gathering concurrently — concurrency doesn't
fix redundant work. Fixed by threading an optional `repos` param through so the repo
list is fetched once and reused. Real measured latency for one full user-activity
fetch (9 JIRA issues + 20 commits + repo list): ~2.7s.

## Name → identifier mapping (`users.py`)

Per-user OAuth means only one real authenticated identity exists in this build (see
above). `users.py` maps one real display name to a real JIRA `account_id` + GitHub
username; every other name a query might mention (John, Sarah, Mike from the
required test cases) has no entry and deliberately falls through to the
"user not found" path — reusing that gap as one of the required error-handling test
cases rather than fabricating fake data for it.

**What a multi-user version would need:** each teammate completing their own OAuth
flow, and a way to resolve "whose stored token do we use to look up teammate X's
activity" (JIRA/GitHub both allow querying visible-but-not-self users with your own
token, so one logged-in session can answer questions about teammates — this just
isn't seeded with more than one real mapping yet).

## What we'd do with another week

- Real multi-user mapping (see above) instead of a single hardcoded identity
- Caching (GitHub/JIRA rate limits are the real ceiling under concurrent/repeated
  queries)
- LLM-based response generation for open-ended follow-up questions
- Broader test coverage for `query_parser.py`'s phrasing patterns
