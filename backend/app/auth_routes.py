from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import db, oauth_github, oauth_jira

router = APIRouter(prefix="/auth")

SESSION_COOKIE = "session_id"
GITHUB_STATE_COOKIE = "github_oauth_state"
JIRA_STATE_COOKIE = "jira_oauth_state"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# When the frontend and backend live on different domains (e.g. Vercel + Render),
# the session cookie needs SameSite=None + Secure or browsers drop it silently.
# Secure cookies require HTTPS, which is only true once we're actually deployed.
_CROSS_SITE = FRONTEND_URL.startswith("https://")
COOKIE_SAMESITE = "none" if _CROSS_SITE else "lax"
COOKIE_SECURE = _CROSS_SITE


@router.get("/github/login")
async def github_login():
    state = oauth_github.new_state()
    redirect = RedirectResponse(oauth_github.get_authorize_url(state))
    redirect.set_cookie(GITHUB_STATE_COOKIE, state, httponly=True, max_age=600, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE)
    return redirect


@router.get("/github/callback")
async def github_callback(request: Request, code: str, state: str):
    expected_state = request.cookies.get(GITHUB_STATE_COOKIE)
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    token = oauth_github.exchange_code_for_token(code)

    session_id = request.cookies.get(SESSION_COOKIE) or secrets.token_urlsafe(32)
    db.create_session(session_id)
    db.save_github_token(session_id, token)

    response = RedirectResponse(FRONTEND_URL)
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, max_age=60 * 60 * 24 * 30, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE)
    response.delete_cookie(GITHUB_STATE_COOKIE)
    return response


@router.get("/jira/login")
async def jira_login():
    state = oauth_jira.new_state()
    redirect = RedirectResponse(oauth_jira.get_authorize_url(state))
    redirect.set_cookie(JIRA_STATE_COOKIE, state, httponly=True, max_age=600, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE)
    return redirect


@router.get("/jira/callback")
async def jira_callback(request: Request, code: str, state: str):
    expected_state = request.cookies.get(JIRA_STATE_COOKIE)
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    access_token, refresh_token = oauth_jira.exchange_code_for_tokens(code)
    cloud_id = oauth_jira.get_cloud_id(access_token)

    session_id = request.cookies.get(SESSION_COOKIE) or secrets.token_urlsafe(32)
    db.create_session(session_id)
    db.save_jira_tokens(session_id, access_token, refresh_token, cloud_id)

    response = RedirectResponse(FRONTEND_URL)
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, max_age=60 * 60 * 24 * 30, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE)
    response.delete_cookie(JIRA_STATE_COOKIE)
    return response


@router.post("/github/logout")
async def github_logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        db.clear_github_token(session_id)
    return {"github_connected": False}


@router.post("/jira/logout")
async def jira_logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        db.clear_jira_tokens(session_id)
    return {"jira_connected": False}


@router.get("/me")
async def me(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return {
            "authenticated": False,
            "github_connected": False,
            "jira_connected": False,
        }

    session = db.get_session(session_id)
    if not session:
        return {
            "authenticated": False,
            "github_connected": False,
            "jira_connected": False,
        }

    return {
        "authenticated": True,
        "github_connected": session["github_token"] is not None,
        "jira_connected": session["jira_access_token"] is not None,
    }
