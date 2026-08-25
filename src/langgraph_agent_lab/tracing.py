"""Optional Langfuse tracing for LangChain and LangGraph runs."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv


def build_langfuse_handler() -> Any | None:
    """Create a callback handler when Langfuse credentials are configured."""
    load_dotenv(override=False)
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key and not secret_key:
        return None
    if not public_key or not secret_key:
        raise RuntimeError(
            "Langfuse tracing requires both LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"
        )

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError as exc:
        raise RuntimeError(
            "Langfuse credentials are configured, but its LangChain callback could not "
            "be imported. Install compatible versions with: "
            "pip install 'langchain>=1,<2' 'langfuse>=4,<5'"
        ) from exc

    return CallbackHandler()


def flush_langfuse(handler: Any | None) -> None:
    """Flush queued observations before a short-lived CLI process exits."""
    if handler is None:
        return
    from langfuse import get_client

    get_client().flush()


def tracing_config(
    *,
    thread_id: str,
    scenario_id: str,
    tags: list[str],
    handler: Any | None,
) -> dict[str, Any]:
    """Build LangGraph run config with optional Langfuse trace attributes."""
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if handler is None:
        return config

    trace_name = f"agent-lab-{scenario_id}"
    trace_tags = ["langgraph", "agent-lab", *tags]
    config.update(
        {
            "callbacks": [handler],
            "run_name": trace_name,
            "tags": trace_tags,
            "metadata": {
                "langfuse_trace_name": trace_name,
                "langfuse_session_id": thread_id,
                "langfuse_tags": trace_tags,
                "scenario_id": scenario_id,
                "framework": "langgraph",
            },
        }
    )
    return config
