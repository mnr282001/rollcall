from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import activity, db, github_client, jira_client, query_parser, response_generator, users
from app.auth_routes import SESSION_COOKIE, router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


class AddUserRequest(BaseModel):
    name: str
    jira_account_id: str
    github_username: str


@app.post("/admin/users", status_code=201)
async def add_user(request: Request, body: AddUserRequest):
    # Gated behind "logged in to this app at all" rather than a real admin role —
    # there's no RBAC system here, just a way to keep this off the open internet.
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id or not db.get_session(session_id):
        raise HTTPException(status_code=401, detail="Not logged in")

    db.add_team_member(body.name, body.jira_account_id, body.github_username)
    return {"name": body.name.strip().lower()}


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


@app.post("/ask", response_model=AskResponse)
async def ask(request: Request, body: AskRequest):
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not logged in — visit /auth/github/login and /auth/jira/login first")

    names = query_parser.parse_names(body.question)
    if not names:
        return AskResponse(answer="Sorry, I couldn't figure out who you're asking about.")

    try:
        resolved_users = list(
            zip(names, await asyncio.gather(*(users.resolve_user(session_id, name) for name in names)))
        )
    except (jira_client.JiraAuthError, github_client.GitHubAuthError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (jira_client.JiraConnectionError, github_client.GitHubConnectionError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    not_found = [name for name, user in resolved_users if user is None]
    found = [(name, user) for name, user in resolved_users if user is not None]

    try:
        activities = await asyncio.gather(
            *(
                activity.get_user_activity(session_id, user["jira_account_id"], user["github_username"])
                for name, user in found
            )
        )
    except (jira_client.JiraAuthError, github_client.GitHubAuthError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (jira_client.JiraConnectionError, github_client.GitHubConnectionError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    resolved = list(zip((name for name, _ in found), activities))
    return AskResponse(answer=response_generator.generate_combined_response(resolved, not_found))
