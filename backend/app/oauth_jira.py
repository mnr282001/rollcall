from __future__ import annotations

import base64
import json
import os
import secrets
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
# Keep deployed values in .env, while allowing git-ignored local development
# settings to override them without changing production configuration.
load_dotenv(Path(__file__).resolve().parents[1] / ".env.local", override=True)

JIRA_OAUTH_CLIENT_ID = os.environ["JIRA_OAUTH_CLIENT_ID"]
JIRA_OAUTH_CLIENT_SECRET = os.environ["JIRA_OAUTH_CLIENT_SECRET"]
JIRA_OAUTH_REDIRECT_URI = os.environ["JIRA_OAUTH_REDIRECT_URI"]

AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"


def new_state() -> str:
    return secrets.token_urlsafe(24)


def get_authorize_url(state: str) -> str:
    params = httpx.QueryParams(
        {
            "audience": "api.atlassian.com",
            "client_id": JIRA_OAUTH_CLIENT_ID,
            "scope": "read:jira-work read:jira-user offline_access",
            "redirect_uri": JIRA_OAUTH_REDIRECT_URI,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
    )
    return f"{AUTHORIZE_URL}?{params}"


def exchange_code_for_tokens(code: str) -> tuple[str, str]:
    """Returns (access_token, refresh_token)."""
    response = httpx.post(
        TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": JIRA_OAUTH_CLIENT_ID,
            "client_secret": JIRA_OAUTH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": JIRA_OAUTH_REDIRECT_URI,
        },
    )
    response.raise_for_status()
    body = response.json()
    return body["access_token"], body["refresh_token"]


def refresh_access_token(refresh_token: str) -> tuple[str, str]:
    """Returns a new (access_token, refresh_token) using a stored refresh token."""
    response = httpx.post(
        TOKEN_URL,
        json={
            "grant_type": "refresh_token",
            "client_id": JIRA_OAUTH_CLIENT_ID,
            "client_secret": JIRA_OAUTH_CLIENT_SECRET,
            "refresh_token": refresh_token,
        },
    )
    response.raise_for_status()
    body = response.json()
    return body["access_token"], body["refresh_token"]


def is_token_expired(access_token: str, leeway_seconds: int = 30) -> bool:
    """Decodes the JWT's exp claim locally (no signature check needed — we're only
    reading our own stored token to decide whether to refresh, not authenticating
    the caller). Jira's /search/jql silently returns empty results for a stale
    token instead of 401ing, so we can't rely on a failed request to tell us.
    """
    try:
        payload_b64 = access_token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return time.time() >= (payload["exp"] - leeway_seconds)
    except (IndexError, ValueError, KeyError):
        return True


def get_cloud_id(access_token: str) -> str:
    """The first accessible Jira site's cloudId (fine for a single-workspace demo)."""
    response = httpx.get(
        ACCESSIBLE_RESOURCES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    resources = response.json()
    if not resources:
        raise RuntimeError("No accessible Jira sites for this account")
    return resources[0]["id"]
