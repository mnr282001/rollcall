from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request

from app import db, jira_client
from app.auth_routes import SESSION_COOKIE, router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
async def read_item(item_id: int, q: Optional[str] = None):
    return {"item_id": item_id, "q": q}


# Temporary manual-testing endpoint for Phase 1 — remove once Phase 3/4 wire the
# real /ask flow through the query parser and name -> accountId lookup.
@app.get("/debug/jira-issues")
async def debug_jira_issues(request: Request, account_id: str = "61e9d1c998cd6100706712a6"):
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not logged in — visit /auth/jira/login first")

    session = db.get_session(session_id)
    if not session or not session["jira_access_token"]:
        raise HTTPException(status_code=401, detail="Jira not connected — visit /auth/jira/login first")

    try:
        issues = jira_client.get_jira_issues(session_id, account_id)
    except jira_client.JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return {"account_id": account_id, "issues": issues}