"""Mermaid helpers for visualizing live LangGraph execution."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def execution_mermaid(
    graph: Any,
    *,
    active_nodes: Iterable[str] = (),
    completed_nodes: Iterable[str] = (),
) -> str:
    """Export the compiled graph and add execution-state classes."""
    source = graph.get_graph().draw_mermaid()
    # LangGraph exports a top-down graph by default. A left-to-right layout is
    # easier to scan as an execution timeline in the review console.
    source = source.replace("graph TD;", "flowchart LR;", 1)
    known_nodes = set(graph.get_graph().nodes)
    active = sorted(set(active_nodes) & known_nodes)
    completed = sorted((set(completed_nodes) - set(active)) & known_nodes)
    decorations = [
        "classDef step fill:#f8fafc,stroke:#94a3b8,stroke-width:1.5px,color:#172033;",
        "classDef decision fill:#fff7ed,stroke:#f59e0b,stroke-width:2px,color:#7c2d12;",
        "classDef toolNode fill:#f5f3ff,stroke:#8b5cf6,stroke-width:2px,color:#4c1d95;",
        "classDef guard fill:#fff1f2,stroke:#f43f5e,stroke-width:2px,color:#881337;",
        "classDef terminal fill:#eef2ff,stroke:#6366f1,stroke-width:2px,color:#312e81;",
        "class intake,answer,clarify,merge_tools step;",
        "class classify,evaluate,retry decision;",
        "class tool,tool_dispatch,parallel_tool toolNode;",
        "class risky_action,approval guard;",
        "class dead_letter,finalize terminal;",
        "classDef active fill:#dbeafe,stroke:#2563eb,stroke-width:4px,"
        "color:#172033,font-weight:bold;",
        "classDef completed fill:#dcfce7,stroke:#16a34a,stroke-width:2.5px,color:#14532d;",
    ]
    if completed:
        decorations.append(f"class {','.join(completed)} completed;")
    if active:
        decorations.append(f"class {','.join(active)} active;")
    return source.rstrip() + "\n" + "\n".join(decorations) + "\n"


def completed_nodes_from_state(values: dict[str, Any]) -> set[str]:
    """Extract visited node names without exposing event metadata or user data."""
    return {
        str(event.get("node"))
        for event in values.get("events", [])
        if event.get("node")
    }
