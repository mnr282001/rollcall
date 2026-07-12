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


_RECENT_REPOS_LIMIT = 5


def get_recent_repos(session_id: str, limit: int = _RECENT_REPOS_LIMIT) -> list[dict]:
    """Repos the authenticated user has recently pushed to, most recent first.

    GitHub has no single endpoint for "everything a user worked on" — /user/repos
    sorted by push time is the practical stand-in, and doubles as the repo set we
    pull commits/PRs from.
    """
    response = _request(
        "GET",
        session_id,
        "/user/repos",
        params={"sort": "pushed", "direction": "desc", "per_page": limit},
    )
    response.raise_for_status()
    return [
        {
            "full_name": repo["full_name"],
            "pushed_at": repo["pushed_at"],
            "private": repo["private"],
        }
        for repo in response.json()
    ]


_COMMITS_PER_REPO = 5


def get_recent_commits(session_id: str, username: str, repo_limit: int = _RECENT_REPOS_LIMIT) -> list[dict]:
    """Recent commits by username, across the user's most recently pushed repos.

    Commits are scoped per-repo in GitHub's API, so this fans out across the
    top `repo_limit` recently-pushed repos rather than one global query.
    """
    commits: list[dict] = []
    for repo in get_recent_repos(session_id, limit=repo_limit):
        response = _request(
            "GET",
            session_id,
            f"/repos/{repo['full_name']}/commits",
            params={"author": username, "per_page": _COMMITS_PER_REPO},
        )
        if response.status_code == 409:
            # Empty repository (no commits yet) — GitHub returns 409, not an empty list.
            continue
        response.raise_for_status()
        for commit in response.json():
            commits.append(
                {
                    "repo": repo["full_name"],
                    "sha": commit["sha"][:7],
                    "message": commit["commit"]["message"].splitlines()[0],
                    "date": commit["commit"]["author"]["date"],
                }
            )
    return commits


def get_open_pull_requests(session_id: str, username: str, repo_limit: int = _RECENT_REPOS_LIMIT) -> list[dict]:
    """Open PRs authored by username, across the user's most recently pushed repos.

    The PRs-list endpoint has no "author" filter, so we fetch each repo's open
    PRs and filter by author client-side.
    """
    pull_requests: list[dict] = []
    for repo in get_recent_repos(session_id, limit=repo_limit):
        response = _request(
            "GET",
            session_id,
            f"/repos/{repo['full_name']}/pulls",
            params={"state": "open", "per_page": 20},
        )
        response.raise_for_status()
        for pr in response.json():
            if pr["user"]["login"] != username:
                continue
            pull_requests.append(
                {
                    "repo": repo["full_name"],
                    "number": pr["number"],
                    "title": pr["title"],
                    "updated_at": pr["updated_at"],
                }
            )
    return pull_requests
