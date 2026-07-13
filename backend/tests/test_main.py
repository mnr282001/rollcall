from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import main
from app import chat, db


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(db, "init_db", Mock())
    with TestClient(main.app) as test_client:
        yield test_client


def test_read_root(client):
    response = client.get("/")
    assert response.json() == {"Hello": "World"}


def test_add_user_requires_login(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: None)

    response = client.post(
        "/admin/users",
        json={"name": "Nayab", "jira_account_id": "account-1", "github_username": "nayab"},
    )

    assert response.status_code == 401


def test_add_user_creates_team_member_when_logged_in(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: {"session_id": session_id})
    add_team_member = Mock()
    monkeypatch.setattr(db, "add_team_member", add_team_member)
    client.cookies.set("session_id", "session-1")

    response = client.post(
        "/admin/users",
        json={"name": "Nayab Rehmat", "jira_account_id": "account-1", "github_username": "nayab"},
    )

    assert response.status_code == 201
    assert response.json() == {"name": "nayab rehmat"}
    add_team_member.assert_called_once_with("Nayab Rehmat", "account-1", "nayab")


def test_chat_requires_login(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: None)

    response = client.post("/chat", json={"message": "hi"})

    assert response.status_code == 401


def test_chat_returns_500_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: {"session_id": session_id})
    client.cookies.set("session_id", "session-1")

    def raise_not_configured():
        raise chat.NotConfiguredError("OPENAI_API_KEY is not configured")

    monkeypatch.setattr(chat, "ensure_configured", raise_not_configured)

    response = client.post("/chat", json={"message": "hi"})

    assert response.status_code == 500


def test_chat_streams_sse_chunks(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: {"session_id": session_id})
    client.cookies.set("session_id", "session-1")
    monkeypatch.setattr(chat, "ensure_configured", lambda: None)

    async def fake_stream_message(session_id, message, user_timezone):
        yield "Hello "
        yield "world"

    monkeypatch.setattr(chat, "stream_message", fake_stream_message)

    response = client.post("/chat", json={"message": "hi", "timezone": "UTC"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == 'data: "Hello "\n\ndata: "world"\n\n'


def test_chat_history_requires_login(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: None)

    response = client.get("/chat/history")

    assert response.status_code == 401


def test_chat_history_filters_to_user_and_assistant_with_content(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: {"session_id": session_id})
    client.cookies.set("session_id", "session-1")
    monkeypatch.setattr(
        db,
        "get_messages",
        lambda session_id: [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "assistant", "content": None},
            {"role": "tool", "content": "{}"},
        ],
    )

    response = client.get("/chat/history")

    assert response.json() == {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    }


def test_reset_chat_requires_login(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: None)

    response = client.delete("/chat/history")

    assert response.status_code == 401


def test_reset_chat_deletes_messages(client, monkeypatch):
    monkeypatch.setattr(db, "get_session", lambda session_id: {"session_id": session_id})
    client.cookies.set("session_id", "session-1")
    delete_messages = Mock()
    monkeypatch.setattr(db, "delete_messages", delete_messages)

    response = client.delete("/chat/history")

    assert response.json() == {"ok": True}
    delete_messages.assert_called_once_with("session-1")
