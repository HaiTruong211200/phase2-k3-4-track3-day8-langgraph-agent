from __future__ import annotations

from typing import TypedDict

import pytest

from langgraph_agent_lab.persistence import build_checkpointer


class CounterState(TypedDict):
    count: int


def _build_counter_graph(checkpointer):
    pytest.importorskip("langgraph")
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(CounterState)
    builder.add_node("increment", lambda state: {"count": state["count"] + 1})
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)
    return builder.compile(checkpointer=checkpointer)


def test_sqlite_checkpointer_uses_wal(tmp_path):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    checkpointer = build_checkpointer("sqlite", str(tmp_path / "checkpoints.sqlite"))
    try:
        journal_mode = checkpointer.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"
    finally:
        checkpointer.conn.close()


def test_sqlite_state_survives_reopen(tmp_path):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    database = tmp_path / "resume.sqlite"
    config = {"configurable": {"thread_id": "persistence-test"}}

    first_checkpointer = build_checkpointer("sqlite", str(database))
    first_graph = _build_counter_graph(first_checkpointer)
    assert first_graph.invoke({"count": 0}, config=config)["count"] == 1
    first_checkpointer.conn.close()

    reopened_checkpointer = build_checkpointer("sqlite", str(database))
    try:
        reopened_graph = _build_counter_graph(reopened_checkpointer)
        assert reopened_graph.get_state(config).values["count"] == 1
        assert len(list(reopened_graph.get_state_history(config))) >= 2
    finally:
        reopened_checkpointer.conn.close()
