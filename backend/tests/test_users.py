from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from app import db, github_client, jira_client, users

_SESSION_ID = "session-1"
_NAME = "Nayab"


def _row(hours_old: float, github_username: str | None = "nayab") -> dict:
    resolved_at = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    return {
        "jira_account_id": "account-1",
        "github_username": github_username,
        "resolved_at": resolved_at.isoformat(),
    }


async def test_fresh_cache_hit_returned_without_live_lookup(monkeypatch):
    monkeypatch.setattr(db, "get_team_member", lambda name: _row(hours_old=1))
    find_jira = AsyncMock()
    monkeypatch.setattr(jira_client, "find_user_by_name", find_jira)

    result = await users.resolve_user(_SESSION_ID, _NAME)

    assert result == {"jira_account_id": "account-1", "github_username": "nayab"}
    find_jira.assert_not_called()


async def test_stale_cache_triggers_live_resolution_and_recaches(monkeypatch):
    monkeypatch.setattr(db, "get_team_member", lambda name: _row(hours_old=25))
    monkeypatch.setattr(jira_client, "find_user_by_name", AsyncMock(return_value="account-2"))
    monkeypatch.setattr(github_client, "find_user_by_name", AsyncMock(return_value="nayab2"))
    add_team_member = Mock()
    monkeypatch.setattr(db, "add_team_member", add_team_member)

    result = await users.resolve_user(_SESSION_ID, _NAME)

    assert result == {"jira_account_id": "account-2", "github_username": "nayab2"}
    add_team_member.assert_called_once_with(_NAME, "account-2", "nayab2")


async def test_cache_miss_resolves_live(monkeypatch):
    monkeypatch.setattr(db, "get_team_member", lambda name: None)
    monkeypatch.setattr(jira_client, "find_user_by_name", AsyncMock(return_value="account-3"))
    monkeypatch.setattr(github_client, "find_user_by_name", AsyncMock(return_value=None))
    monkeypatch.setattr(db, "add_team_member", Mock())

    result = await users.resolve_user(_SESSION_ID, _NAME)

    assert result == {"jira_account_id": "account-3", "github_username": None}


async def test_no_jira_match_returns_none(monkeypatch):
    monkeypatch.setattr(db, "get_team_member", lambda name: None)
    monkeypatch.setattr(jira_client, "find_user_by_name", AsyncMock(return_value=None))
    find_github = AsyncMock()
    monkeypatch.setattr(github_client, "find_user_by_name", find_github)

    result = await users.resolve_user(_SESSION_ID, "Nobody")

    assert result is None
    find_github.assert_not_called()


async def test_connection_error_falls_back_to_stale_cache(monkeypatch):
    stale_row = _row(hours_old=48)
    monkeypatch.setattr(db, "get_team_member", lambda name: stale_row)
    monkeypatch.setattr(
        jira_client, "find_user_by_name", AsyncMock(side_effect=jira_client.JiraConnectionError("down"))
    )

    result = await users.resolve_user(_SESSION_ID, _NAME)

    assert result == {"jira_account_id": "account-1", "github_username": "nayab"}


async def test_connection_error_with_no_cache_raises(monkeypatch):
    monkeypatch.setattr(db, "get_team_member", lambda name: None)
    monkeypatch.setattr(
        jira_client, "find_user_by_name", AsyncMock(side_effect=jira_client.JiraConnectionError("down"))
    )

    with pytest.raises(jira_client.JiraConnectionError):
        await users.resolve_user(_SESSION_ID, _NAME)


async def test_github_connection_error_falls_back_to_stale_cache(monkeypatch):
    stale_row = _row(hours_old=48)
    monkeypatch.setattr(db, "get_team_member", lambda name: stale_row)
    monkeypatch.setattr(jira_client, "find_user_by_name", AsyncMock(return_value="account-1"))
    monkeypatch.setattr(
        github_client, "find_user_by_name", AsyncMock(side_effect=github_client.GitHubConnectionError("down"))
    )

    result = await users.resolve_user(_SESSION_ID, _NAME)

    assert result == {"jira_account_id": "account-1", "github_username": "nayab"}
