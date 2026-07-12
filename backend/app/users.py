from __future__ import annotations

from app import db, github_client, jira_client


async def resolve_user(session_id: str, name: str) -> dict | None:
    """Resolves a display name to Jira/GitHub identifiers.

    Checks the team_members cache first. On a miss, looks the name up live
    against the session's real Jira workspace (and, if the session belongs to
    any GitHub orgs, those orgs' members too), then caches whatever it finds
    so the next query for the same name is instant. A person with no GitHub
    match still resolves — they just get Jira-only activity.
    """
    row = db.get_team_member(name)
    if row:
        return {"jira_account_id": row["jira_account_id"], "github_username": row["github_username"]}

    jira_account_id = await jira_client.find_user_by_name(session_id, name)
    if not jira_account_id:
        return None

    github_username = await github_client.find_user_by_name(session_id, name)
    db.add_team_member(name, jira_account_id, github_username)
    return {"jira_account_id": jira_account_id, "github_username": github_username}
