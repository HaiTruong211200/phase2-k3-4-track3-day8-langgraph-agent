import pytest

import langgraph_agent_lab.tracing as tracing


def test_langfuse_is_optional(monkeypatch):
    monkeypatch.setattr(tracing, "load_dotenv", lambda **kwargs: None)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracing.build_langfuse_handler() is None


def test_langfuse_rejects_partial_credentials(monkeypatch):
    monkeypatch.setattr(tracing, "load_dotenv", lambda **kwargs: None)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="requires both"):
        tracing.build_langfuse_handler()


def test_tracing_config_without_handler_only_has_thread_id():
    config = tracing.tracing_config(
        thread_id="thread-1",
        scenario_id="S01",
        tags=["simple"],
        handler=None,
    )
    assert config == {"configurable": {"thread_id": "thread-1"}}


def test_tracing_config_adds_langfuse_metadata():
    handler = object()
    config = tracing.tracing_config(
        thread_id="thread-1",
        scenario_id="S01",
        tags=["simple"],
        handler=handler,
    )
    assert config["callbacks"] == [handler]
    assert config["run_name"] == "agent-lab-S01"
    assert config["metadata"]["langfuse_session_id"] == "thread-1"
    assert config["metadata"]["langfuse_trace_name"] == "agent-lab-S01"
    assert config["metadata"]["langfuse_tags"] == ["langgraph", "agent-lab", "simple"]
