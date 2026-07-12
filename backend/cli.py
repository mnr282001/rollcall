from __future__ import annotations

import asyncio

from app import chat, db


def _get_any_session_id() -> str:
    session_id = db.get_any_session_id()
    if not session_id:
        raise SystemExit("No session found — log in via /auth/github/login and /auth/jira/login first.")
    return session_id


async def main() -> None:
    session_id = _get_any_session_id()
    print("Rollcall — ask a question, or type 'quit' to exit.")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("quit", "exit"):
            break
        if not question:
            continue
        print(await chat.handle_message(session_id, question))


if __name__ == "__main__":
    asyncio.run(main())
