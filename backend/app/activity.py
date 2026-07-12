from __future__ import annotations

import asyncio

from app import github_client, jira_client


class UserNotFoundError(Exception):
    """Raised when a display name has no entry in the users.py lookup."""


async def get_user_activity(session_id: str, jira_account_id: str, github_username: str | None) -> dict:
    """Fetches JIRA issues + GitHub commits/PRs/repos for one resolved user, concurrently.

    github_username is None when a person resolved via Jira but has no known
    GitHub account — their activity is Jira-only rather than an error.
    """
    if github_username is None:
        issues = await jira_client.get_jira_issues(session_id, jira_account_id)
        return {"jira_issues": issues, "github_commits": None, "github_pull_requests": None, "github_repos": []}

    issues, repos = await asyncio.gather(
        jira_client.get_jira_issues(session_id, jira_account_id),
        github_client.get_recent_repos(session_id),
    )
    commits, pull_requests = await asyncio.gather(
        github_client.get_recent_commits(session_id, github_username, repos=repos),
        github_client.get_open_pull_requests(session_id, github_username, repos=repos),
    )
    return {
        "jira_issues": issues,
        "github_commits": commits,
        "github_pull_requests": pull_requests,
        "github_repos": repos,
    }
