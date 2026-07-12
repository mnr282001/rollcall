from __future__ import annotations

import httpx

_TIMEOUT = 10.0


class JiraError(Exception):
    """Base class for all jira_client errors."""


class JiraAuthError(JiraError):
    """Raised when the session's Jira access token is missing/invalid/expired."""


class JiraConnectionError(JiraError):
    """Raised on network failures/timeouts talking to JIRA."""


def _request(method: str, access_token: str, cloud_id: str, path: str, **kwargs) -> httpx.Response:
    base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    try:
        response = httpx.request(
            method, f"{base_url}{path}", headers=headers, timeout=_TIMEOUT, **kwargs
        )
    except httpx.RequestError as exc:
        raise JiraConnectionError(f"Could not reach JIRA: {exc}") from exc

    if response.status_code in (401, 403):
        raise JiraAuthError("Jira rejected the access token (missing, invalid, or expired).")

    return response


def whoami(access_token: str, cloud_id: str) -> dict:
    """Sanity check: confirms the session's OAuth token works against a real JIRA endpoint."""
    response = _request("GET", access_token, cloud_id, "/rest/api/3/myself")
    response.raise_for_status()
    return response.json()


def fetch_assigned_issues_raw(access_token: str, cloud_id: str, account_id: str) -> dict:
    """Raw JQL search response for issues assigned to account_id."""
    response = _request(
        "GET",
        access_token,
        cloud_id,
        "/rest/api/3/search/jql",
        params={
            "jql": f"assignee={account_id}",
            "fields": "summary,status,updated",
        },
    )
    response.raise_for_status()
    return response.json()


def get_jira_issues(access_token: str, cloud_id: str, account_id: str) -> list[dict]:
    """Assigned issues for account_id, trimmed to the fields we need.

    "User not found" is an application-level concern (Phase 3's name -> accountId
    lookup dict), not something we ask Jira to verify here. An unknown or inactive
    account_id simply yields an empty list, same as a known account with no work.
    """
    raw = fetch_assigned_issues_raw(access_token, cloud_id, account_id)
    return [
        {
            "key": issue["key"],
            "summary": issue["fields"]["summary"],
            "status": issue["fields"]["status"]["name"],
            "updated": issue["fields"]["updated"],
        }
        for issue in raw["issues"]
    ]
