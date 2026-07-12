from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from app import activity, db, github_client, jira_client, query_parser, response_generator, users
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


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


@app.post("/ask", response_model=AskResponse)
async def ask(request: Request, body: AskRequest):
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not logged in — visit /auth/github/login and /auth/jira/login first")

    name = query_parser.parse_name(body.question)
    if not name:
        return AskResponse(answer="Sorry, I couldn't figure out who you're asking about.")

    user = users.lookup_user(name)
    if not user:
        return AskResponse(answer=f"Sorry, I don't know anyone named {name}.")

    try:
        data = await activity.get_user_activity(session_id, user["jira_account_id"], user["github_username"])
    except (jira_client.JiraAuthError, github_client.GitHubAuthError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (jira_client.JiraConnectionError, github_client.GitHubConnectionError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AskResponse(answer=response_generator.generate_response(name, data))
