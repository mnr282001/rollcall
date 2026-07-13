from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app import activity, github_client, jira_client

_SESSION_ID = "session-1"
_ACCOUNT_ID = "account-1"


async def test_jira_only_when_no_github_username(monkeypatch):
    issues = [{"key": "AB-1"}]
    monkeypatch.setattr(jira_client, "get_jira_issues", AsyncMock(return_value=issues))
    get_repos = AsyncMock()
    monkeypatch.setattr(github_client, "get_recent_repos", get_repos)

    result = await activity.get_user_activity(_SESSION_ID, _ACCOUNT_ID, None)

    assert result == {
        "jira_issues": issues,
        "github_commits": None,
        "github_pull_requests": None,
        "github_repos": [],
    }
    get_repos.assert_not_called()


async def test_fetches_jira_and_github_concurrently_when_username_present(monkeypatch):
    issues = [{"key": "AB-1"}]
    repos = [{"full_name": "org/repo", "pushed_at": "2026-07-01T00:00:00Z", "private": False}]
    commits = [{"repo": "org/repo", "sha": "abc1234", "message": "fix", "date": "2026-07-01T00:00:00Z"}]
    pull_requests = [{"repo": "org/repo", "number": 1, "title": "PR", "updated_at": "2026-07-01T00:00:00Z"}]

    monkeypatch.setattr(jira_client, "get_jira_issues", AsyncMock(return_value=issues))
    monkeypatch.setattr(github_client, "get_recent_repos", AsyncMock(return_value=repos))
    get_commits = AsyncMock(return_value=commits)
    get_prs = AsyncMock(return_value=pull_requests)
    monkeypatch.setattr(github_client, "get_recent_commits", get_commits)
    monkeypatch.setattr(github_client, "get_open_pull_requests", get_prs)

    result = await activity.get_user_activity(_SESSION_ID, _ACCOUNT_ID, "nayab")

    assert result == {
        "jira_issues": issues,
        "github_commits": commits,
        "github_pull_requests": pull_requests,
        "github_repos": repos,
    }
    # repos fetched once and reused for both the commits and PR fan-out, not refetched
    get_commits.assert_awaited_once_with(_SESSION_ID, "nayab", repos=repos)
    get_prs.assert_awaited_once_with(_SESSION_ID, "nayab", repos=repos)


async def test_propagates_github_auth_error(monkeypatch):
    monkeypatch.setattr(jira_client, "get_jira_issues", AsyncMock(return_value=[]))
    monkeypatch.setattr(github_client, "get_recent_repos", AsyncMock(side_effect=github_client.GitHubAuthError("bad token")))

    with pytest.raises(github_client.GitHubAuthError):
        await activity.get_user_activity(_SESSION_ID, _ACCOUNT_ID, "nayab")


async def test_propagates_jira_rate_limit_error(monkeypatch):
    monkeypatch.setattr(
        jira_client, "get_jira_issues", AsyncMock(side_effect=jira_client.JiraRateLimitError("rate limited"))
    )
    monkeypatch.setattr(github_client, "get_recent_repos", AsyncMock(return_value=[]))

    with pytest.raises(jira_client.JiraRateLimitError):
        await activity.get_user_activity(_SESSION_ID, _ACCOUNT_ID, "nayab")
