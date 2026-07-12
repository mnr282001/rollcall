from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "sessions.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                github_token TEXT,
                jira_access_token TEXT,
                jira_refresh_token TEXT,
                jira_cloud_id TEXT
            )
            """
        )


def create_session(session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)", (session_id,)
        )


def save_github_token(session_id: str, token: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET github_token = ? WHERE session_id = ?",
            (token, session_id),
        )


def save_jira_tokens(
    session_id: str, access_token: str, refresh_token: str, cloud_id: str
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET jira_access_token = ?, jira_refresh_token = ?, jira_cloud_id = ?
            WHERE session_id = ?
            """,
            (access_token, refresh_token, cloud_id, session_id),
        )


def get_session(session_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
