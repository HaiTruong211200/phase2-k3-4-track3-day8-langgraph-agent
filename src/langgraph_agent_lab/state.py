"""State schema for the Day 08 LangGraph lab.

Students should extend the schema only when needed. Keep state lean and serializable.
"""

from __future__ import annotations

from enum import StrEnum
from operator import add
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field, field_validator


def merge_parallel_results(
    current: list[dict[str, Any]], update: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge fan-out results deterministically, independent of completion order."""
    indexed = {
        (str(item.get("tool_name", "")), int(item.get("attempt", 0))): item
        for item in [*current, *update]
    }
    return [indexed[key] for key in sorted(indexed)]


class Route(StrEnum):
    SIMPLE = "simple"
    TOOL = "tool"
    MISSING_INFO = "missing_info"
    RISKY = "risky"
    ERROR = "error"
    BLOCKED = "blocked"
    DEAD_LETTER = "dead_letter"
    DONE = "done"


class LabEvent(BaseModel):
    """Append-only audit event for grading and debugging."""

    node: str
    event_type: str
    message: str
    latency_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    approved: bool = False
    reviewer: str = "mock-reviewer"
    comment: str = ""


class AgentState(TypedDict, total=False):
    """LangGraph state.

    TODO(student): decide which fields should be append-only and which should be overwritten.
    The current annotations give a safe starting point for auditability.
    """

    thread_id: str
    scenario_id: str
    query: str
    route: str
    risk_level: str
    attempt: int
    max_attempts: int
    final_answer: str | None
    evaluation_result: str
    evaluation_reason: str | None
    evaluation_method: str | None
    pending_question: str | None
    proposed_action: str | None
    approval: dict[str, Any] | None
    security_blocked: bool
    security_reason: str | None
    fanout_tool_name: str | None
    parallel_tool_results: Annotated[list[dict[str, Any]], merge_parallel_results]
    messages: Annotated[list[str], add]
    tool_results: Annotated[list[str], add]
    errors: Annotated[list[str], add]
    events: Annotated[list[dict[str, Any]], add]


class Scenario(BaseModel):
    id: str
    query: str
    expected_route: Route
    requires_approval: bool = False
    should_retry: bool = False
    max_attempts: int = 3
    tags: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value


def initial_state(scenario: Scenario) -> AgentState:
    """Create a serializable initial state for one scenario."""
    return {
        "thread_id": f"thread-{scenario.id}",
        "scenario_id": scenario.id,
        "query": scenario.query,
        "route": "",
        "risk_level": "unknown",
        "attempt": 0,
        "max_attempts": scenario.max_attempts,
        "final_answer": None,
        "evaluation_result": "",
        "evaluation_reason": None,
        "evaluation_method": None,
        "pending_question": None,
        "proposed_action": None,
        "approval": None,
        "security_blocked": False,
        "security_reason": None,
        "fanout_tool_name": None,
        "parallel_tool_results": [],
        "messages": [],
        "tool_results": [],
        "errors": [],
        "events": [],
    }


def make_event(node: str, event_type: str, message: str, **metadata: Any) -> dict[str, Any]:
    """Create a normalized event payload."""
    event = LabEvent(node=node, event_type=event_type, message=message, metadata=metadata)
    return event.model_dump()
