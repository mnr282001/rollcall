from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from openai import OpenAIError

from app import activity, chat, db, github_client, jira_client, users

_SESSION_ID = "session-1"


# --- small pure helpers -----------------------------------------------------


def test_resolve_timezone_valid_name():
    assert chat._resolve_timezone("America/Los_Angeles") == ZoneInfo("America/Los_Angeles")


def test_resolve_timezone_none_defaults_to_utc():
    assert chat._resolve_timezone(None) == ZoneInfo("UTC")


def test_resolve_timezone_invalid_name_defaults_to_utc():
    assert chat._resolve_timezone("Not/ARealZone") == ZoneInfo("UTC")


def test_to_local_iso_converts_utc_to_target_timezone():
    result = chat._to_local_iso("2026-07-01T12:00:00Z", ZoneInfo("America/Los_Angeles"))
    assert result == "2026-07-01T05:00:00-07:00"


def test_seconds_to_hours_none_stays_none():
    assert chat._seconds_to_hours(None) is None


def test_seconds_to_hours_rounds_to_one_decimal():
    assert chat._seconds_to_hours(5400) == 1.5


# --- _activity_facts ---------------------------------------------------------


def test_activity_facts_shapes_full_person_with_github():
    activity_data = {
        "jira_issues": [
            {
                "key": "AB-1",
                "status": "In Progress",
                "summary": "Do the thing",
                "updated": "2026-07-01T00:00:00Z",
                "priority": "High",
                "time_estimate_seconds": 3600,
                "due_date": "2026-07-10",
                "issue_type": "Bug",
            }
        ],
        "github_commits": [
            {"repo": "org/repo", "sha": "abc1234", "message": "fix bug", "date": "2026-07-01T00:00:00Z"}
        ],
        "github_pull_requests": [
            {
                "repo": "org/repo",
                "number": 1,
                "title": "Fix",
                "updated_at": "2026-07-01T00:00:00Z",
                "draft": False,
                "requested_reviewers": ["sarah"],
            }
        ],
        "github_repos": [{"full_name": "org/repo", "pushed_at": "2026-07-01T00:00:00Z", "private": False}],
    }

    facts = chat._activity_facts("Nayab", activity_data, ZoneInfo("UTC"))

    assert facts["name"] == "Nayab"
    assert facts["has_linked_github"] is True
    assert facts["jira_issues"][0]["estimate_hours"] == 1.0
    assert facts["github_repos"] == [
        {"full_name": "org/repo", "pushed_at": "2026-07-01T00:00:00+00:00", "private": False}
    ]
    assert facts["github_commits"][0]["repo"] == "org/repo"
    assert facts["github_pull_requests"][0]["requested_reviewers"] == ["sarah"]


def test_activity_facts_no_linked_github_has_none_commits_and_prs():
    activity_data = {
        "jira_issues": [],
        "github_commits": None,
        "github_pull_requests": None,
        "github_repos": [],
    }

    facts = chat._activity_facts("NoGithub", activity_data, ZoneInfo("UTC"))

    assert facts["has_linked_github"] is False
    assert facts["github_commits"] is None
    assert facts["github_pull_requests"] is None
    assert facts["github_repos"] == []


# --- _execute_get_activity ----------------------------------------------------


async def test_execute_get_activity_returns_empty_for_no_names():
    result = await chat._execute_get_activity(_SESSION_ID, [], ZoneInfo("UTC"))
    assert result == {"people": [], "not_found": []}


async def test_execute_get_activity_splits_found_and_not_found(monkeypatch):
    async def fake_resolve_user(session_id, name):
        return {"jira_account_id": "acc-1", "github_username": "nayab"} if name == "Nayab" else None

    monkeypatch.setattr(users, "resolve_user", fake_resolve_user)
    monkeypatch.setattr(
        activity,
        "get_user_activity",
        AsyncMock(
            return_value={
                "jira_issues": [],
                "github_commits": [],
                "github_pull_requests": [],
                "github_repos": [],
            }
        ),
    )

    result = await chat._execute_get_activity(_SESSION_ID, ["Nayab", "Ghost"], ZoneInfo("UTC"))

    assert result["not_found"] == ["Ghost"]
    assert [p["name"] for p in result["people"]] == ["Nayab"]


@pytest.mark.parametrize(
    "exc, expected_error",
    [
        (jira_client.JiraAuthError("bad token"), "auth_expired"),
        (github_client.GitHubAuthError("bad token"), "auth_expired"),
        (jira_client.JiraConnectionError("down"), "connection"),
        (github_client.GitHubConnectionError("down"), "connection"),
        (jira_client.JiraRateLimitError("slow down"), "rate_limited"),
        (github_client.GitHubRateLimitError("slow down"), "rate_limited"),
    ],
)
async def test_execute_get_activity_maps_resolve_errors(monkeypatch, exc, expected_error):
    monkeypatch.setattr(users, "resolve_user", AsyncMock(side_effect=exc))

    result = await chat._execute_get_activity(_SESSION_ID, ["Nayab"], ZoneInfo("UTC"))

    assert result["error"] == expected_error


@pytest.mark.parametrize(
    "exc, expected_error",
    [
        (jira_client.JiraAuthError("bad token"), "auth_expired"),
        (jira_client.JiraConnectionError("down"), "connection"),
        (github_client.GitHubRateLimitError("slow down"), "rate_limited"),
    ],
)
async def test_execute_get_activity_maps_activity_fetch_errors(monkeypatch, exc, expected_error):
    monkeypatch.setattr(
        users, "resolve_user", AsyncMock(return_value={"jira_account_id": "acc-1", "github_username": "nayab"})
    )
    monkeypatch.setattr(activity, "get_user_activity", AsyncMock(side_effect=exc))

    result = await chat._execute_get_activity(_SESSION_ID, ["Nayab"], ZoneInfo("UTC"))

    assert result["error"] == expected_error


# --- stream_message ------------------------------------------------------------


def _text_chunk(content):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])


def _tool_call_chunk(index, call_id, name, arguments):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            index=index,
                            id=call_id,
                            function=SimpleNamespace(name=name, arguments=arguments),
                        )
                    ],
                )
            )
        ]
    )


async def _fake_stream(chunks):
    for chunk in chunks:
        yield chunk


@pytest.fixture(autouse=True)
def _fake_db(monkeypatch):
    monkeypatch.setattr(db, "get_messages", lambda session_id: [])
    monkeypatch.setattr(db, "add_message", Mock())


def _install_fake_openai(monkeypatch, streams):
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=streams))))
    monkeypatch.setattr(chat, "_get_client", lambda: fake_client)
    return fake_client


async def test_stream_message_yields_plain_answer_with_no_tool_call(monkeypatch):
    _install_fake_openai(monkeypatch, [_fake_stream([_text_chunk("Hello"), _text_chunk(" world")])])

    chunks = [c async for c in chat.stream_message(_SESSION_ID, "hi")]

    assert chunks == ["Hello", " world"]
    assistant_calls = [c for c in db.add_message.call_args_list if c.args[1] == "assistant"]
    assert assistant_calls[-1].kwargs["content"] == "Hello world"


async def test_stream_message_calls_tool_then_answers(monkeypatch):
    tool_args = json.dumps({"names": ["Nayab"]})
    _install_fake_openai(
        monkeypatch,
        [
            _fake_stream([_tool_call_chunk(0, "call_1", "get_activity_for_people", tool_args)]),
            _fake_stream([_text_chunk("Nayab is working on AB-1.")]),
        ],
    )
    execute = AsyncMock(return_value={"people": [{"name": "Nayab"}], "not_found": []})
    monkeypatch.setattr(chat, "_execute_get_activity", execute)

    chunks = [c async for c in chat.stream_message(_SESSION_ID, "what is nayab doing?")]

    assert chunks == ["Nayab is working on AB-1."]
    execute.assert_awaited_once()
    assert execute.call_args.args[1] == ["Nayab"]

    tool_message_calls = [c for c in db.add_message.call_args_list if c.args[1] == "tool"]
    assert len(tool_message_calls) == 1
    assert json.loads(tool_message_calls[0].kwargs["content"]) == {"people": [{"name": "Nayab"}], "not_found": []}


async def test_stream_message_falls_back_on_openai_error(monkeypatch):
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=OpenAIError("boom"))))
    )
    monkeypatch.setattr(chat, "_get_client", lambda: fake_client)

    chunks = [c async for c in chat.stream_message(_SESSION_ID, "hi")]

    assert chunks == [chat._FALLBACK_ANSWER]
    fallback_calls = [c for c in db.add_message.call_args_list if c.args[1] == "assistant"]
    assert fallback_calls[-1].kwargs["content"] == chat._FALLBACK_ANSWER


async def test_stream_message_falls_back_after_exhausting_max_hops(monkeypatch):
    tool_args = json.dumps({"names": []})
    streams = [
        _fake_stream([_tool_call_chunk(0, f"call_{i}", "get_activity_for_people", tool_args)])
        for i in range(chat._MAX_HOPS)
    ]
    create = _install_fake_openai(monkeypatch, streams).chat.completions.create
    monkeypatch.setattr(chat, "_execute_get_activity", AsyncMock(return_value={"people": [], "not_found": []}))

    chunks = [c async for c in chat.stream_message(_SESSION_ID, "hi")]

    assert chunks == [chat._FALLBACK_ANSWER]
    assert create.await_count == chat._MAX_HOPS
