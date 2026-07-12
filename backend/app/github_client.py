from __future__ import annotations

import httpx

from app import db

_TIMEOUT = 10.0
_BASE_URL = "https://api.github.com"


class GitHubError(Exception):
    """Base class for all github_client errors."""


class GitHubAuthError(GitHubError):
    """Raised when there's no valid GitHub session."""


class GitHubConnectionError(GitHubError):
    """Raised on network failures/timeouts talking to GitHub."""


def _do_request(method: str, token: str, path: str, **kwargs) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        return httpx.request(method, f"{_BASE_URL}{path}", headers=headers, timeout=_TIMEOUT, **kwargs)
    except httpx.RequestError as exc:
        raise GitHubConnectionError(f"Could not reach GitHub: {exc}") from exc


def _request(method: str, session_id: str, path: str, **kwargs) -> httpx.Response:
    session = db.get_session(session_id)
    if not session or not session["github_token"]:
        raise GitHubAuthError("No GitHub session — visit /auth/github/login first.")

    response = _do_request(method, session["github_token"], path, **kwargs)

    if response.status_code in (401, 403):
        raise GitHubAuthError("GitHub rejected the access token.")

    return response


def whoami(session_id: str) -> dict:
    """Sanity check: confirms the session's OAuth token works against a real GitHub endpoint."""
    response = _request("GET", session_id, "/user")
    response.raise_for_status()
    return response.json()
