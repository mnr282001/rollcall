from __future__ import annotations

import os
import secrets
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
# Keep deployed values in .env, while allowing git-ignored local development
# settings to override them without changing production configuration.
load_dotenv(Path(__file__).resolve().parents[1] / ".env.local", override=True)

GITHUB_CLIENT_ID = os.environ["GITHUB_CLIENT_ID"]
GITHUB_CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
GITHUB_REDIRECT_URI = os.environ["GITHUB_REDIRECT_URI"]

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"


def new_state() -> str:
    return secrets.token_urlsafe(24)


def get_authorize_url(state: str) -> str:
    params = httpx.QueryParams(
        {
            "client_id": GITHUB_CLIENT_ID,
            "redirect_uri": GITHUB_REDIRECT_URI,
            "scope": "read:user repo",
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{params}"


def exchange_code_for_token(code: str) -> str:
    response = httpx.post(
        TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": GITHUB_REDIRECT_URI,
        },
    )
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise RuntimeError(f"GitHub OAuth error: {body}")
    return body["access_token"]
