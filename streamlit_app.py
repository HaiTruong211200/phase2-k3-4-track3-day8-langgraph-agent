"""Streamlit UI for running and reviewing the LangGraph lab workflow."""

from __future__ import annotations

import html
import os
from uuid import uuid4

import streamlit as st
from langgraph.types import Command

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Route, Scenario, initial_state
from langgraph_agent_lab.tracing import build_langfuse_handler, tracing_config
from langgraph_agent_lab.visualization import completed_nodes_from_state, execution_mermaid

st.set_page_config(page_title="LangGraph Review Console", page_icon="◎", layout="wide")
st.markdown(
    """
    <style>
    :root {
      --ink: #172033;
      --muted: #667085;
      --line: #e2e8f0;
      --surface: #ffffff;
      --brand: #2563eb;
    }
    html, body, [class*="st-"] { font-family: Inter, "Segoe UI", Arial, sans-serif; }
    .stApp { background: linear-gradient(180deg, #f8faff 0, #f4f7fb 320px); color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(248, 250, 255, .86); backdrop-filter: blur(10px); }
    [data-testid="stMainBlockContainer"] { max-width: 1320px; padding: 2.2rem 3rem 4rem; }
    [data-testid="stSidebar"] { background: #101828; border-right: 0; }
    [data-testid="stSidebar"] * { color: #f8fafc; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: #aeb8ca; }
    [data-testid="stSidebar"] hr { border-color: #344054; }
    [data-testid="stSidebar"] button { border-color: #475467; background: #1d2939; }
    p, label, .stMarkdown, [data-testid="stWidgetLabel"] { font-size: 1rem; line-height: 1.65; }
    h2 { font-size: 1.55rem !important; letter-spacing: -.02em; margin-top: 1.8rem !important; }
    h3 { font-size: 1.18rem !important; }
    .hero { padding: 1.3rem 0 1.15rem; border-bottom: 1px solid var(--line); margin-bottom: .7rem; }
    .hero-kicker { color: var(--brand); font-size: .78rem; font-weight: 750; letter-spacing: .13em;
      text-transform: uppercase; margin-bottom: .55rem; }
    .hero h1 { color: var(--ink); font-size: clamp(2.1rem, 4vw, 3.2rem); line-height: 1.08;
      letter-spacing: -.045em; margin: 0 0 .65rem; font-weight: 780; }
    .hero p { color: var(--muted); font-size: 1.08rem; max-width: 760px;
      margin: 0; line-height: 1.65; }
    .graph-legend { display: flex; gap: 1.25rem; align-items: center; color: var(--muted);
      font-size: .88rem; margin: -.2rem 0 .75rem; }
    .legend-item { display: inline-flex; gap: .45rem; align-items: center; }
    .legend-dot { width: .7rem; height: .7rem; border-radius: 99px; display: inline-block; }
    .dot-active { background: #2563eb; box-shadow: 0 0 0 3px #dbeafe; }
    .dot-done { background: #16a34a; box-shadow: 0 0 0 3px #dcfce7; }
    .status-card { background: var(--surface); border: 1px solid #bfdbfe; border-radius: 18px;
      padding: 1.2rem 1.35rem; margin: .8rem 0 1.2rem; box-shadow: 0 12px 32px #1d4ed80d; }
    [data-testid="stForm"], [data-testid="stMetric"], [data-testid="stDataFrame"] {
      background: var(--surface); border: 1px solid var(--line); border-radius: 16px;
      box-shadow: 0 8px 24px #18243b08;
    }
    [data-testid="stForm"] { padding: 1.25rem 1.35rem .55rem; }
    [data-testid="stMetric"] { padding: 1rem 1.1rem; }
    [data-testid="stMetricLabel"] p { color: var(--muted); font-size: .85rem; font-weight: 650; }
    [data-testid="stMetricValue"] { font-size: 1.45rem; color: var(--ink); }
    textarea { font-size: 1rem !important; line-height: 1.55 !important;
      border-radius: 12px !important; }
    .stButton button, .stFormSubmitButton button { min-height: 2.8rem; border-radius: 11px;
      font-size: .96rem; font-weight: 680; }
    iframe { background: white; border: 1px solid var(--line) !important; border-radius: 18px;
      box-shadow: 0 10px 30px #18243b0a; }
    [data-testid="stAlert"] { border-radius: 14px; }
    @media (max-width: 800px) {
      [data-testid="stMainBlockContainer"] { padding: 1.35rem 1rem 3rem; }
      .hero h1 { font-size: 2.15rem; }
      .hero p { font-size: 1rem; }
      .graph-legend { flex-wrap: wrap; gap: .7rem 1.1rem; }
    }
    </style>
    <div class="hero">
      <div class="hero-kicker">Agent operations workspace</div>
      <h1>LangGraph Review Console</h1>
      <p>Chạy ticket, kiểm tra route và duyệt hành động rủi ro trước khi gọi tool.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_graph():
    checkpointer = build_checkpointer("sqlite", "outputs/ui_checkpoints.sqlite")
    return build_graph(checkpointer=checkpointer)


@st.cache_resource
def get_trace_handler():
    return build_langfuse_handler()


def current_values() -> dict:
    config = st.session_state.get("run_config")
    if not config:
        return {}
    return dict(get_graph().get_state(config).values)


def render_graph(placeholder, *, active_nodes=(), values=None) -> None:
    """Render the actual compiled graph with live node highlighting."""
    completed = completed_nodes_from_state(values or {})
    source = execution_mermaid(
        get_graph(), active_nodes=active_nodes, completed_nodes=completed
    )
    escaped_source = html.escape(source)
    component = f"""
    <style>
      body {{ margin: 0; background: #fbfcff; overflow: hidden; }}
      .graph-shell {{ min-height: 610px; position: relative; padding: 54px 28px 28px;
        box-sizing: border-box; font-family: Inter, "Segoe UI", system-ui, sans-serif;
        color: #172033; }}
      .viewport {{ width: 100%; height: 530px; overflow: auto; display: block;
        scrollbar-color: #cbd5e1 transparent; }}
      .mermaid {{ width: max-content; transform-origin: top left; transition: transform .18s ease;
        min-width: max-content; padding: 28px 56px 48px; }}
      .mermaid svg {{ height: auto; filter: drop-shadow(0 10px 18px #1720330a); }}
      .node rect, .node polygon, .node path {{ rx: 12px; ry: 12px; }}
      .nodeLabel {{ font-size: 15px !important; font-weight: 680; letter-spacing: .01em; }}
      .edgeLabel {{ background: #fbfcff !important; color: #64748b !important;
        font-size: 12px !important; border-radius: 6px; }}
      .flowchart-link {{ stroke: #94a3b8 !important; stroke-width: 1.6px !important; }}
      marker path {{ fill: #64748b !important; stroke: #64748b !important; }}
      .toolbar {{ position: absolute; z-index: 2; top: 14px; right: 16px; display: flex;
        align-items: center; gap: 5px; padding: 5px; border: 1px solid #e2e8f0;
        border-radius: 11px; background: rgba(255,255,255,.92); box-shadow: 0 6px 20px #17203312; }}
      .toolbar button {{ width: 34px; height: 30px; border: 0; border-radius: 7px;
        background: transparent; color: #475569; font: 700 15px Inter, sans-serif;
        cursor: pointer; }}
      .toolbar button:hover {{ background: #eff6ff; color: #2563eb; }}
      .zoom-label {{ min-width: 42px; text-align: center; color: #64748b; font-size: 12px; }}
    </style>
    <div class="graph-shell">
      <div class="toolbar" aria-label="Điều khiển thu phóng graph">
        <button type="button" onclick="changeZoom(-0.1)" title="Thu nhỏ">−</button>
        <span class="zoom-label" id="zoomLabel">100%</span>
        <button type="button" onclick="changeZoom(0.1)" title="Phóng to">+</button>
        <button type="button" onclick="resetZoom()" title="Về kích thước ban đầu">↺</button>
      </div>
      <div class="viewport" id="viewport">
        <div class="mermaid" id="diagram">{escaped_source}</div>
      </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <script>
      let zoom = 1;
      const diagram = document.getElementById("diagram");
      const zoomLabel = document.getElementById("zoomLabel");
      function applyZoom() {{
        diagram.style.transform = `scale(${{zoom}})`;
        zoomLabel.textContent = `${{Math.round(zoom * 100)}}%`;
      }}
      function changeZoom(delta) {{
        zoom = Math.min(1.6, Math.max(0.55, zoom + delta));
        applyZoom();
      }}
      function resetZoom() {{
        zoom = 1;
        applyZoom();
        document.getElementById("viewport").scrollTo(0, 0);
      }}
      mermaid.initialize({{
        startOnLoad: true,
        theme: "base",
        securityLevel: "strict",
        flowchart: {{ curve: "basis", htmlLabels: true, nodeSpacing: 38, rankSpacing: 72,
          padding: 16, useMaxWidth: false }},
        themeVariables: {{
          fontFamily: "Inter, Segoe UI, system-ui",
          fontSize: "15px",
          primaryColor: "#f8fafc",
          lineColor: "#94a3b8",
          clusterBkg: "#f8fafc",
          edgeLabelBackground: "#fbfcff"
        }}
      }});
    </script>
    """
    placeholder.empty()
    with placeholder.container():
        # The HTML is generated only from the compiled graph and fixed styles.
        # No user input is interpolated into this executable iframe.
        st.iframe(component, height=650)
        if active_nodes:
            st.caption("Node hiện tại/tiếp theo: " + ", ".join(active_nodes))


def _payload_from_update(update: object) -> dict | None:
    interrupts = update if isinstance(update, (list, tuple)) else [update]
    if not interrupts:
        return None
    value = getattr(interrupts[0], "value", interrupts[0])
    return value if isinstance(value, dict) else {"question": str(value)}


def stream_with_progress(graph_input) -> tuple[dict, dict | None]:
    """Run or resume the graph and refresh Mermaid after every streamed step."""
    config = st.session_state["run_config"]
    payload = None
    render_graph(graph_placeholder, active_nodes=("intake",), values=current_values())
    for update in get_graph().stream(graph_input, config=config, stream_mode="updates"):
        if "__interrupt__" in update:
            payload = _payload_from_update(update["__interrupt__"])
        snapshot = get_graph().get_state(config)
        active = tuple(snapshot.next)
        if not active:
            active = tuple(key for key in update if key != "__interrupt__")
        render_graph(graph_placeholder, active_nodes=active, values=dict(snapshot.values))
    snapshot = get_graph().get_state(config)
    values = dict(snapshot.values)
    if payload is None:
        for task in snapshot.tasks:
            if task.interrupts:
                payload = _payload_from_update(task.interrupts)
                break
    render_graph(
        graph_placeholder,
        active_nodes=tuple(snapshot.next),
        values=values,
    )
    return values, payload


with st.sidebar:
    st.subheader("Tùy chọn extension")
    fanout = st.toggle("Parallel fan-out", value=True)
    llm_judge = st.toggle("LLM-as-judge", value=True)
    st.caption("Real HITL luôn bật trong UI; CLI/CI vẫn dùng mock mặc định.")
    st.divider()
    if st.button("Ticket mới", use_container_width=True):
        for key in ("run_config", "result", "interrupt", "query"):
            st.session_state.pop(key, None)
        st.rerun()

os.environ["LANGGRAPH_INTERRUPT"] = "true"
os.environ["LANGGRAPH_FANOUT"] = "true" if fanout else "false"
os.environ["LLM_JUDGE_ENABLED"] = "true" if llm_judge else "false"

st.subheader("Graph execution")
st.markdown(
    """
    <div class="graph-legend">
      <span class="legend-item"><span class="legend-dot dot-active"></span>
        Đang chạy / tiếp theo</span>
      <span class="legend-item"><span class="legend-dot dot-done"></span>Đã hoàn thành</span>
    </div>
    """,
    unsafe_allow_html=True,
)
graph_placeholder = st.empty()
render_graph(
    graph_placeholder,
    active_nodes=tuple(get_graph().get_state(st.session_state["run_config"]).next)
    if st.session_state.get("run_config")
    else (),
    values=current_values(),
)

with st.form("ticket_form"):
    query = st.text_area(
        "Nội dung ticket",
        value=st.session_state.get("query", ""),
        placeholder="Ví dụ: Refund this customer and send confirmation email",
        height=120,
        disabled=bool(st.session_state.get("interrupt")),
    )
    submitted = st.form_submit_button(
        "Chạy workflow", type="primary", disabled=bool(st.session_state.get("interrupt"))
    )

if submitted:
    if not query.strip():
        st.warning("Vui lòng nhập nội dung ticket.")
    else:
        scenario_id = f"ui-{uuid4().hex[:10]}"
        scenario = Scenario(
            id=scenario_id,
            query=query,
            expected_route=Route.SIMPLE,
            max_attempts=3,
        )
        state = initial_state(scenario)
        handler = get_trace_handler()
        config = tracing_config(
            thread_id=state["thread_id"],
            scenario_id=scenario_id,
            tags=["streamlit", "hitl"],
            handler=handler,
        )
        st.session_state["run_config"] = config
        with st.spinner("Đang chạy graph..."):
            result, payload = stream_with_progress(state)
        st.session_state["query"] = query
        st.session_state["result"] = result
        st.session_state["interrupt"] = payload
        st.rerun()

payload = st.session_state.get("interrupt")
if payload:
    values = current_values()
    st.markdown('<div class="status-card">', unsafe_allow_html=True)
    st.subheader("Đang chờ phê duyệt")
    st.write(payload.get("question", "Bạn có duyệt hành động này không?"))
    st.code(payload.get("proposed_action") or values.get("proposed_action", ""), language=None)
    approve_col, reject_col = st.columns(2)
    if approve_col.button("Duyệt và tiếp tục", type="primary", use_container_width=True):
        decision = {"approved": True, "reviewer": "streamlit-reviewer", "comment": "UI approval"}
        with st.spinner("Đang resume workflow..."):
            result, payload = stream_with_progress(Command(resume=decision))
        st.session_state["result"] = result
        st.session_state["interrupt"] = payload
        st.rerun()
    if reject_col.button("Từ chối", use_container_width=True):
        decision = {"approved": False, "reviewer": "streamlit-reviewer", "comment": "UI rejection"}
        with st.spinner("Đang resume workflow..."):
            result, payload = stream_with_progress(Command(resume=decision))
        st.session_state["result"] = result
        st.session_state["interrupt"] = payload
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

values = current_values()
if values:
    route_col, risk_col, attempt_col, judge_col = st.columns(4)
    route_col.metric("Route", values.get("route") or "-")
    risk_col.metric("Risk", values.get("risk_level") or "-")
    attempt_col.metric("Attempt", values.get("attempt", 0))
    judge_col.metric("Evaluator", values.get("evaluation_method") or "-")

    if values.get("final_answer"):
        st.subheader("Kết quả")
        st.success(values["final_answer"])

    if values.get("parallel_tool_results"):
        st.subheader("Kết quả fan-out")
        st.dataframe(values["parallel_tool_results"], use_container_width=True, hide_index=True)

    st.subheader("Event trail")
    event_rows = [
        {
            "node": event.get("node"),
            "type": event.get("event_type"),
            "message": event.get("message"),
        }
        for event in values.get("events", [])
    ]
    st.dataframe(event_rows, use_container_width=True, hide_index=True)
