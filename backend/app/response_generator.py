from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

load_dotenv()

_OPENAI_MODEL = "gpt-4o-mini"
_client: OpenAI | None = None


def _get_client() -> OpenAI | None:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    _client = OpenAI(api_key=api_key)
    return _client


def _activity_facts(name: str, activity: dict) -> dict:
    """Structured, LLM-safe summary of one person's activity — no free text for the model to embellish."""
    commits = activity["github_commits"]
    pull_requests = activity["github_pull_requests"]
    return {
        "name": name,
        "jira_issues": [
            {
                "key": issue["key"],
                "status": issue["status"],
                "summary": issue["summary"],
                "updated": issue["updated"],
            }
            for issue in activity["jira_issues"]
        ],
        "has_linked_github": commits is not None,
        "github_commits": None if commits is None else [
            {"repo": commit["repo"], "message": commit["message"], "sha": commit["sha"]} for commit in commits
        ],
        "github_pull_requests": None if pull_requests is None else [
            {"repo": pr["repo"], "number": pr["number"], "title": pr["title"]} for pr in pull_requests
        ],
    }


def _llm_answer(question: str, facts: list[dict], not_found: list[str]) -> str | None:
    """Asks OpenAI to answer the original question from the facts. Returns None on any failure or missing key."""
    client = _get_client()
    if client is None:
        return None

    try:
        completion = client.chat.completions.create(
            model=_OPENAI_MODEL,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Rollcall, a teammate-activity assistant. Answer the user's question "
                        "conversationally using ONLY the JSON facts provided — never invent JIRA tickets, "
                        "commits, PRs, or people beyond what's given. Tailor the answer to what was actually "
                        "asked: if the question is about JIRA specifically, focus on that instead of dumping "
                        "GitHub activity too, and vice versa. If a name appears in `not_found`, say you don't "
                        "know that person. If a person has `has_linked_github: false`, mention they have no "
                        "linked GitHub account rather than guessing about their code activity. Each JIRA issue "
                        "has an `updated` timestamp — if the question asks about a specific time frame (e.g. "
                        "'today', 'this week'), only count issues whose `updated` falls in that window, and say "
                        "there's no activity in that window if none qualify. Never state that someone did or "
                        "didn't do something in a time frame you weren't given a timestamp to check. Keep it "
                        "brief and natural, like a helpful teammate would answer."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\n"
                        f"Facts:\n{json.dumps({'people': facts, 'not_found': not_found}, indent=2)}"
                    ),
                },
            ],
        )
        return completion.choices[0].message.content
    except OpenAIError:
        return None


def _format_issues(issues: list[dict]) -> str:
    if not issues:
        return "no open JIRA issues"
    lines = [f"  - {issue['key']} ({issue['status']}): {issue['summary']}" for issue in issues[:5]]
    more = f"\n  ...and {len(issues) - 5} more" if len(issues) > 5 else ""
    return f"{len(issues)} JIRA issue(s):\n" + "\n".join(lines) + more


def _format_commits(commits: list[dict]) -> str:
    if not commits:
        return "no recent commits"
    lines = [f"  - [{commit['repo']}] {commit['message']} ({commit['sha']})" for commit in commits[:5]]
    more = f"\n  ...and {len(commits) - 5} more" if len(commits) > 5 else ""
    return f"{len(commits)} recent commit(s):\n" + "\n".join(lines) + more


def _format_pull_requests(pull_requests: list[dict]) -> str:
    if not pull_requests:
        return "no open pull requests"
    lines = [f"  - [{pr['repo']}] #{pr['number']}: {pr['title']}" for pr in pull_requests]
    return f"{len(pull_requests)} open pull request(s):\n" + "\n".join(lines)


def generate_response(name: str, activity: dict) -> str:
    """Combines JIRA + GitHub activity into one conversational answer."""
    issues = activity["jira_issues"]
    commits = activity["github_commits"]
    pull_requests = activity["github_pull_requests"]

    if commits is None and pull_requests is None:
        if not issues:
            return f"{name} doesn't have any recent JIRA activity, and has no linked GitHub account."
        return f"Here's what {name} has been working on:\n\nJIRA: {_format_issues(issues)}\n\n(No linked GitHub account.)"

    if not issues and not commits and not pull_requests:
        return f"{name} doesn't have any recent JIRA or GitHub activity."

    return (
        f"Here's what {name} has been working on:\n\n"
        f"JIRA: {_format_issues(issues)}\n\n"
        f"GitHub commits: {_format_commits(commits)}\n\n"
        f"GitHub PRs: {_format_pull_requests(pull_requests)}"
    )


def generate_combined_response(
    resolved: list[tuple[str, dict]], not_found: list[str], question: str | None = None
) -> str:
    """Combines per-person answers for a multi-name query into one response.

    When `question` is given and OPENAI_API_KEY is configured, an LLM phrases the
    answer around what was actually asked (e.g. "just JIRA tickets"). Falls back to
    the deterministic dump below if there's no key, the question is missing, or the
    OpenAI call fails.
    """
    if not resolved and not not_found:
        return "Sorry, I couldn't figure out who you're asking about."

    if question:
        facts = [_activity_facts(name, data) for name, data in resolved]
        llm_answer = _llm_answer(question, facts, not_found)
        if llm_answer:
            return llm_answer

    sections = [generate_response(name, data) for name, data in resolved]
    if not_found:
        names = ", ".join(not_found)
        sections.append(f"I don't know anyone named {names}.")

    return "\n\n---\n\n".join(sections)
