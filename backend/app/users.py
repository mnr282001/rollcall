from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db, github_client, jira_client

_CACHE_TTL = timedelta(hours=24)


def _as_user_dict(row: dict) -> dict:
    return {"jira_account_id": row["jira_account_id"], "github_username": row["github_username"]}


def _is_stale(row: dict) -> bool:
    resolved_at = datetime.fromisoformat(row["resolved_at"])
    return datetime.now(timezone.utc) - resolved_at > _CACHE_TTL


async def resolve_user(session_id: str, name: str) -> dict | None:
    """Resolves a display name to Jira/GitHub identifiers.

    Checks the team_members cache first. A cache hit younger than 24h is
    returned as-is. Otherwise (cache miss, or a hit older than 24h) resolves
    live against the session's real Jira workspace (and, if the session
    belongs to any GitHub orgs, those orgs' members too), then caches
    whatever it finds so the next query is instant again. A person with no
    GitHub match still resolves — they just get Jira-only activity.

    If a live re-resolution fails because Jira/GitHub is unreachable, a stale
    cached row is served rather than surfacing an error — a day-old mapping is
    still more useful than an outage-triggered "I don't know this person."
    """
    row = db.get_team_member(name)
    if row and not _is_stale(row):
        return _as_user_dict(row)

    try:
        jira_account_id = await jira_client.find_user_by_name(session_id, name)
        if not jira_account_id:
            return None
        github_username = await github_client.find_user_by_name(session_id, name)
    except (jira_client.JiraConnectionError, github_client.GitHubConnectionError):
        if row:
            return _as_user_dict(row)
        raise

    db.add_team_member(name, jira_account_id, github_username)
    return {"jira_account_id": jira_account_id, "github_username": github_username}
