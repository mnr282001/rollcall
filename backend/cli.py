from __future__ import annotations

import asyncio
import sqlite3

from app import activity, query_parser, response_generator, users
from app.db import DB_PATH


def _get_any_session_id() -> str:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT session_id FROM sessions LIMIT 1").fetchone()
    if not row:
        raise SystemExit("No session found — log in via /auth/github/login and /auth/jira/login first.")
    return row[0]


async def answer(session_id: str, question: str) -> str:
    name = query_parser.parse_name(question)
    if not name:
        return "Sorry, I couldn't figure out who you're asking about."

    user = users.lookup_user(name)
    if not user:
        return f"Sorry, I don't know anyone named {name}."

    data = await activity.get_user_activity(session_id, user["jira_account_id"], user["github_username"])
    return response_generator.generate_response(name, data)


async def main() -> None:
    session_id = _get_any_session_id()
    print("Team Activity Monitor — ask a question, or type 'quit' to exit.")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("quit", "exit"):
            break
        if not question:
            continue
        print(await answer(session_id, question))


if __name__ == "__main__":
    asyncio.run(main())
