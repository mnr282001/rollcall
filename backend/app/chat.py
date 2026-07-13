from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAIError

from app import activity, db, github_client, jira_client, users

load_dotenv()

_OPENAI_MODEL = "gpt-4o-mini"
_MAX_HOPS = 4
_client: AsyncOpenAI | None = None


class NotConfiguredError(Exception):
    """Raised when OPENAI_API_KEY is missing — chat is unusable without it."""


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise NotConfiguredError("OPENAI_API_KEY is not configured")
    _client = AsyncOpenAI(api_key=api_key)
    return _client


def ensure_configured() -> None:
    """Raises NotConfiguredError up front, before a streaming response's headers are sent."""
    _get_client()


_TOOL = {
    "type": "function",
    "function": {
        "name": "get_activity_for_people",
        "description": (
            "Look up Jira issues and GitHub commits/pull requests/repos for one or more "
            "teammates by display name. Call this for any person you need facts about — "
            "including someone already discussed earlier in the conversation, if you need "
            "fresh or more specific data to answer a follow-up."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Display names of the people to look up, e.g. ['Nayab', 'Sarah']",
                }
            },
            "required": ["names"],
        },
    },
}


def _resolve_timezone(user_timezone: str | None) -> ZoneInfo:
    if user_timezone:
        try:
            return ZoneInfo(user_timezone)
        except ZoneInfoNotFoundError:
            pass
    return ZoneInfo("UTC")


def _current_date(tz: ZoneInfo) -> str:
    """Today's date in the user's local timezone.

    Commit/PR/issue timestamps land on the calendar day they happened for the
    user, not for the server — using UTC unconditionally made "today" roll
    over hours early or late for anyone outside UTC, so activity got reported
    against a date that hadn't occurred yet in the user's own timezone.
    """
    return datetime.now(tz).date().isoformat()


def _to_local_iso(timestamp: str, tz: ZoneInfo) -> str:
    """Re-expresses a UTC API timestamp (GitHub always returns commit/PR dates in UTC) in the
    user's local timezone, so its calendar day lines up with `current_date` for the LLM's
    'today'/'this week' comparisons instead of silently being a UTC day off.
    """
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(tz).isoformat()


def _system_prompt(tz: ZoneInfo) -> dict:
    current_date = _current_date(tz)
    return {
        "role": "system",
        "content": (
            "You are Rollcall, a teammate-activity assistant having an ongoing conversation "
            "with a user. Your only purpose is answering questions about teammates' Jira and "
            "GitHub activity — what they're working on, their tickets, commits, and PRs. If the "
            "user asks something unrelated to teammate activity (general knowledge, trivia, "
            "coding help, anything not answerable via the get_activity_for_people tool), don't "
            "answer it — briefly say that's outside what you help with and redirect them to ask "
            "about a teammate's work instead. Answer only using facts returned by the "
            "get_activity_for_people tool — never invent JIRA tickets, commits, PRs, or people "
            "beyond what a tool call returns. Call the tool whenever you need facts about someone, "
            "including someone already "
            "discussed earlier if a follow-up needs fresher or more specific data. Resolve "
            "pronouns and follow-ups (e.g. 'what about her PRs?', 'and Sarah too?') using the "
            "conversation history yourself before deciding who to look up. Tailor each answer to "
            "what was actually asked: if the question is about JIRA specifically, focus on that "
            "instead of dumping GitHub activity too, and vice versa. If a tool result's "
            "`not_found` list contains a name, say you don't know that person. If a person has "
            "`has_linked_github: false`, mention they have no linked GitHub account rather than "
            "guessing about their code activity. If a tool result has an `error` field "
            "(`auth_expired` or `connection`), explain the problem conversationally and suggest "
            "reconnecting Jira/GitHub in the app rather than treating it as fatal — still answer "
            "about anyone else in the same request if possible. JIRA issues have an `updated` "
            "timestamp (when the ticket was last modified in any way — not necessarily when it "
            "was completed), a `priority` (may be null if unset), an `estimate_hours` (original "
            "time estimate in hours, may be null if not set), a `due_date` (may be null), and an "
            "`issue_type` (e.g. Bug, Story, Task). Mention priority, estimate, or due date when "
            "the question is about workload, urgency, or deadlines — call out anything overdue "
            "(due_date before the current date and not Done) — but don't force them into every "
            f"answer. Commits have a `date`. PRs have an `updated_at`, a `draft` flag (a draft PR "
            "isn't ready for review or merge — say so if it's relevant), and "
            "`requested_reviewers` (who still needs to review it, may be empty). The current "
            f"date is {current_date}. If the question asks about a specific time frame "
            "(e.g. 'today', 'this week'), only count items whose timestamp falls in that window "
            "relative to the current date, and say there's no activity in that window if none "
            "qualify. Don't claim an issue was 'completed' in that window just because `updated` "
            "falls in it and the status happens to be Done — say it was last touched then, unless "
            "that's genuinely the same thing you can infer. Never state that someone did or "
            "didn't do something in a time frame without checking its timestamp against the "
            "current date. Keep it brief and natural, like a helpful teammate would answer."
        ),
    }


def _seconds_to_hours(seconds: int | None) -> float | None:
    return None if seconds is None else round(seconds / 3600, 1)


def _activity_facts(name: str, activity_data: dict, tz: ZoneInfo) -> dict:
    """Structured, LLM-safe summary of one person's activity — no free text for the model to embellish."""
    commits = activity_data["github_commits"]
    pull_requests = activity_data["github_pull_requests"]
    return {
        "name": name,
        "jira_issues": [
            {
                "key": issue["key"],
                "status": issue["status"],
                "summary": issue["summary"],
                "updated": issue["updated"],
                "priority": issue.get("priority"),
                "estimate_hours": _seconds_to_hours(issue.get("time_estimate_seconds")),
                "due_date": issue.get("due_date"),
                "issue_type": issue.get("issue_type"),
            }
            for issue in activity_data["jira_issues"]
        ],
        "has_linked_github": commits is not None,
        "github_commits": None if commits is None else [
            {
                "repo": commit["repo"],
                "message": commit["message"],
                "sha": commit["sha"],
                "date": _to_local_iso(commit["date"], tz),
            }
            for commit in commits
        ],
        "github_pull_requests": None if pull_requests is None else [
            {
                "repo": pr["repo"],
                "number": pr["number"],
                "title": pr["title"],
                "updated_at": _to_local_iso(pr["updated_at"], tz),
                "draft": pr.get("draft"),
                "requested_reviewers": pr.get("requested_reviewers"),
            }
            for pr in pull_requests
        ],
    }


async def _execute_get_activity(session_id: str, names: list[str], tz: ZoneInfo) -> dict:
    if not names:
        return {"people": [], "not_found": []}

    try:
        resolved = list(zip(names, await asyncio.gather(*(users.resolve_user(session_id, n) for n in names))))
    except (jira_client.JiraAuthError, github_client.GitHubAuthError) as exc:
        return {"error": "auth_expired", "message": str(exc)}
    except (jira_client.JiraConnectionError, github_client.GitHubConnectionError) as exc:
        return {"error": "connection", "message": str(exc)}

    not_found = [name for name, user in resolved if user is None]
    found = [(name, user) for name, user in resolved if user is not None]

    try:
        activities = await asyncio.gather(
            *(
                activity.get_user_activity(session_id, user["jira_account_id"], user["github_username"])
                for _, user in found
            )
        )
    except (jira_client.JiraAuthError, github_client.GitHubAuthError) as exc:
        return {"error": "auth_expired", "message": str(exc)}
    except (jira_client.JiraConnectionError, github_client.GitHubConnectionError) as exc:
        return {"error": "connection", "message": str(exc)}

    facts = [_activity_facts(name, data, tz) for (name, _), data in zip(found, activities)]
    return {"people": facts, "not_found": not_found}


def _row_to_openai_message(row: dict) -> dict:
    if row["role"] == "assistant" and row["tool_calls"]:
        return {"role": "assistant", "content": row["content"], "tool_calls": row["tool_calls"]}
    if row["role"] == "tool":
        return {"role": "tool", "tool_call_id": row["tool_call_id"], "content": row["content"]}
    return {"role": row["role"], "content": row["content"]}


_FALLBACK_ANSWER = "Sorry, I'm having trouble putting together an answer right now — try rephrasing?"


async def stream_message(session_id: str, user_message: str, user_timezone: str | None = None) -> AsyncIterator[str]:
    """Answers a chat message, streaming the reply text as it's generated.

    The LLM decides which people (if any) to look up via the get_activity_for_people
    tool, resolving pronouns/follow-ups from prior turns itself. Every turn (user,
    assistant, and tool) is persisted so the next call picks up the full thread. Only
    the final hop (no tool call) produces content, so that's the only one streamed to
    the caller — earlier hops that just decide to call the tool emit nothing.

    `user_timezone` (an IANA name like "America/Los_Angeles") anchors "today" to the
    user's own calendar day rather than the server's — see _current_date.
    """
    client = _get_client()
    tz = _resolve_timezone(user_timezone)
    db.add_message(session_id, "user", content=user_message)

    messages = [_system_prompt(tz)] + [_row_to_openai_message(row) for row in db.get_messages(session_id)]

    try:
        for _ in range(_MAX_HOPS):
            stream = await client.chat.completions.create(
                model=_OPENAI_MODEL,
                temperature=0.3,
                messages=messages,
                tools=[_TOOL],
                tool_choice="auto",
                stream=True,
            )

            content_parts: list[str] = []
            tool_calls_acc: dict[int, dict] = {}

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
                    yield delta.content
                for tool_call_delta in delta.tool_calls or []:
                    entry = tool_calls_acc.setdefault(
                        tool_call_delta.index,
                        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                    )
                    if tool_call_delta.id:
                        entry["id"] = tool_call_delta.id
                    if tool_call_delta.function and tool_call_delta.function.name:
                        entry["function"]["name"] += tool_call_delta.function.name
                    if tool_call_delta.function and tool_call_delta.function.arguments:
                        entry["function"]["arguments"] += tool_call_delta.function.arguments

            content = "".join(content_parts) or None

            if not tool_calls_acc:
                answer = content or _FALLBACK_ANSWER
                if not content:
                    yield answer
                db.add_message(session_id, "assistant", content=answer)
                return

            tool_calls_payload = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
            db.add_message(session_id, "assistant", content=content, tool_calls=tool_calls_payload)
            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls_payload})

            for tool_call in tool_calls_payload:
                args = json.loads(tool_call["function"]["arguments"])
                result = await _execute_get_activity(session_id, args.get("names", []), tz)
                result_content = json.dumps(result)
                db.add_message(session_id, "tool", content=result_content, tool_call_id=tool_call["id"])
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result_content})
    except OpenAIError:
        db.add_message(session_id, "assistant", content=_FALLBACK_ANSWER)
        yield _FALLBACK_ANSWER
        return

    db.add_message(session_id, "assistant", content=_FALLBACK_ANSWER)
    yield _FALLBACK_ANSWER
