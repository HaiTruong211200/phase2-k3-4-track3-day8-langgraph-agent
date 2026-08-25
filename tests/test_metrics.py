from langgraph_agent_lab.metrics import metric_from_state, summarize_metrics
from langgraph_agent_lab.state import make_event


def test_metric_from_state_success():
    state = {
        "scenario_id": "S",
        "route": "simple",
        "final_answer": "ok",
        "events": [make_event("intake", "completed", "ok"), make_event("answer", "completed", "ok")],
        "errors": [],
        "approval": None,
    }
    metric = metric_from_state(state, expected_route="simple", approval_required=False)
    assert metric.success is True
    assert metric.nodes_visited == 2


def test_metric_from_state_route_mismatch():
    state = {
        "scenario_id": "S",
        "route": "tool",
        "final_answer": "ok",
        "events": [],
        "errors": [],
        "approval": None,
    }
    metric = metric_from_state(state, expected_route="simple", approval_required=False)
    assert metric.success is False


def test_summarize_metrics():
    m1 = metric_from_state(
        {"scenario_id": "1", "route": "simple", "final_answer": "ok", "events": [], "errors": [], "approval": None},
        "simple",
        False,
    )
    m2 = metric_from_state(
        {"scenario_id": "2", "route": "tool", "final_answer": None, "events": [], "errors": [], "approval": None},
        "tool",
        False,
    )
    report = summarize_metrics([m1, m2])
    assert report.total_scenarios == 2
    assert 0 <= report.success_rate <= 1


def test_mock_approval_is_not_counted_as_real_interrupt():
    state = {
        "scenario_id": "risky",
        "route": "risky",
        "final_answer": "ok",
        "events": [
            make_event(
                "approval",
                "approved",
                "mock approval",
                interrupted=False,
            )
        ],
        "errors": [],
        "approval": {"approved": True},
    }
    metric = metric_from_state(state, "risky", True, latency_ms=25)
    assert metric.approval_observed is True
    assert metric.interrupt_count == 0
    assert metric.latency_ms == 25


def test_real_interrupt_uses_event_metadata():
    state = {
        "scenario_id": "risky",
        "route": "risky",
        "final_answer": "ok",
        "events": [
            make_event(
                "approval",
                "approved",
                "human approval",
                interrupted=True,
            )
        ],
        "errors": [],
        "approval": {"approved": True},
    }
    metric = metric_from_state(state, "risky", True)
    assert metric.interrupt_count == 1
