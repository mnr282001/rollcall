# Graph Report - .  (2026-07-17)

## Corpus Check
- Corpus is ~16,443 words - fits in a single context window. You may not need a graph.

## Summary
- 407 nodes · 568 edges · 37 communities (26 shown, 11 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 33 edges (avg confidence: 0.79)
- Token cost: 151,074 input · 0 output

## Community Hubs (Navigation)
- Activity Aggregation
- Auth & Query Wiring
- Chat Assistant (LLM)
- Chat Tests
- Jira Client
- FastAPI Main App
- DB Layer Tests
- Frontend Lint Config
- Frontend Dev Dependencies
- Frontend Runtime Dependencies
- Session DB Layer
- Jira OAuth
- Jira OAuth Tests
- Auth Routes
- GitHub Client Tests
- User Lookup Tests
- Frontend Entry & Branding
- Jira Client Tests
- Icon Sprite Assets
- Brand Identity
- Oxlint Docs Notes
- Vercel Config
- Pytest Dependency
- Pytest Asyncio Dependency
- Python Dotenv Dependency
- Uvicorn Dependency
- FDE Polish Checklist Item
- Error Handling Checklist Item
- Demo Prep Checklist Item
- Vite Logo Asset

## God Nodes (most connected - your core abstractions)
1. `_install_fake_client()` - 15 edges
2. `_get_client()` - 14 edges
3. `_request()` - 11 edges
4. `_request()` - 10 edges
5. `_activity_facts()` - 8 edges
6. `stream_message()` - 7 edges
7. `Target folder structure` - 7 edges
8. `GitHubError` - 6 edges
9. `JiraError` - 6 edges
10. `_FakeQuery` - 6 edges

## Surprising Connections (you probably didn't know these)
- `test_db.py` --references--> `supabase==2.30.1`  [AMBIGUOUS]
  TESTING.md → backend/requirements.txt
- `src/main.jsx (app entry script)` --shares_data_with--> `App.test.jsx`  [INFERRED]
  frontend/index.html → TESTING.md
- `Decisions log` --references--> `Templates vs. LLM for response generation`  [EXTRACTED]
  checklist.md → TRADEOFFS.md
- `Decisions log` --references--> `Name to identifier mapping (users.py) - static dict to dynamic resolution`  [EXTRACTED]
  checklist.md → TRADEOFFS.md
- `Phase 0 - Setup` --references--> `fastapi==0.128.8`  [INFERRED]
  checklist.md → backend/requirements.txt

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Per-user OAuth authentication flow (JIRA + GitHub)** — backend_app_oauth_github, backend_app_oauth_jira, backend_app_auth_routes, backend_app_db, testing_test_oauth_github, testing_test_oauth_jira, testing_test_auth_routes [INFERRED 0.85]
- **Concurrent JIRA+GitHub activity fetch pattern** — backend_app_activity, backend_app_jira_client, backend_app_github_client, tradeoffs_concurrent_vs_sequential_fetches [INFERRED 0.85]
- **Chat streaming implementation and its test coverage** — backend_app_chat, testing_test_chat, testing_test_main, testing_app_test_jsx [INFERRED 0.85]

## Communities (37 total, 11 thin omitted)

### Community 0 - "Activity Aggregation"
Cohesion: 0.09
Nodes (34): get_user_activity(), Exception, Fetches JIRA issues + GitHub commits/PRs/repos for one resolved user, concurrent, Raised when a display name has no entry in the users.py lookup., UserNotFoundError, _do_request(), find_user_by_name(), get_open_pull_requests() (+26 more)

### Community 1 - "Auth & Query Wiring"
Cohesion: 0.07
Nodes (28): main.py, query_parser.py, response_generator.py, _as_user_dict(), _is_stale(), Resolves a display name to Jira/GitHub identifiers.      Checks the team_members, resolve_user(), fastapi==0.128.8 (+20 more)

### Community 2 - "Chat Assistant (LLM)"
Cohesion: 0.10
Nodes (31): AsyncOpenAI, _activity_facts(), _current_date(), ensure_configured(), _execute_get_activity(), _get_client(), _in_window(), _local_date() (+23 more)

### Community 3 - "Chat Tests"
Cohesion: 0.14
Nodes (24): _fake_stream(), _install_fake_openai(), test_activity_facts_no_linked_github_has_none_commits_and_prs(), test_activity_facts_no_window_returns_everything(), test_activity_facts_shapes_full_person_with_github(), test_activity_facts_windows_to_the_requested_day_only(), test_execute_get_activity_applies_start_and_end_date(), test_execute_get_activity_maps_activity_fetch_errors() (+16 more)

### Community 4 - "Jira Client"
Cohesion: 0.11
Nodes (27): _do_request(), fetch_assigned_issues_raw(), find_user_by_name(), get_jira_issues(), _get_valid_access_token(), JiraAuthError, JiraConnectionError, JiraError (+19 more)

### Community 5 - "FastAPI Main App"
Cohesion: 0.11
Nodes (13): add_user(), AddUserRequest, chat_endpoint(), chat_history(), ChatRequest, lifespan(), Request, _require_session() (+5 more)

### Community 6 - "DB Layer Tests"
Cohesion: 0.15
Nodes (17): _FakeClient, _FakeQuery, _install_fake_client(), Minimal stand-in for supabase-py's fluent query builder.      Every builder meth, test_add_message_inserts_all_fields(), test_add_team_member_upserts_lowercased_name(), test_clear_github_token_sets_none(), test_clear_jira_tokens_sets_all_none() (+9 more)

### Community 7 - "Frontend Lint Config"
Cohesion: 0.11
Nodes (11): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema, App(), defaultHistory, defaultStatus (+3 more)

### Community 8 - "Frontend Dev Dependencies"
Cohesion: 0.10
Nodes (21): devDependencies, jsdom, oxlint, @testing-library/jest-dom, @testing-library/react, @testing-library/user-event, @types/react, @types/react-dom (+13 more)

### Community 9 - "Frontend Runtime Dependencies"
Cohesion: 0.10
Nodes (19): dependencies, react, react-dom, react-markdown, remark-gfm, name, private, scripts (+11 more)

### Community 10 - "Session DB Layer"
Cohesion: 0.19
Nodes (17): add_message(), add_team_member(), clear_github_token(), clear_jira_tokens(), create_session(), delete_messages(), _get_client(), get_messages() (+9 more)

### Community 11 - "Jira OAuth"
Cohesion: 0.15
Nodes (10): exchange_code_for_tokens(), get_cloud_id(), is_token_expired(), Returns (access_token, refresh_token)., Returns a new (access_token, refresh_token) using a stored refresh token., Decodes the JWT's exp claim locally (no signature check needed — we're only, The first accessible Jira site's cloudId (fine for a single-workspace demo)., refresh_access_token() (+2 more)

### Community 13 - "Jira OAuth Tests"
Cohesion: 0.21
Nodes (4): _fake_jwt(), test_is_token_expired_false_for_future_exp(), test_is_token_expired_true_for_past_exp(), test_is_token_expired_true_within_leeway_window()

### Community 14 - "Auth Routes"
Cohesion: 0.29
Nodes (7): github_callback(), github_logout(), jira_callback(), jira_logout(), me(), Request, test_auth_routes.py

### Community 15 - "GitHub Client Tests"
Cohesion: 0.36
Nodes (6): _response(), test_403_without_rate_limit_header_raises_auth_error_immediately(), test_backoff_honors_retry_after_header(), test_raises_rate_limit_error_after_exhausting_retries(), test_retries_on_429_then_succeeds(), test_retries_on_primary_rate_limit_then_succeeds()

### Community 16 - "User Lookup Tests"
Cohesion: 0.33
Nodes (5): _row(), test_connection_error_falls_back_to_stale_cache(), test_fresh_cache_hit_returned_without_live_lookup(), test_github_connection_error_falls_back_to_stale_cache(), test_stale_cache_triggers_live_resolution_and_recaches()

### Community 17 - "Frontend Entry & Branding"
Cohesion: 0.22
Nodes (9): Fraunces / IBM Plex Mono / IBM Plex Sans (Google Fonts), frontend/index.html (Vite entry HTML), Rollcall (product name), Vite (build tool), @vitejs/plugin-react (Oxc), @vitejs/plugin-react-swc (SWC), src/main.jsx (app entry script), App.test.jsx (+1 more)

### Community 18 - "Jira Client Tests"
Cohesion: 0.39
Nodes (5): _response(), test_403_still_raises_auth_error_immediately(), test_backoff_honors_retry_after_header(), test_raises_rate_limit_error_after_exhausting_retries(), test_retries_on_429_then_succeeds()

### Community 19 - "Icon Sprite Assets"
Cohesion: 0.52
Nodes (7): icons.svg (Icon Sprite Sheet), Bluesky Icon Symbol, Discord Icon Symbol, Documentation Icon Symbol, GitHub Icon Symbol, Social (Contacts/Network) Icon Symbol, X (Twitter) Icon Symbol

## Ambiguous Edges - Review These
- `test_db.py` → `supabase==2.30.1`  [AMBIGUOUS]
  TESTING.md · relation: references

## Knowledge Gaps
- **57 isolated node(s):** `$schema`, `oxc`, `react/rules-of-hooks`, `warn`, `name` (+52 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `test_db.py` and `supabase==2.30.1`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `Shared token vs. per-user OAuth` connect `Auth & Query Wiring` to `Session DB Layer`, `Jira OAuth`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `Target folder structure` connect `Auth & Query Wiring` to `Activity Aggregation`, `Jira Client`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `ZoneInfo` (e.g. with `test_activity_facts_no_linked_github_has_none_commits_and_prs()` and `test_activity_facts_no_window_returns_everything()`) actually correct?**
  _`ZoneInfo` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `$schema`, `oxc`, `react/rules-of-hooks` to the rest of the system?**
  _57 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Activity Aggregation` be split into smaller, more focused modules?**
  _Cohesion score 0.08888888888888889 - nodes in this community are weakly interconnected._
- **Should `Auth & Query Wiring` be split into smaller, more focused modules?**
  _Cohesion score 0.07386363636363637 - nodes in this community are weakly interconnected._