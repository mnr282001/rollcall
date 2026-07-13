from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import oauth_github


def test_new_state_is_url_safe_and_reasonably_random():
    a, b = oauth_github.new_state(), oauth_github.new_state()
    assert a != b
    assert len(a) >= 20


def test_get_authorize_url_includes_expected_params():
    url = oauth_github.get_authorize_url("state-123")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert url.startswith(oauth_github.AUTHORIZE_URL)
    assert params["client_id"] == [oauth_github.GITHUB_CLIENT_ID]
    assert params["redirect_uri"] == [oauth_github.GITHUB_REDIRECT_URI]
    assert params["state"] == ["state-123"]
    assert params["scope"] == ["read:user repo"]


def test_exchange_code_for_token_returns_access_token(monkeypatch):
    def fake_post(url, headers=None, data=None):
        assert url == oauth_github.TOKEN_URL
        assert data["code"] == "the-code"
        return httpx.Response(200, json={"access_token": "gh-token-123"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    token = oauth_github.exchange_code_for_token("the-code")

    assert token == "gh-token-123"


def test_exchange_code_for_token_raises_on_oauth_error_body(monkeypatch):
    def fake_post(url, headers=None, data=None):
        return httpx.Response(
            200, json={"error": "bad_verification_code"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(RuntimeError, match="bad_verification_code"):
        oauth_github.exchange_code_for_token("stale-code")


def test_exchange_code_for_token_raises_on_http_error(monkeypatch):
    def fake_post(url, headers=None, data=None):
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(httpx.HTTPStatusError):
        oauth_github.exchange_code_for_token("the-code")
