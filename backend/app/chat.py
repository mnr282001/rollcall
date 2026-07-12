from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from app import activity, db, github_client, jira_client, users

load_dotenv()

_OPENAI_MODEL = "gpt-4o-mini"
_MAX_HOPS = 4
_client: OpenAI | None = None


class NotConfiguredError(Exception):
    """Raised when OPENAI_API_KEY is missing — chat is unusable without it."""


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise NotConfiguredError("OPENAI_API_KEY is not configured")
    _client = OpenAI(api_key=api_key)
    return _client


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


def _system_prompt() -> dict:
    current_date = datetime.now(timezone.utc).date().isoformat()
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
            f"date (UTC) is {current_date}. If the question asks about a specific time frame "
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


def _activity_facts(name: str, activity_data: dict) -> dict:
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
            {"repo": commit["repo"], "message": commit["message"], "sha": commit["sha"], "date": commit["date"]}
            for commit in commits
        ],
        "github_pull_requests": None if pull_requests is None else [
            {
                "repo": pr["repo"],
                "number": pr["number"],
                "title": pr["title"],
                "updated_at": pr["updated_at"],
                "draft": pr.get("draft"),
                "requested_reviewers": pr.get("requested_reviewers"),
            }
            for pr in pull_requests
        ],
    }


async def _execute_get_activity(session_id: str, names: list[str]) -> dict:
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

    facts = [_activity_facts(name, data) for (name, _), data in zip(found, activities)]
    return {"people": facts, "not_found": not_found}


def _row_to_openai_message(row: dict) -> dict:
    if row["role"] == "assistant" and row["tool_calls"]:
        return {"role": "assistant", "content": row["content"], "tool_calls": row["tool_calls"]}
    if row["role"] == "tool":
        return {"role": "tool", "tool_call_id": row["tool_call_id"], "content": row["content"]}
    return {"role": row["role"], "content": row["content"]}


_FALLBACK_ANSWER = "Sorry, I'm having trouble putting together an answer right now — try rephrasing?"


async def handle_message(session_id: str, user_message: str) -> str:
    """Answers a chat message, using the full session history for context.

    The LLM decides which people (if any) to look up via the get_activity_for_people
    tool, resolving pronouns/follow-ups from prior turns itself. Every turn (user,
    assistant, and tool) is persisted so the next call picks up the full thread.
    """
    client = _get_client()
    db.add_message(session_id, "user", content=user_message)

    messages = [_system_prompt()] + [_row_to_openai_message(row) for row in db.get_messages(session_id)]

    try:
        for _ in range(_MAX_HOPS):
            completion = await asyncio.to_thread(
                client.chat.completions.create,
                model=_OPENAI_MODEL,
                temperature=0.3,
                messages=messages,
                tools=[_TOOL],
                tool_choice="auto",
            )
            message = completion.choices[0].message

            if not message.tool_calls:
                answer = message.content or _FALLBACK_ANSWER
                db.add_message(session_id, "assistant", content=answer)
                return answer

            tool_calls_payload = [tool_call.model_dump() for tool_call in message.tool_calls]
            db.add_message(session_id, "assistant", content=message.content, tool_calls=tool_calls_payload)
            messages.append({"role": "assistant", "content": message.content, "tool_calls": tool_calls_payload})

            for tool_call in message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                result = await _execute_get_activity(session_id, args.get("names", []))
                content = json.dumps(result)
                db.add_message(session_id, "tool", content=content, tool_call_id=tool_call.id)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": content})
    except OpenAIError:
        db.add_message(session_id, "assistant", content=_FALLBACK_ANSWER)
        return _FALLBACK_ANSWER

    db.add_message(session_id, "assistant", content=_FALLBACK_ANSWER)
    return _FALLBACK_ANSWER
