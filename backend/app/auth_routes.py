from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import db, oauth_github, oauth_jira

router = APIRouter(prefix="/auth")

SESSION_COOKIE = "session_id"
GITHUB_STATE_COOKIE = "github_oauth_state"
JIRA_STATE_COOKIE = "jira_oauth_state"


@router.get("/github/login")
async def github_login():
    state = oauth_github.new_state()
    redirect = RedirectResponse(oauth_github.get_authorize_url(state))
    redirect.set_cookie(GITHUB_STATE_COOKIE, state, httponly=True, max_age=600)
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

    response = RedirectResponse("/")
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, max_age=60 * 60 * 24 * 30)
    response.delete_cookie(GITHUB_STATE_COOKIE)
    return response


@router.get("/jira/login")
async def jira_login():
    state = oauth_jira.new_state()
    redirect = RedirectResponse(oauth_jira.get_authorize_url(state))
    redirect.set_cookie(JIRA_STATE_COOKIE, state, httponly=True, max_age=600)
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

    response = RedirectResponse("/")
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, max_age=60 * 60 * 24 * 30)
    response.delete_cookie(JIRA_STATE_COOKIE)
    return response


@router.get("/me")
async def me(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return {"authenticated": False}

    session = db.get_session(session_id)
    if not session:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "github_connected": session["github_token"] is not None,
        "jira_connected": session["jira_access_token"] is not None,
    }
