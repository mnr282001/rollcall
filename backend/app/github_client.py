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


async def _do_request(method: str, token: str, path: str, **kwargs) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            return await client.request(method, f"{_BASE_URL}{path}", headers=headers, **kwargs)
    except httpx.RequestError as exc:
        raise GitHubConnectionError(f"Could not reach GitHub: {exc}") from exc


async def _request(method: str, session_id: str, path: str, **kwargs) -> httpx.Response:
    session = db.get_session(session_id)
    if not session or not session["github_token"]:
        raise GitHubAuthError("No GitHub session — visit /auth/github/login first.")

    response = await _do_request(method, session["github_token"], path, **kwargs)

    if response.status_code in (401, 403):
        raise GitHubAuthError("GitHub rejected the access token.")

    return response


async def whoami(session_id: str) -> dict:
    """Sanity check: confirms the session's OAuth token works against a real GitHub endpoint."""
    response = await _request("GET", session_id, "/user")
    response.raise_for_status()
    return response.json()


async def get_user_orgs(session_id: str) -> list[str]:
    """Orgs the authenticated session's own GitHub account belongs to."""
    response = await _request("GET", session_id, "/user/orgs", params={"per_page": 100})
    response.raise_for_status()
    return [org["login"] for org in response.json()]


_MEMBERS_LIMIT = 100


async def find_user_by_name(session_id: str, name: str) -> str | None:
    """Searches members of the session's own GitHub orgs by display name.

    GitHub's org-members list only returns logins, not display names, so each
    member needs a follow-up profile fetch — expensive for large orgs, but
    there's no bulk "members with profile" endpoint. Only an exact display
    name match counts; ambiguous or no matches return None rather than
    guessing, same policy as jira_client.find_user_by_name.
    """
    name_lower = name.strip().lower()
    matches: list[str] = []

    for org in await get_user_orgs(session_id):
        response = await _request("GET", session_id, f"/orgs/{org}/members", params={"per_page": _MEMBERS_LIMIT})
        response.raise_for_status()
        for member in response.json():
            profile_response = await _request("GET", session_id, f"/users/{member['login']}")
            profile_response.raise_for_status()
            profile = profile_response.json()
            if (profile.get("name") or "").strip().lower() == name_lower:
                matches.append(member["login"])

    return matches[0] if len(matches) == 1 else None


_RECENT_REPOS_LIMIT = 5


async def get_recent_repos(session_id: str, limit: int = _RECENT_REPOS_LIMIT) -> list[dict]:
    """Repos the authenticated user has recently pushed to, most recent first.

    GitHub has no single endpoint for "everything a user worked on" — /user/repos
    sorted by push time is the practical stand-in, and doubles as the repo set we
    pull commits/PRs from.
    """
    response = await _request(
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


async def get_recent_commits(
    session_id: str, username: str, repo_limit: int = _RECENT_REPOS_LIMIT, repos: list[dict] | None = None
) -> list[dict]:
    """Recent commits by username, across the user's most recently pushed repos.

    Commits are scoped per-repo in GitHub's API, so this fans out across the
    top `repo_limit` recently-pushed repos rather than one global query. Pass
    `repos` (from a prior get_recent_repos call) to avoid refetching it.
    """
    if repos is None:
        repos = await get_recent_repos(session_id, limit=repo_limit)
    commits: list[dict] = []
    for repo in repos:
        response = await _request(
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


async def get_open_pull_requests(
    session_id: str, username: str, repo_limit: int = _RECENT_REPOS_LIMIT, repos: list[dict] | None = None
) -> list[dict]:
    """Open PRs authored by username, across the user's most recently pushed repos.

    The PRs-list endpoint has no "author" filter, so we fetch each repo's open
    PRs and filter by author client-side. Pass `repos` (from a prior
    get_recent_repos call) to avoid refetching it.
    """
    if repos is None:
        repos = await get_recent_repos(session_id, limit=repo_limit)
    pull_requests: list[dict] = []
    for repo in repos:
        response = await _request(
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
                    "draft": pr["draft"],
                    "requested_reviewers": [reviewer["login"] for reviewer in pr["requested_reviewers"]],
                }
            )
    return pull_requests
