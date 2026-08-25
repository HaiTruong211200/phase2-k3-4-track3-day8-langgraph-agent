"""Checkpointer adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _sqlite_database_path(database_url: str | None) -> tuple[str, bool]:
    """Normalize a SQLite URL/path and report whether URI connection mode is needed."""
    value = database_url or "outputs/checkpoints.sqlite"
    if value.startswith("sqlite:///"):
        value = value.removeprefix("sqlite:///")
    elif value.startswith("sqlite://"):
        raise ValueError("SQLite URL must use sqlite:///path/to/database.sqlite")

    if value == ":memory:" or value.startswith("file:"):
        return value, value.startswith("file:")

    path = Path(value).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path), False


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer.

    TODO(student): implement SQLite support for the persistence extension track.
    The starter provides MemorySaver only — SQLite/Postgres are extension tasks.

    For SQLite:
    - pip install langgraph-checkpoint-sqlite
    - Use SqliteSaver with sqlite3.connect() and WAL mode
    - See: https://langchain-ai.github.io/langgraph/how-tos/persistence/
    """
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError(
                "SQLite persistence requires the optional dependency: "
                "pip install langgraph-checkpoint-sqlite"
            ) from exc

        database, uri = _sqlite_database_path(database_url)
        connection = sqlite3.connect(
            database,
            check_same_thread=False,
            timeout=30.0,
            uri=uri,
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.commit()
        return SqliteSaver(conn=connection)
    if kind == "postgres":
        raise NotImplementedError(
            "TODO(student): implement Postgres checkpointer (optional extension)"
        )
    raise ValueError(f"Unknown checkpointer kind: {kind}")
