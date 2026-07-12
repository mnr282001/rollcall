from __future__ import annotations

import httpx

from app import db, oauth_jira

_TIMEOUT = 10.0


class JiraError(Exception):
    """Base class for all jira_client errors."""


class JiraAuthError(JiraError):
    """Raised when there's no valid Jira session, even after attempting a refresh."""


class JiraConnectionError(JiraError):
    """Raised on network failures/timeouts talking to JIRA."""


async def _do_request(method: str, access_token: str, cloud_id: str, path: str, **kwargs) -> httpx.Response:
    base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            return await client.request(method, f"{base_url}{path}", headers=headers, **kwargs)
    except httpx.RequestError as exc:
        raise JiraConnectionError(f"Could not reach JIRA: {exc}") from exc


async def _get_valid_access_token(session_id: str, session) -> str:
    """Refreshes proactively if the token is expired.

    Jira's /search/jql silently returns an empty result set for a stale token
    instead of 401ing, so we can't wait for a failed request to tell us — we
    check the JWT's own exp claim before every call instead.
    """
    access_token = session["jira_access_token"]
    if not oauth_jira.is_token_expired(access_token):
        return access_token

    if not session["jira_refresh_token"]:
        raise JiraAuthError("Jira access token expired and no refresh token is stored.")

    new_access_token, new_refresh_token = oauth_jira.refresh_access_token(session["jira_refresh_token"])
    db.save_jira_tokens(session_id, new_access_token, new_refresh_token, session["jira_cloud_id"])
    return new_access_token


async def _request(method: str, session_id: str, path: str, **kwargs) -> httpx.Response:
    session = db.get_session(session_id)
    if not session or not session["jira_access_token"]:
        raise JiraAuthError("No Jira session — visit /auth/jira/login first.")

    access_token = await _get_valid_access_token(session_id, session)
    response = await _do_request(method, access_token, session["jira_cloud_id"], path, **kwargs)

    if response.status_code in (401, 403):
        raise JiraAuthError("Jira rejected the access token even after a freshness check.")

    return response


async def whoami(session_id: str) -> dict:
    """Sanity check: confirms the session's OAuth token works against a real JIRA endpoint."""
    response = await _request("GET", session_id, "/rest/api/3/myself")
    response.raise_for_status()
    return response.json()


async def fetch_assigned_issues_raw(session_id: str, account_id: str) -> dict:
    """Raw JQL search response for issues assigned to account_id."""
    response = await _request(
        "GET",
        session_id,
        "/rest/api/3/search/jql",
        params={
            "jql": f"assignee={account_id}",
            "fields": "summary,status,updated",
        },
    )
    response.raise_for_status()
    return response.json()


async def get_jira_issues(session_id: str, account_id: str) -> list[dict]:
    """Assigned issues for account_id, trimmed to the fields we need.

    "User not found" is an application-level concern (Phase 3's name -> accountId
    lookup dict), not something we ask Jira to verify here. An unknown or inactive
    account_id simply yields an empty list, same as a known account with no work.
    """
    raw = await fetch_assigned_issues_raw(session_id, account_id)
    return [
        {
            "key": issue["key"],
            "summary": issue["fields"]["summary"],
            "status": issue["fields"]["status"]["name"],
            "updated": issue["fields"]["updated"],
        }
        for issue in raw["issues"]
    ]
