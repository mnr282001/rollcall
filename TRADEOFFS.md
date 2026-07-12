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

## Name → identifier mapping (`users.py`) — from static dict to dynamic resolution

Started with a static hardcoded dict (one real display name → Jira `account_id` +
GitHub username), which meant any name not manually pre-registered — even a real,
active Jira user with a real assigned task — incorrectly reported "I don't know
anyone named X." That's the wrong failure mode: a real teammate assigned real work
should never require someone to hand-edit a Python dict first.

**Fix:** `users.resolve_user(session_id, name)` now checks a `team_members` cache
first, and on a miss, resolves live:
- **Jira** via `/rest/api/3/users/search`, restricted to active `atlassian`-type
  accounts, matched by exact display name or (if unambiguous) a whole-word match.
- **GitHub** by listing the session's own org memberships (`/user/orgs`) and
  searching those orgs' members by profile display name — a person with no GitHub
  match still resolves via Jira alone, with an explicit "no linked GitHub account"
  note rather than a false "no activity."

Whatever resolves gets cached into `team_members` so the next query for the same
name is instant — `POST /admin/users` still exists for manual overrides (e.g. a
display-name mismatch between Jira and GitHub).

**Real bug caught while building this:** Jira's `/users/search?query=` is not a
reliable filter — a query matching nobody returns the *entire user directory*
instead of an empty list. An early version took "the first candidate" as a
best-effort guess, which meant literally any unmatched name (including nonsense
strings) silently resolved to the wrong person. Fixed by requiring an exact or
unambiguous whole-word display-name match client-side, with no closest-guess
fallback — an ambiguous name (e.g. two real people sharing a last name) now
correctly returns "I don't know," rather than confidently showing the wrong
person's data.

**Real limitation found, not a bug:** GitHub org-scoped resolution only works for
accounts that belong to at least one org — the test account here has zero org
memberships (confirmed via GitHub's API directly, not a scope issue), so any name
without a cached mapping resolves Jira-only until a real org is in play.

## `team_members` cache TTL

The `team_members` cache had no expiry — once a name resolved, that Jira
`account_id`/GitHub username mapping was permanent, so a display-name change,
account deactivation, or someone else being renamed to match would silently go
stale forever with no way to notice.

**Options considered:**
- **No TTL, manual invalidation only** (via `POST /admin/users`) — simplest, but
  relies on someone remembering to fix a stale mapping after the fact.
- **24-hour TTL** (chosen) — a `resolved_at` timestamp column; `resolve_user()`
  treats a cached row older than 24h as stale and re-resolves live, refreshing the
  timestamp on success. If the live re-resolution fails (Jira/GitHub unreachable),
  it falls back to serving the stale cached row rather than surfacing an error or
  refusing to answer — a day-old mapping is still more useful than an
  outage-triggered "I don't know this person."
- **Re-validate on every query, no cache** — always fresh, but reintroduces the
  expensive part of GitHub resolution (list org members, then one profile fetch
  per member) on every single question, which doesn't scale with org size or
  query volume.

**Why 24h:** team/display-name changes are infrequent enough that daily freshness
catches real drift quickly without meaningfully increasing API load. Verified all
three paths against real data: a fresh cache hit skips live resolution entirely: a
stale hit re-resolves and refreshes `resolved_at`; and a stale hit under a
simulated Jira outage still returns the last-known-good mapping instead of
failing the query.

## Chat send latency: streaming + parallel GitHub fetches

Clicking "send" felt slow because the UI showed nothing until the *entire*
backend round trip — including the full non-streamed OpenAI completion —
finished, and `github_client.py` fetched each of the (up to 5) recently-pushed
repos' commits/PRs one at a time instead of concurrently.

**Fix 1 — stream the OpenAI response end-to-end.** `chat.py`'s
`handle_message` became `stream_message`, using `AsyncOpenAI` with
`stream=True` and yielding content chunks as they're generated. `POST /chat`
now returns a `StreamingResponse` instead of a buffered JSON body, and the
frontend reads it incrementally via `response.body.getReader()`, appending
each chunk to the assistant bubble as it arrives instead of waiting for
`response.json()`.

**Cost:** config errors (missing `OPENAI_API_KEY`) must be checked *before*
the stream starts (`chat.ensure_configured()`), since HTTP headers are
already committed once streaming begins — can't cleanly turn a mid-stream
failure into a 500 anymore, only fall back to error text inline. The
tool-calling hop (deciding *whether* to look up a teammate) still streams
nothing — only the final answer-generating hop produces content — so a
question that triggers a lookup still has a silent gap before anything
appears. Showing a "checking Jira/GitHub…" indicator during that hop was
considered but skipped as UI complexity beyond this pass.

**Fix 2 — parallelize per-repo GitHub calls.** `get_recent_commits` and
`get_open_pull_requests` looped over repos sequentially (`for repo in repos:
await ...`); both now fan out with `asyncio.gather`.

**Cost:** more concurrent outbound requests to GitHub per chat turn — fine
at `_RECENT_REPOS_LIMIT = 5`, but would need a semaphore if that limit grows
a lot.

**Deliberately not fixed this pass:**
- The two sequential LLM round trips inherent to OpenAI function-calling
  (decide-to-call-tool, then compose-answer) — streaming softens this but
  doesn't remove the first call's latency.
- Serial, blocking `db.add_message` calls per turn (`db.py` is a sync
  Supabase client called directly from async code, not even via
  `asyncio.to_thread`) — a smaller contributor than the two fixes above.
- No caching of repo/commit/PR data across turns in the same session.

## What we'd do with another week

- Real multi-user mapping (see above) instead of a single hardcoded identity
- Caching (GitHub/JIRA rate limits are the real ceiling under concurrent/repeated
  queries)
- LLM-based response generation for open-ended follow-up questions
- Broader test coverage for `query_parser.py`'s phrasing patterns
