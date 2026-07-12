from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import chat, db
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


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str


def _require_session(request: Request) -> str:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id or not db.get_session(session_id):
        raise HTTPException(status_code=401, detail="Not logged in — visit /auth/github/login and /auth/jira/login first")
    return session_id


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: Request, body: ChatRequest):
    session_id = _require_session(request)
    try:
        answer = await chat.handle_message(session_id, body.message)
    except chat.NotConfiguredError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(answer=answer)


@app.get("/chat/history")
async def chat_history(request: Request):
    session_id = _require_session(request)
    rows = db.get_messages(session_id)
    return {
        "messages": [
            {"role": row["role"], "content": row["content"]}
            for row in rows
            if row["role"] in ("user", "assistant") and row["content"]
        ]
    }


@app.delete("/chat/history")
async def reset_chat(request: Request):
    session_id = _require_session(request)
    db.delete_messages(session_id)
    return {"ok": True}
