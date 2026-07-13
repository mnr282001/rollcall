from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app import db, jira_client, oauth_jira

_SESSION_ID = "session-1"
_REQUEST = httpx.Request("GET", "https://api.atlassian.com/ex/jira/cloud-1/rest/api/3/myself")


def _response(status_code: int, headers: dict | None = None, json: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, headers=headers or {}, json=json, request=_REQUEST)


@pytest.fixture(autouse=True)
def _fake_session(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_session",
        lambda session_id: {
            "jira_access_token": "fake-access-token",
            "jira_refresh_token": "fake-refresh-token",
            "jira_cloud_id": "cloud-1",
        },
    )
    monkeypatch.setattr(oauth_jira, "is_token_expired", lambda access_token: False)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


async def test_retries_on_429_then_succeeds(monkeypatch):
    responses = [_response(429), _response(200, json={"accountId": "abc"})]
    do_request = AsyncMock(side_effect=responses)
    monkeypatch.setattr(jira_client, "_do_request", do_request)

    result = await jira_client.whoami(_SESSION_ID)

    assert result == {"accountId": "abc"}
    assert do_request.call_count == 2


async def test_raises_rate_limit_error_after_exhausting_retries(monkeypatch):
    do_request = AsyncMock(return_value=_response(429))
    monkeypatch.setattr(jira_client, "_do_request", do_request)

    with pytest.raises(jira_client.JiraRateLimitError):
        await jira_client.whoami(_SESSION_ID)

    assert do_request.call_count == jira_client._MAX_RATE_LIMIT_RETRIES + 1


async def test_403_still_raises_auth_error_immediately(monkeypatch):
    do_request = AsyncMock(return_value=_response(403))
    monkeypatch.setattr(jira_client, "_do_request", do_request)

    with pytest.raises(jira_client.JiraAuthError):
        await jira_client.whoami(_SESSION_ID)

    assert do_request.call_count == 1


async def test_backoff_honors_retry_after_header(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    responses = [
        _response(429, headers={"Retry-After": "3"}),
        _response(200, json={"accountId": "abc"}),
    ]
    monkeypatch.setattr(jira_client, "_do_request", AsyncMock(side_effect=responses))

    await jira_client.whoami(_SESSION_ID)

    sleep.assert_awaited_once_with(3.0)
