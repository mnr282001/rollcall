from __future__ import annotations

from types import SimpleNamespace

from app import db


class _FakeQuery:
    """Minimal stand-in for supabase-py's fluent query builder.

    Every builder method just records the call and returns self so any
    chain (select/eq/order, update/eq, upsert, insert, delete/eq) works;
    execute() returns the canned result configured on the fake client.
    """

    def __init__(self, calls: list, result_data):
        self._calls = calls
        self._result_data = result_data

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self._calls.append((name, args, kwargs))
            return self

        return method

    def execute(self):
        self._calls.append(("execute", (), {}))
        return SimpleNamespace(data=self._result_data)


class _FakeClient:
    def __init__(self, result_data=None):
        self.result_data = result_data
        self.calls: list = []

    def table(self, name):
        self.calls.append(("table", (name,), {}))
        return _FakeQuery(self.calls, self.result_data)


def _install_fake_client(monkeypatch, result_data=None) -> _FakeClient:
    fake = _FakeClient(result_data)
    monkeypatch.setattr(db, "_get_client", lambda: fake)
    return fake


def test_create_session_upserts_by_session_id(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    db.create_session("session-1")

    assert ("table", ("sessions",), {}) in fake.calls
    assert ("upsert", ({"session_id": "session-1"},), {"on_conflict": "session_id"}) in fake.calls


def test_save_github_token_updates_by_session_id(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    db.save_github_token("session-1", "gh-token")

    assert ("update", ({"github_token": "gh-token"},), {}) in fake.calls
    assert ("eq", ("session_id", "session-1"), {}) in fake.calls


def test_save_jira_tokens_updates_all_fields(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    db.save_jira_tokens("session-1", "access", "refresh", "cloud-1")

    assert (
        "update",
        ({"jira_access_token": "access", "jira_refresh_token": "refresh", "jira_cloud_id": "cloud-1"},),
        {},
    ) in fake.calls


def test_clear_github_token_sets_none(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    db.clear_github_token("session-1")

    assert ("update", ({"github_token": None},), {}) in fake.calls


def test_clear_jira_tokens_sets_all_none(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    db.clear_jira_tokens("session-1")

    assert (
        "update",
        ({"jira_access_token": None, "jira_refresh_token": None, "jira_cloud_id": None},),
        {},
    ) in fake.calls


def test_get_session_returns_first_row_when_found(monkeypatch):
    _install_fake_client(monkeypatch, result_data=[{"session_id": "session-1", "github_token": "gh"}])

    result = db.get_session("session-1")

    assert result == {"session_id": "session-1", "github_token": "gh"}


def test_get_session_returns_none_when_not_found(monkeypatch):
    _install_fake_client(monkeypatch, result_data=[])

    assert db.get_session("missing") is None


def test_add_team_member_upserts_lowercased_name(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    db.add_team_member("Nayab Rehmat", "account-1", "nayab")

    upsert_calls = [call for call in fake.calls if call[0] == "upsert"]
    assert len(upsert_calls) == 1
    payload, kwargs = upsert_calls[0][1][0], upsert_calls[0][2]
    assert payload["name"] == "nayab rehmat"
    assert payload["jira_account_id"] == "account-1"
    assert payload["github_username"] == "nayab"
    assert "resolved_at" in payload
    assert kwargs == {"on_conflict": "name"}


def test_get_team_member_lowercases_and_strips_name(monkeypatch):
    fake = _install_fake_client(monkeypatch, result_data=[{"name": "nayab"}])

    result = db.get_team_member("  Nayab  ")

    assert result == {"name": "nayab"}
    assert ("eq", ("name", "nayab"), {}) in fake.calls


def test_get_team_member_returns_none_when_not_found(monkeypatch):
    _install_fake_client(monkeypatch, result_data=[])

    assert db.get_team_member("nobody") is None


def test_add_message_inserts_all_fields(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    db.add_message("session-1", "assistant", content="hi", tool_calls=[{"id": "1"}], tool_call_id=None)

    insert_calls = [call for call in fake.calls if call[0] == "insert"]
    assert insert_calls[0][1][0] == {
        "session_id": "session-1",
        "role": "assistant",
        "content": "hi",
        "tool_calls": [{"id": "1"}],
        "tool_call_id": None,
    }


def test_get_messages_returns_rows_ordered(monkeypatch):
    rows = [{"id": 1, "role": "user"}, {"id": 2, "role": "assistant"}]
    fake = _install_fake_client(monkeypatch, result_data=rows)

    result = db.get_messages("session-1")

    assert result == rows
    assert ("order", ("id",), {}) in fake.calls


def test_delete_messages_deletes_by_session_id(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    db.delete_messages("session-1")

    assert ("table", ("messages",), {}) in fake.calls
    assert ("delete", (), {}) in fake.calls
    assert ("eq", ("session_id", "session-1"), {}) in fake.calls
