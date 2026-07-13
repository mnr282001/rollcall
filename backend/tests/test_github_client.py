from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app import db, github_client

_SESSION_ID = "session-1"
_REQUEST = httpx.Request("GET", "https://api.github.com/user")


def _response(status_code: int, headers: dict | None = None, json: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, headers=headers or {}, json=json, request=_REQUEST)


@pytest.fixture(autouse=True)
def _fake_session(monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: {"github_token": "fake-token"})


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


async def test_retries_on_primary_rate_limit_then_succeeds(monkeypatch):
    responses = [
        _response(403, headers={"X-RateLimit-Remaining": "0"}),
        _response(200, json={"login": "nayab"}),
    ]
    do_request = AsyncMock(side_effect=responses)
    monkeypatch.setattr(github_client, "_do_request", do_request)

    result = await github_client.whoami(_SESSION_ID)

    assert result == {"login": "nayab"}
    assert do_request.call_count == 2


async def test_retries_on_429_then_succeeds(monkeypatch):
    responses = [_response(429), _response(200, json={"login": "nayab"})]
    monkeypatch.setattr(github_client, "_do_request", AsyncMock(side_effect=responses))

    result = await github_client.whoami(_SESSION_ID)

    assert result == {"login": "nayab"}


async def test_raises_rate_limit_error_after_exhausting_retries(monkeypatch):
    do_request = AsyncMock(return_value=_response(429))
    monkeypatch.setattr(github_client, "_do_request", do_request)

    with pytest.raises(github_client.GitHubRateLimitError):
        await github_client.whoami(_SESSION_ID)

    assert do_request.call_count == github_client._MAX_RATE_LIMIT_RETRIES + 1


async def test_403_without_rate_limit_header_raises_auth_error_immediately(monkeypatch):
    do_request = AsyncMock(return_value=_response(403))
    monkeypatch.setattr(github_client, "_do_request", do_request)

    with pytest.raises(github_client.GitHubAuthError):
        await github_client.whoami(_SESSION_ID)

    assert do_request.call_count == 1


async def test_backoff_honors_retry_after_header(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    responses = [
        _response(429, headers={"Retry-After": "7"}),
        _response(200, json={"login": "nayab"}),
    ]
    monkeypatch.setattr(github_client, "_do_request", AsyncMock(side_effect=responses))

    await github_client.whoami(_SESSION_ID)

    sleep.assert_awaited_once_with(7.0)
