from __future__ import annotations

import asyncio

from app import activity, db, query_parser, response_generator, users


def _get_any_session_id() -> str:
    session_id = db.get_any_session_id()
    if not session_id:
        raise SystemExit("No session found — log in via /auth/github/login and /auth/jira/login first.")
    return session_id


async def answer(session_id: str, question: str) -> str:
    names = query_parser.parse_names(question)
    if not names:
        return "Sorry, I couldn't figure out who you're asking about."

    resolved_users = list(
        zip(names, await asyncio.gather(*(users.resolve_user(session_id, name) for name in names)))
    )
    not_found = [name for name, user in resolved_users if user is None]
    found = [(name, user) for name, user in resolved_users if user is not None]

    activities = await asyncio.gather(
        *(
            activity.get_user_activity(session_id, user["jira_account_id"], user["github_username"])
            for name, user in found
        )
    )
    resolved = list(zip((name for name, _ in found), activities))
    return response_generator.generate_combined_response(resolved, not_found)


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
