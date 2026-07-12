from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    return _client


def init_db() -> None:
    """Schema lives in Supabase migrations, not here — this just confirms connectivity."""
    _get_client()


def create_session(session_id: str) -> None:
    _get_client().table("sessions").upsert({"session_id": session_id}, on_conflict="session_id").execute()


def save_github_token(session_id: str, token: str) -> None:
    _get_client().table("sessions").update({"github_token": token}).eq("session_id", session_id).execute()


def save_jira_tokens(session_id: str, access_token: str, refresh_token: str, cloud_id: str) -> None:
    _get_client().table("sessions").update(
        {
            "jira_access_token": access_token,
            "jira_refresh_token": refresh_token,
            "jira_cloud_id": cloud_id,
        }
    ).eq("session_id", session_id).execute()


def clear_github_token(session_id: str) -> None:
    _get_client().table("sessions").update({"github_token": None}).eq("session_id", session_id).execute()


def clear_jira_tokens(session_id: str) -> None:
    _get_client().table("sessions").update(
        {
            "jira_access_token": None,
            "jira_refresh_token": None,
            "jira_cloud_id": None,
        }
    ).eq("session_id", session_id).execute()


def get_any_session_id() -> str | None:
    """Used only by cli.py, which has no cookie to read a session_id from.

    Prefers a session with both tokens present — cli.py needs both Jira and
    GitHub to answer anything, and picking an incomplete session at random
    would fail every query.
    """
    result = (
        _get_client()
        .table("sessions")
        .select("session_id")
        .not_.is_("jira_access_token", "null")
        .not_.is_("github_token", "null")
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["session_id"]

    result = _get_client().table("sessions").select("session_id").limit(1).execute()
    return result.data[0]["session_id"] if result.data else None


def get_session(session_id: str) -> dict | None:
    result = _get_client().table("sessions").select("*").eq("session_id", session_id).execute()
    return result.data[0] if result.data else None


def add_team_member(name: str, jira_account_id: str, github_username: str | None) -> None:
    _get_client().table("team_members").upsert(
        {
            "name": name.strip().lower(),
            "jira_account_id": jira_account_id,
            "github_username": github_username,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="name",
    ).execute()


def get_team_member(name: str) -> dict | None:
    result = (
        _get_client().table("team_members").select("*").eq("name", name.strip().lower()).execute()
    )
    return result.data[0] if result.data else None
