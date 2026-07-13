from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth_routes, db, oauth_github, oauth_jira


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(auth_routes.router)
    return TestClient(app)


def test_github_login_redirects_and_sets_state_cookie(client):
    response = client.get("/auth/github/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith(oauth_github.AUTHORIZE_URL)
    assert auth_routes.GITHUB_STATE_COOKIE in response.cookies


def test_jira_login_redirects_and_sets_state_cookie(client):
    response = client.get("/auth/jira/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith(oauth_jira.AUTHORIZE_URL)
    assert auth_routes.JIRA_STATE_COOKIE in response.cookies


def test_github_callback_rejects_mismatched_state(client):
    client.cookies.set(auth_routes.GITHUB_STATE_COOKIE, "expected-state")

    response = client.get(
        "/auth/github/callback", params={"code": "abc", "state": "wrong-state"}, follow_redirects=False
    )

    assert response.status_code == 400


def test_github_callback_rejects_missing_state_cookie(client):
    response = client.get(
        "/auth/github/callback", params={"code": "abc", "state": "some-state"}, follow_redirects=False
    )

    assert response.status_code == 400


def test_github_callback_success_sets_session_and_clears_state_cookie(client, monkeypatch):
    monkeypatch.setattr(oauth_github, "exchange_code_for_token", Mock(return_value="gh-token"))
    monkeypatch.setattr(db, "create_session", Mock())
    save_token = Mock()
    monkeypatch.setattr(db, "save_github_token", save_token)

    client.cookies.set(auth_routes.GITHUB_STATE_COOKIE, "matching-state")
    response = client.get(
        "/auth/github/callback", params={"code": "abc", "state": "matching-state"}, follow_redirects=False
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == auth_routes.FRONTEND_URL
    assert auth_routes.SESSION_COOKIE in response.cookies
    save_token.assert_called_once()
    assert save_token.call_args.args[1] == "gh-token"


def test_jira_callback_success_sets_session_and_clears_state_cookie(client, monkeypatch):
    monkeypatch.setattr(oauth_jira, "exchange_code_for_tokens", Mock(return_value=("access", "refresh")))
    monkeypatch.setattr(oauth_jira, "get_cloud_id", Mock(return_value="cloud-1"))
    monkeypatch.setattr(db, "create_session", Mock())
    save_tokens = Mock()
    monkeypatch.setattr(db, "save_jira_tokens", save_tokens)

    client.cookies.set(auth_routes.JIRA_STATE_COOKIE, "matching-state")
    response = client.get(
        "/auth/jira/callback", params={"code": "abc", "state": "matching-state"}, follow_redirects=False
    )

    assert response.status_code in (302, 307)
    assert auth_routes.SESSION_COOKIE in response.cookies
    save_tokens.assert_called_once_with(save_tokens.call_args.args[0], "access", "refresh", "cloud-1")


def test_github_logout_clears_token_when_session_present(client, monkeypatch):
    clear_token = Mock()
    monkeypatch.setattr(db, "clear_github_token", clear_token)
    client.cookies.set(auth_routes.SESSION_COOKIE, "session-1")

    response = client.post("/auth/github/logout")

    assert response.json() == {"github_connected": False}
    clear_token.assert_called_once_with("session-1")


def test_github_logout_noop_when_no_session_cookie(client, monkeypatch):
    clear_token = Mock()
    monkeypatch.setattr(db, "clear_github_token", clear_token)

    response = client.post("/auth/github/logout")

    assert response.json() == {"github_connected": False}
    clear_token.assert_not_called()


def test_jira_logout_clears_tokens_when_session_present(client, monkeypatch):
    clear_tokens = Mock()
    monkeypatch.setattr(db, "clear_jira_tokens", clear_tokens)
    client.cookies.set(auth_routes.SESSION_COOKIE, "session-1")

    response = client.post("/auth/jira/logout")

    assert response.json() == {"jira_connected": False}
    clear_tokens.assert_called_once_with("session-1")


def test_me_without_session_cookie_reports_unauthenticated(client):
    response = client.get("/auth/me")

    assert response.json() == {
        "authenticated": False,
        "github_connected": False,
        "jira_connected": False,
    }


def test_me_with_unknown_session_reports_unauthenticated(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: None)
    client.cookies.set(auth_routes.SESSION_COOKIE, "ghost-session")

    response = client.get("/auth/me")

    assert response.json()["authenticated"] is False


def test_me_reports_connection_status_from_session(client, monkeypatch):
    monkeypatch.setattr(
        db,
        "get_session",
        lambda session_id: {"github_token": "gh", "jira_access_token": None},
    )
    client.cookies.set(auth_routes.SESSION_COOKIE, "session-1")

    response = client.get("/auth/me")

    assert response.json() == {
        "authenticated": True,
        "github_connected": True,
        "jira_connected": False,
    }
