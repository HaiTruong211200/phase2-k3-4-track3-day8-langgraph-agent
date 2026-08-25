"""Routing functions for conditional edges.

Each function takes AgentState and returns a string — the name of the next node.
These strings MUST match node names registered in graph.py.
"""

from __future__ import annotations

import os

from .state import AgentState


def _tool_target() -> str:
    """Select optional fan-out without changing the default core path."""
    return "tool_dispatch" if os.getenv("LANGGRAPH_FANOUT", "").lower() == "true" else "tool"


def route_after_intake(state: AgentState) -> str:
    """Stop unsafe input before it is sent to an LLM."""
    return "finalize" if state.get("security_blocked", False) else "classify"


def route_after_classify(state: AgentState) -> str:
    """Map classified route to the next graph node.

    Mapping:
    - "simple"       → "answer"
    - "tool"         → "tool"
    - "missing_info" → "clarify"
    - "risky"        → "risky_action"
    - "error"        → "retry"
    - unknown/default → "answer"

    Hint: use a dict mapping for clean implementation.
    """
    route_map = {
        "simple": "answer",
        "tool": _tool_target(),
        "missing_info": "clarify",
        "risky": "risky_action",
        "error": "retry",
    }
    return route_map.get(state.get("route", ""), "answer")


def route_after_evaluate(state: AgentState) -> str:
    """Decide if tool result is satisfactory or needs retry.

    This is the 'done?' check that creates the retry loop —
    a key LangGraph advantage over linear LCEL chains.

    - If evaluation_result == "needs_retry" → "retry"
    - Otherwise → "answer"
    """
    if state.get("evaluation_result") == "needs_retry":
        return "retry"
    return "answer"


def route_after_retry(state: AgentState) -> str:
    """Decide whether to retry the tool or give up.

    MUST be bounded — unbounded retry loops will fail grading.

    - If attempt < max_attempts → "tool" (try again)
    - If attempt >= max_attempts → "dead_letter" (give up, escalate)
    """
    attempt = state.get("attempt", 0)
    max_attempts = state.get("max_attempts", 3)
    return "tool" if attempt < max_attempts else "dead_letter"


def route_after_approval(state: AgentState) -> str:
    """Route based on human approval decision.

    - If approved → "tool" (proceed with risky action)
    - If rejected → "clarify" (ask user for alternative)
    """
    approval = state.get("approval") or {}
    return _tool_target() if approval.get("approved", False) else "clarify"


def dispatch_parallel_tools(state: AgentState):
    """Fan out two independent mock tools using LangGraph Send()."""
    from langgraph.types import Send

    shared = {
        "query": state.get("query", ""),
        "route": state.get("route", ""),
        "attempt": state.get("attempt", 0),
        "proposed_action": state.get("proposed_action"),
    }
    return [
        Send("parallel_tool", {**shared, "fanout_tool_name": tool_name})
        for tool_name in ("customer_context", "policy_check")
    ]
