from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langgraph.types import Command

import langgraph_agent_lab.nodes as nodes
from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import merge_parallel_results
from langgraph_agent_lab.visualization import completed_nodes_from_state, execution_mermaid


class FakeStructuredModel:
    def __init__(self, schema, route: str = "tool", fail: bool = False):
        self.schema = schema
        self.route = route
        self.fail = fail

    def invoke(self, _messages):
        if self.fail:
            raise TimeoutError("judge timeout")
        if self.schema is nodes.IntentClassification:
            return self.schema(route=self.route, reason="test classification")
        return self.schema(verdict="success", reason="usable result", confidence=0.9)


class FakeLLM:
    def __init__(self, route: str = "tool", fail_judge: bool = False):
        self.route = route
        self.fail_judge = fail_judge

    def with_structured_output(self, schema):
        return FakeStructuredModel(
            schema,
            route=self.route,
            fail=self.fail_judge and schema is nodes.EvaluationVerdict,
        )

    def invoke(self, _messages):
        return SimpleNamespace(content="Câu trả lời kiểm thử")


def test_llm_judge_returns_structured_verdict(monkeypatch):
    monkeypatch.setenv("LLM_JUDGE_ENABLED", "true")
    monkeypatch.setattr(nodes, "get_llm", lambda **kwargs: FakeLLM())
    result = nodes.evaluate_node({"query": "lookup", "tool_results": ["usable"]})
    assert result["evaluation_result"] == "success"
    assert result["evaluation_method"] == "llm_judge"
    assert result["evaluation_reason"] == "usable result"


def test_llm_judge_timeout_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setenv("LLM_JUDGE_ENABLED", "true")
    monkeypatch.setattr(nodes, "get_llm", lambda **kwargs: FakeLLM(fail_judge=True))
    result = nodes.evaluate_node({"query": "lookup", "tool_results": ["ERROR timeout"]})
    assert result["evaluation_result"] == "needs_retry"
    assert result["evaluation_method"] == "heuristic_fallback"
    assert result["events"][0]["metadata"]["judge_error"] == "TimeoutError"


def test_llm_judge_cost_guard_skips_model(monkeypatch):
    monkeypatch.setenv("LLM_JUDGE_ENABLED", "true")
    monkeypatch.setenv("LLM_JUDGE_MAX_ATTEMPT", "1")

    def unexpected_call(**_kwargs):
        raise AssertionError("LLM must not be called after the cost guard")

    monkeypatch.setattr(nodes, "get_llm", unexpected_call)
    result = nodes.evaluate_node(
        {"attempt": 2, "query": "lookup", "tool_results": ["usable"]}
    )
    assert result["evaluation_result"] == "success"
    assert result["evaluation_method"] == "cost_guard_fallback"


def test_parallel_reducer_is_deterministic():
    left = [{"tool_name": "policy_check", "attempt": 0, "output": "B"}]
    right = [{"tool_name": "customer_context", "attempt": 0, "output": "A"}]
    assert merge_parallel_results(left, right) == merge_parallel_results(right, left)
    assert [item["tool_name"] for item in merge_parallel_results(left, right)] == [
        "customer_context",
        "policy_check",
    ]


def test_send_fanout_runs_and_merges_in_stable_order(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_FANOUT", "true")
    monkeypatch.delenv("LLM_JUDGE_ENABLED", raising=False)
    monkeypatch.setattr(nodes, "get_llm", lambda **kwargs: FakeLLM(route="tool"))
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    config = {"configurable": {"thread_id": "fanout-test"}}
    result = graph.invoke(
        {
            "thread_id": "fanout-test",
            "scenario_id": "fanout",
            "query": "lookup order 123",
            "attempt": 0,
            "max_attempts": 3,
            "messages": [],
            "tool_results": [],
            "parallel_tool_results": [],
            "errors": [],
            "events": [],
        },
        config=config,
    )
    assert [item["tool_name"] for item in result["parallel_tool_results"]] == [
        "customer_context",
        "policy_check",
    ]
    visited = [event["node"] for event in result["events"]]
    assert visited.count("parallel_tool") == 2
    assert "merge_tools" in visited


def test_real_hitl_rejection_resumes_same_thread_without_tool(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_INTERRUPT", "true")
    monkeypatch.delenv("LANGGRAPH_FANOUT", raising=False)
    monkeypatch.setattr(nodes, "get_llm", lambda **kwargs: FakeLLM(route="risky"))
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    config = {"configurable": {"thread_id": "hitl-test"}}
    initial = graph.invoke(
        {
            "thread_id": "hitl-test",
            "scenario_id": "hitl",
            "query": "refund customer",
            "attempt": 0,
            "max_attempts": 3,
            "messages": [],
            "tool_results": [],
            "parallel_tool_results": [],
            "errors": [],
            "events": [],
        },
        config=config,
    )
    assert initial.get("__interrupt__")

    resumed = graph.invoke(
        Command(resume={"approved": False, "reviewer": "tester"}),
        config=config,
    )
    assert resumed["approval"]["approved"] is False
    visited = [event["node"] for event in resumed["events"]]
    assert "clarify" in visited
    assert "tool" not in visited
    assert visited[-1] == "finalize"


def test_mermaid_is_exported_from_compiled_graph_with_execution_classes():
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    mermaid = execution_mermaid(
        graph,
        active_nodes=["evaluate"],
        completed_nodes=["intake", "classify", "tool", "evaluate"],
    )
    assert "flowchart LR" in mermaid
    assert "class classify,intake,tool completed;" in mermaid
    assert "class evaluate active;" in mermaid
    assert "classDef active" in mermaid


def test_completed_nodes_uses_only_event_node_names():
    values = {
        "query": "secret user content",
        "events": [
            {"node": "intake", "message": "raw private text"},
            {"node": "classify", "message": "another private value"},
        ],
    }
    assert completed_nodes_from_state(values) == {"intake", "classify"}


def test_submitted_mermaid_artifact_matches_the_compiled_graph():
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    artifact = Path("reports/actual_graph.mmd").read_text(encoding="utf-8")
    assert artifact == execution_mermaid(graph)
