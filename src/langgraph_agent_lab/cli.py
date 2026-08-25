"""CLI for the lab."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Annotated
from uuid import uuid4

import typer
import yaml

from .graph import build_graph
from .metrics import MetricsReport, metric_from_state, summarize_metrics, write_metrics
from .persistence import build_checkpointer
from .report import write_report
from .scenarios import load_scenarios
from .state import initial_state
from .tracing import build_langfuse_handler, flush_langfuse, tracing_config

app = typer.Typer(no_args_is_help=True)


@app.command("run-scenarios")
def run_scenarios(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run all grading scenarios and write metrics JSON."""
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    scenarios = load_scenarios(cfg["scenarios_path"])
    checkpointer = build_checkpointer(cfg.get("checkpointer", "memory"), cfg.get("database_url"))
    graph = build_graph(checkpointer=checkpointer)
    langfuse_handler = build_langfuse_handler()
    if langfuse_handler is not None:
        typer.echo("Langfuse tracing enabled")
    metrics = []
    run_id = uuid4().hex
    recovery_config = None
    recovery_scenario_id = None
    try:
        for scenario in scenarios:
            state = initial_state(scenario)
            state["thread_id"] = f"{state['thread_id']}-{run_id}"
            run_config = tracing_config(
                thread_id=state["thread_id"],
                scenario_id=scenario.id,
                tags=scenario.tags,
                handler=langfuse_handler,
            )
            started_at = perf_counter()
            final_state = graph.invoke(state, config=run_config)
            latency_ms = max(1, round((perf_counter() - started_at) * 1_000))
            metrics.append(
                metric_from_state(
                    final_state,
                    scenario.expected_route.value,
                    scenario.requires_approval,
                    latency_ms=latency_ms,
                )
            )
            if recovery_config is None:
                recovery_config = {"configurable": {"thread_id": state["thread_id"]}}
                recovery_scenario_id = scenario.id
    finally:
        flush_langfuse(langfuse_handler)
    report = summarize_metrics(metrics)
    if cfg.get("checkpointer") == "sqlite" and recovery_config is not None:
        recovery_checkpointer = build_checkpointer("sqlite", cfg.get("database_url"))
        try:
            recovery_graph = build_graph(checkpointer=recovery_checkpointer)
            recovered = recovery_graph.get_state(recovery_config)
            history = list(recovery_graph.get_state_history(recovery_config))
            report.resume_success = (
                recovered.values.get("scenario_id") == recovery_scenario_id
                and len(history) >= 2
            )
        finally:
            recovery_checkpointer.conn.close()
    write_metrics(report, output)
    if cfg.get("report_path"):
        write_report(report, cfg["report_path"])
    typer.echo(f"Wrote metrics to {output}")


@app.command("validate-metrics")
def validate_metrics(metrics: Annotated[Path, typer.Option("--metrics")]) -> None:
    """Validate metrics JSON schema for grading."""
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    report = MetricsReport.model_validate(payload)
    if report.total_scenarios < 6:
        raise typer.BadParameter("Expected at least 6 scenarios")
    typer.echo(f"Metrics valid. success_rate={report.success_rate:.2%}")


if __name__ == "__main__":
    app()
