from __future__ import annotations

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import oauth_jira


def _fake_jwt(exp: float) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.signature"


def test_new_state_is_url_safe_and_reasonably_random():
    a, b = oauth_jira.new_state(), oauth_jira.new_state()
    assert a != b
    assert len(a) >= 20


def test_get_authorize_url_includes_expected_params():
    url = oauth_jira.get_authorize_url("state-123")
    params = parse_qs(urlparse(url).query)

    assert url.startswith(oauth_jira.AUTHORIZE_URL)
    assert params["client_id"] == [oauth_jira.JIRA_OAUTH_CLIENT_ID]
    assert params["state"] == ["state-123"]
    assert params["response_type"] == ["code"]
    assert params["prompt"] == ["consent"]


def test_exchange_code_for_tokens_returns_access_and_refresh(monkeypatch):
    def fake_post(url, json=None, **kwargs):
        assert url == oauth_jira.TOKEN_URL
        assert json["grant_type"] == "authorization_code"
        assert json["code"] == "the-code"
        return httpx.Response(
            200,
            json={"access_token": "access-1", "refresh_token": "refresh-1"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    access, refresh = oauth_jira.exchange_code_for_tokens("the-code")

    assert (access, refresh) == ("access-1", "refresh-1")


def test_refresh_access_token_uses_refresh_grant(monkeypatch):
    def fake_post(url, json=None, **kwargs):
        assert json["grant_type"] == "refresh_token"
        assert json["refresh_token"] == "old-refresh"
        return httpx.Response(
            200,
            json={"access_token": "access-2", "refresh_token": "refresh-2"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    access, refresh = oauth_jira.refresh_access_token("old-refresh")

    assert (access, refresh) == ("access-2", "refresh-2")


def test_is_token_expired_false_for_future_exp():
    token = _fake_jwt(exp=time.time() + 3600)
    assert oauth_jira.is_token_expired(token) is False


def test_is_token_expired_true_for_past_exp():
    token = _fake_jwt(exp=time.time() - 3600)
    assert oauth_jira.is_token_expired(token) is True


def test_is_token_expired_true_within_leeway_window():
    token = _fake_jwt(exp=time.time() + 10)
    assert oauth_jira.is_token_expired(token, leeway_seconds=30) is True


def test_is_token_expired_true_for_malformed_token():
    assert oauth_jira.is_token_expired("not-a-jwt") is True


def test_get_cloud_id_returns_first_resource_id(monkeypatch):
    def fake_get(url, headers=None):
        assert url == oauth_jira.ACCESSIBLE_RESOURCES_URL
        return httpx.Response(200, json=[{"id": "cloud-1"}, {"id": "cloud-2"}], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    assert oauth_jira.get_cloud_id("access-token") == "cloud-1"


def test_get_cloud_id_raises_when_no_accessible_sites(monkeypatch):
    def fake_get(url, headers=None):
        return httpx.Response(200, json=[], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(RuntimeError, match="No accessible Jira sites"):
        oauth_jira.get_cloud_id("access-token")
