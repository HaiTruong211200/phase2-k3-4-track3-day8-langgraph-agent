# Day 08 Lab Report

## 1. Team / student

- Name: Hai
- Repo: `HaiTruong211200/phase2-k3-4-track3-day8-langgraph-agent`
- Commit reviewed: `6d8252d` plus the current working-tree implementation
- Generated: 2026-08-25

## 2. Metrics summary

| Metric | Value |
|---|---:|
| Total scenarios | 7 |
| Successful scenarios | 7 |
| Success rate | 100.00% |
| Average nodes visited | 6.43 |
| Total retries | 3 |
| Total real HITL interrupts | 0 |
| Persistence resume demonstrated | Yes |

## 3. Architecture

The graph registers eleven nodes with narrow responsibilities: `intake`, `classify`,
`tool`, `evaluate`, `answer`, `clarify`, `risky_action`, `approval`, `retry`,
`dead_letter`, and `finalize`. `START -> intake` is fixed. A guardrail decision after
`intake` either stops at `finalize` or continues to `classify`; classification then selects
the direct-answer, tool, clarification, risky-action, or initial-error branch.

The tool path is `tool -> evaluate`; evaluation conditionally selects `answer` or `retry`.
The retry router selects `tool` only while `attempt < max_attempts`, otherwise it selects
`dead_letter`. The risky path is `risky_action -> approval`, after which approval selects
`tool` and rejection selects `clarify`. `answer`, `clarify`, and `dead_letter` all have a
fixed edge to `finalize`, followed by `END`. Thus every cycle has a monotonic attempt bound
and every non-cyclic branch has an explicit terminal edge.

SQLite checkpointing uses a unique `thread_id` per scenario and batch run. This avoids
merging append-only audit history from repeated benchmark runs while still allowing every
node transition to be recovered and inspected within that run.

## 4. State schema

| Field | Update behavior | Purpose |
|---|---|---|
| `query` | overwrite | Normalized current request |
| `route` | overwrite | Current classification or blocked route |
| `attempt` | overwrite | Current bounded-retry counter |
| `evaluation_result` | overwrite | Latest tool evaluation gate |
| `pending_question` | overwrite | Current clarification request |
| `proposed_action` | overwrite | Current action awaiting approval |
| `approval` | overwrite | Latest human/mock approval decision |
| `security_blocked` | overwrite | Intake guardrail decision |
| `messages` | append | Conversation/audit messages |
| `tool_results` | append | Complete tool-attempt history |
| `errors` | append | Failure and retry history |
| `events` | append | Normalized node-level audit trail |

## 5. Scenario results

| Scenario | Expected route | Actual route | Success | Nodes | Retries | HITL interrupts | Approval observed | Latency (ms) | Errors |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| S01_simple | simple | simple | Yes | 4 | 0 | 0 | No | 6620 | - |
| S02_tool | tool | tool | Yes | 6 | 0 | 0 | No | 4312 | - |
| S03_missing | missing_info | missing_info | Yes | 4 | 0 | 0 | No | 1718 | - |
| S04_risky | risky | risky | Yes | 8 | 0 | 0 | Yes | 4204 | - |
| S05_error | error | error | Yes | 10 | 2 | 0 | No | 4045 | Transient failure recorded; retry attempt 1; Transient failure recorded; retry attempt 2 |
| S06_delete | risky | risky | Yes | 8 | 0 | 0 | Yes | 4310 | - |
| S07_dead_letter | error | error | Yes | 5 | 1 | 0 | No | 1817 | Transient failure recorded; retry attempt 1; Maximum retry count reached after 1 attempt(s) |

## 6. Failure analysis

### Retry and tool failure

- **Origin:** `tool_node` deliberately returns a result containing `ERROR` for a transient
  error route while `attempt < 2`.
- **Detection evidence:** `tool_results[-1]` preserves the failing output;
  `evaluate_node` overwrites `evaluation_result` with `needs_retry`; `events` records
  `tool:failed`, `evaluate:completed`, and `retry:scheduled`; `errors` records the attempt.
- **Containment and next edge:** `route_after_evaluate` selects `retry`. That node increments
  `attempt`, and `route_after_retry` selects either another `tool` call or `dead_letter`.
- **Termination guarantee:** `attempt` increases monotonically and the retry edge is allowed
  only while `attempt < max_attempts`. At the bound, `dead_letter` sets `final_answer` and
  follows the fixed `dead_letter -> finalize -> END` edges.
- **Observed evidence:** retry counts in the final metrics are `S05_error`=2, `S07_dead_letter`=1. A scenario
  can be successful because it followed its expected error/dead-letter route, not because
  the underlying tool operation succeeded.
- **Residual limitation:** the tool and evaluator are deterministic mocks. They do not yet
  distinguish retryable transport errors from permanent business errors, apply backoff, or
  enforce idempotency for a real side effect.

### Risky action rejected before tool execution

- **Origin:** `classify_node` assigns route `risky` to refunds, deletions, or other
  state-changing requests; `risky_action_node` writes the requested side effect to
  `proposed_action` without executing it.
- **Detection evidence:** `risk_level=high`, the `risky_action:prepared` event, and the
  overwrite-only `approval.approved` decision provide the routing signal and audit record.
- **Containment and next edge:** `route_after_approval` sends `approved=True` to `tool`, but
  sends rejection or a missing decision to `clarify`; therefore rejection cannot reach the
  side-effecting node.
- **Termination guarantee:** the rejected branch has fixed edges
  `clarify -> finalize -> END`. The approved branch rejoins the already bounded
  `tool -> evaluate` path.
- **Observed evidence:** approval-required scenarios report `S04_risky`=observed, `S06_delete`=observed. The final
  scenario batch used mock approvals and recorded 0 real HITL
  interrupts, so it demonstrates the approval gate but not an interactive rejection.
- **Residual limitation:** mock approval defaults to `True`. Rejection routing is covered by
  tests, but production requires authenticated reviewers, durable pause/resume, authorization
  policy, expiry, and an idempotent tool boundary.

### Prompt injection

The intake guardrail normalizes Unicode, removes control characters, limits input length,
and blocks high-confidence instruction-override, prompt-exfiltration, role-injection, and
safety-bypass patterns before classification. LLM calls additionally separate trusted
system instructions from untrusted user data.

Scenario-level outcome: No scenario-level failures were observed in this run.

## 7. Persistence / recovery evidence

The configured `SqliteSaver` uses WAL mode and `check_same_thread=False`. Each batch adds a
random run suffix to `thread_id`, preventing old append-only events from contaminating new
metrics. After the scenario loop, the CLI constructs a **new saver and graph** against the
same database, retrieves the first scenario with the same `thread_id`, and requires both a
matching `scenario_id` and at least two history snapshots before setting
`resume_success=true`. The final metrics record this proof as **successful**.

The independent persistence test is stricter about connection lifecycle: it invokes a
small graph, closes the original SQLite connection, reopens the database through a second
saver, verifies the recovered value, and confirms `get_state_history()` contains multiple
snapshots. This proves persisted recovery without exposing raw state, credentials, or
database contents. It does not simulate a process kill during an in-flight external tool.

## 8. Extension work

Completed with executable evidence:

- SQLite persistence with WAL mode, reopen verification, and state-history tests.
- Prompt-injection guardrail before the first LLM node, including a test proving blocked
  input reaches only `intake` and `finalize`.
- Optional Langfuse callback wiring with scenario trace names, thread sessions, tags, and
  metadata; configuration behavior is covered by tests.

Implemented but not demonstrated by the final scenario metrics:

- Real interrupt/resume approval behind `LANGGRAPH_INTERRUPT=true`; the batch run uses mock
  approval so CI does not pause.
- Mermaid rendering is available through `graph.get_graph().draw_mermaid()`, but no diagram
  artifact is claimed as submission evidence.

## 9. Improvement plan

The first production priority is the side-effect boundary: replace the mock tool and
auto-approval with authenticated, idempotent integrations and a durable reviewer interface.
That closes the largest gap between the demonstrated core graph and safe production use.
Next, classify errors as retryable/permanent, add exponential backoff, and test process-kill
recovery during a paused approval. Scenario latency is now measured end-to-end, but per-node
latency, token usage, tool latency, and trace-delivery success remain future instrumentation;
the report therefore does not infer them from the current metrics.
