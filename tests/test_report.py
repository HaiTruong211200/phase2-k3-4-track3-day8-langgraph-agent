from langgraph_agent_lab.metrics import MetricsReport, ScenarioMetric
from langgraph_agent_lab.report import render_report, write_report


def _metrics() -> MetricsReport:
    return MetricsReport(
        total_scenarios=1,
        success_rate=1.0,
        avg_nodes_visited=4.0,
        total_retries=1,
        total_interrupts=0,
        resume_success=True,
        scenario_metrics=[
            ScenarioMetric(
                scenario_id="S|01",
                success=True,
                expected_route="tool",
                actual_route="tool",
                nodes_visited=4,
                retry_count=1,
                errors=["transient\nerror"],
            )
        ],
    )


def test_render_report_contains_required_sections_and_metrics():
    report = render_report(_metrics())
    assert "## 2. Tổng hợp metrics" in report
    assert "## 3. Kiến trúc" in report
    assert "## 5. Kết quả scenario" in report
    assert "## 6. Phân tích failure mode" in report
    assert "## 9. Kế hoạch cải thiện" in report
    assert "100.00%" in report
    assert "### 3.1 Graph" in report
    assert "```mermaid\n---\nconfig:" in report
    assert "flowchart LR;" in report
    assert "evidence/ui_llm_judge_and_parrallel_tools.png" in report
    assert "evidence/trace_langfuse_llm_judge_parrallel_tools.png" in report
    assert "chưa đủ để kết luận hai tool có khoảng thời gian chạy chồng lên nhau" in report
    assert "S\\|01" in report
    assert "transient<br>error" in report


def test_write_report_creates_parent_directory(tmp_path):
    output = tmp_path / "reports" / "lab_report.md"
    write_report(_metrics(), output)
    assert output.exists()
    assert output.read_text(encoding="utf-8").startswith("# Báo cáo Day 08")
