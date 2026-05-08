from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from a2a.types import Artifact, Message, TaskState


DB_PATH = os.getenv("AML_DB_PATH", "./aml.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.executescript(sql)


def create_session(session_id: str, user_query: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions(session_id, user_query) VALUES (?, ?)",
            (session_id, user_query),
        )


def finalize_session(session_id: str, final_report: dict, risk_level: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET final_report = ?, risk_level = ?, completed_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            (json.dumps(final_report, ensure_ascii=True), risk_level, session_id),
        )


def create_task(task_id: str, session_id: str, source_agent: str, target_agent: str, state: TaskState) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO tasks(task_id, session_id, source_agent, target_agent, state)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, session_id, source_agent, target_agent, state.value),
        )


def update_task_state(task_id: str, state: TaskState) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE tasks SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
            (state.value, task_id),
        )


def add_message(task_id: str, message: Message) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO messages(message_id, task_id, role, parts_json) VALUES (?, ?, ?, ?)",
            (
                message.message_id,
                task_id,
                message.role,
                json.dumps([part.model_dump(mode="json") for part in message.parts], ensure_ascii=True),
            ),
        )


def add_artifact(task_id: str, artifact: Artifact) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO artifacts(artifact_id, task_id, name, parts_json) VALUES (?, ?, ?, ?)",
            (
                artifact.artifact_id,
                task_id,
                artifact.name,
                json.dumps([part.model_dump(mode="json") for part in artifact.parts], ensure_ascii=True),
            ),
        )
