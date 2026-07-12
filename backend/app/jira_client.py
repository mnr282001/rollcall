from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]

_auth = (JIRA_EMAIL, JIRA_API_TOKEN)
_TIMEOUT = 10.0

# Hardcoded for now — Phase 3 replaces this with the name -> accountId lookup.
_HARDCODED_ACCOUNT_ID = "61e9d1c998cd6100706712a6"


class JiraError(Exception):
    """Base class for all jira_client errors."""


class JiraAuthError(JiraError):
    """Raised when the configured email/API token is rejected."""


class JiraUserNotFoundError(JiraError):
    """Raised when the JIRA account_id does not exist or isn't visible to us."""


class JiraConnectionError(JiraError):
    """Raised on network failures/timeouts talking to JIRA."""


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        response = httpx.request(
            method, f"{JIRA_BASE_URL}{path}", auth=_auth, timeout=_TIMEOUT, **kwargs
        )
    except httpx.RequestError as exc:
        raise JiraConnectionError(f"Could not reach JIRA: {exc}") from exc

    if response.status_code in (401, 403):
        raise JiraAuthError("JIRA rejected the configured email/API token.")

    return response


def whoami() -> dict:
    """Step 1 sanity check: confirms auth works against a real JIRA endpoint."""
    response = _request("GET", "/rest/api/3/myself")
    response.raise_for_status()
    return response.json()


def _assert_user_exists(account_id: str) -> None:
    response = _request("GET", "/rest/api/3/user", params={"accountId": account_id})
    if response.status_code == 404:
        raise JiraUserNotFoundError(f"No JIRA user found for account_id={account_id!r}")
    response.raise_for_status()


def fetch_assigned_issues_raw(account_id: str) -> dict:
    """Step 2: raw JQL search response for issues assigned to account_id."""
    response = _request(
        "GET",
        "/rest/api/3/search/jql",
        params={
            "jql": f"assignee={account_id}",
            "fields": "summary,status,updated",
        },
    )
    response.raise_for_status()
    return response.json()


def get_jira_issues(account_id: str) -> list[dict]:
    """Step 4: assigned issues for account_id, trimmed to the fields we need.

    Raises JiraUserNotFoundError if the account doesn't exist; returns an empty
    list (not an error) if the account exists but has no assigned issues.
    """
    _assert_user_exists(account_id)
    raw = fetch_assigned_issues_raw(account_id)
    return [
        {
            "key": issue["key"],
            "summary": issue["fields"]["summary"],
            "status": issue["fields"]["status"]["name"],
            "updated": issue["fields"]["updated"],
        }
        for issue in raw["issues"]
    ]


if __name__ == "__main__":
    print(whoami())
    print(get_jira_issues(_HARDCODED_ACCOUNT_ID))

    try:
        get_jira_issues("nonexistent-account-id-1234")
    except JiraUserNotFoundError as exc:
        print(f"Handled as expected: {exc}")
