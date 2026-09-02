# Execution Contract — `loopy-agent` v0.8.0 → v1.0.0 Roadmap

> **Purpose**: Deterministic, machine-verifiable execution harness for an AI agent (or human) implementing the **Tier 1 (v0.8.0) → Tier 2 (v0.9.0) → Tier 3 (v1.0.0)** roadmap from `docs/research/competitive-analysis-2026.md`.
> **Source**: `dev-notes/AUDIT.md` (gap assessment), `dev-notes/DISCOVERY.md` (codebase state).
> **Mode**: **B — Existing Application Realignment** (the codebase is live; we are hardening it).
> **Pattern**: **Strangler Fig** — new production-grade code lands alongside legacy code; legacy code is deleted only when characterization tests + new tests prove parity.
> **Zero-Tolerance Invariant**: zero regressions in 581-test suite, zero ruff errors, zero strict-warnings violations, coverage ≥90% at every milestone, every milestone verified by an executable command that exits 0.

---

## Meta Information

- **Current version**: 0.7.10 (latest released tag)
- **Target versions**: 0.8.0 → 0.9.0 → 1.0.0
- **Verification engine**: `pytest --no-header` (exit code 0 = pass)
- **Source audit**: `dev-notes/AUDIT.md`
- **Strategic doc**: `docs/research/competitive-analysis-2026.md`
- **Repository**: `github.com/Dream-Pixels-Forge/loopy-agent`
- **Release pipeline**: GitHub Trusted Publishing via OIDC (already in place since v0.7.0)

---

## Pre-Flight Invariant — Environment Baseline

Before executing Phase 1 of any release bucket, verify:

- [ ] **P0.1 — Working tree clean + on master + synced with origin**
  - `git status --short` produces no output
  - `git log -n 1` matches `origin/master`
- [ ] **P0.2 — Test suite green**
  - `python -m pytest --no-header` exits 0 with **581 passed**
- [ ] **P0.3 — Lint + format clean**
  - `python -m ruff check loopy/ tests/` exits 0 with `All checks passed!`
  - `python -m ruff format --check loopy/ tests/` exits 0
- [ ] **P0.4 — Strict-warnings clean** (any deprecation becomes a test failure)
  - `python -m pytest --no-header` produces zero `RuntimeWarning: coroutine ... was never awaited` and zero `PytestUnraisableExceptionWarning`
- [ ] **P0.5 — Coverage ≥90%**
  - `python -m pytest --cov=loopy --cov-fail-under=90` exits 0

**If any of P0.1–P0.5 fails, fix it before starting Phase 1.** No "I'll fix it while coding." Do not weaken assertions.

---

# Tier 1 — v0.8.0 "Agent Control Plane"

> **Theme**: ship the missing 2026 primitives (graph control flow, HITL, OTel auto-instrumentation) so loopy is production-deployable as a runtime, not just a library.
> **Source**: Tier 1 of `docs/research/competitive-analysis-2026.md` §4.
> **Goal**: close the 4 HIGH-severity gaps AUD-S01, AUD-O01, AUD-D01-R04.

## Phase T1.0 — Characterization Baseline (Golden Master)

Before adding new code, capture the **existing behavior** of `AgentLoop.run()`, `Tracer.start_span()`, and `LLMCache` so we can prove non-regression after each Tier 1 milestone.

### Milestone T1.0.1 — Characterization tests for the control-flow path

- **Objective**: Pin down `AgentLoop`'s current behavior before extending it.
- **Boundaries**: Write against `tests/test_loop_coverage.py`; do not modify `loopy/loop.py`.
- **Verification**: `python -m pytest tests/test_loop_coverage.py -v --no-header` exits 0 with all tests passing.
- **Acceptance Criteria**:
  - Test names reference "characterization" so they are visibly pinned-behavior
  - Coverage of `loopy/loop.py` ≥ 95% (currently 96%)
  - At least one test for: empty `LoopConfig`, callbacks raising, `stop_on_error=True`, `max_retries=0` boundary, default-stop with no callbacks configured, `initial_context=""` (empty), `initial_context=nonempty`, single-step loop, multi-step loop with custom `should_stop`
- **Negative Controls**:
  - A test calling `AgentLoop(LoopConfig(max_steps=100)).run()` without `state_manager` MUST NOT create any file (no implicit disk writes)
  - A test calling `await loop.run()` after `await loop.run()` MUST start fresh `history` (no global state)

### Milestone T1.0.2 — Characterization tests for trace + cache

- **Verification**: `python -m pytest tests/test_observe_coverage.py tests/test_cache_coverage.py --no-header` exits 0.
- **Acceptance Criteria**:
  - `loopy/observe.py` coverage ≥ 95% (currently 98%)
  - `loopy/cache.py` coverage ≥ 95% (currently 98%)
  - Tests cover: `Tracer` with no redactor (no scrubbing), `Tracer` with redactor on plain attributes, `Tracer` with redactor on nested attributes, `LLMCache` miss/hit/eviction, `LLMCache.aget`/`aset` round-trip, persist+reload, eviction at `max_size`

---

## Phase T1.1 — Graph Control Flow (`loopy/flow.py`, NEW MODULE)

### Milestone T1.1.1 — `Node`,` + `Edge` + `StateGraph` primitives

- **Objective**: Ship `loopy/flow.py` exposing typed, persistent, checkpointable graph workflows.
- **File to create**: `loopy/flow.py` (NEW; does not push the count to 22 because it lives under `loopy.loop` conceptually — **defer decision** to maintainer; for now export `from loopy.flow import Node, Edge, StateGraph, Workflow`).
- **Public surface (minimum viable)**:
  - `Node(name: str, run: Callable[[State, Context], Awaitable[State]])`
  - `Edge(from_node: str, to_node: str, condition: Callable[[State], bool] | None = None)`
  - `StateGraph(name: str, nodes: dict[str, Node], edges: list[Edge], entry: str, terminal: set[str])`
  - `Context(events: asyncio.Event, current_node: str, attempt: int)`
  - `Workflow(graph: StateGraph, state_manager: StateManager | None = None)`
  - `await workflow.run(initial_state: State) -> State`
- **Boundaries**:
  - Every node's `run` MUST be idempotent (workflow re-runs from history on resume)
  - No I/O in node `run`; route I/O through `executor: Callable[[Awaitable[T]], Awaitable[T]]` so tests can inject
  - Cycle detection at graph-build time (raise on cycle with no terminating edges)
- **Verification**: `python -m pytest tests/test_flow.py --no-header` exits 0 with ≥30 new tests.
- **Acceptance Criteria**:
  - Test: linear graph A→B→C runs once
  - Test: branching graph routes based on state
  - Test: cycle without terminating edges raises `ValueError` at build
  - Test: workflow persists state to `StateManager` after every node
  - Test: `await workflow.run()` after `state_manager.load()` resumes at last completed node (NOT from start)
  - Test: workflow with no `state_manager` runs in-memory only (no disk)
  - Test: `Tracer` records one span per node when started inside the workflow
  - Test: `Redactor` applied to state at storage time (no PII leaks to disk)
- **Negative Controls**:
  - Calling `await node.run(state, ctx)` directly (not via `Workflow`) MUST NOT persist state
  - Crashing mid-node (raise from `node.run`) leaves the previous node's state intact
  - A `state_manager=None` workflow with a `Tracer(redactor=...)` still scrubs spans (orthogonal to persistence)

### Milestone T1.1.2 — `loopy/__init__.py` exports

- **Verification**: `from loopy.flow import Node, Edge, StateGraph, Workflow` works without import errors; `python -c "import loopy; assert 'Node' in dir(loopy)"` exits 0.
- **Acceptance Criteria**:
  - All 4 new symbols exported from top-level `loopy`
  - Listed in `__all__`
  - Listed in `docs/api/index.md`
  - Listed in `scripts/generate_llms_txt.py` `PUBLIC_MODULES` map

---

## Phase T1.2 — HITL Interrupts (extend `loopy/loop.py`)

### Milestone T1.2.1 — `Interrupt` + `interrupt_before` + `interrupt_after`

- **Objective**: Add human-in-the-loop primitives to `AgentLoop` so production agents can pause before sensitive actions.
- **Files to modify**: `loopy/loop.py` (`LoopConfig` + `AgentLoop.run`)
- **Public surface**:
  - `LoopConfig.interrupt_before: list[str] | None` — node names that pause BEFORE running (default `None` = no interrupts)
  - `LoopConfig.interrupt_after: list[str] | None` — node names that pause AFTER running (default `None`)
  - `Interrupt(proposed_action: str, decision: Literal["approve","reject"] | None = None, context: dict[str, Any] = {})`
  - `await loop.run(input, *, resume_from: Interrupt | None = None) -> State | list[StepResult]` — returns `Interrupt` instead of `list[StepResult]` when paused; `resume_from=Interrupt(decision="approve")` continues
- **Verification**: `python -m pytest tests/test_loop_coverage.py --no-header` exits 0; **at least 12 new tests** added for interrupt semantics.
- **Acceptance Criteria**:
  - Test: `interrupt_before=["actor"]` pauses before the actor runs; `run()` returns `Interrupt` with `proposed_action="Run actor step N with plan X"`
  - Test: `resume_from=Interrupt(decision="approve")` skips the pause and continues
  - Test: `resume_from=Interrupt(decision="reject")` raises `AgentLoopRejected` exception with the original plan in context
  - Test: `interrupt_after=["actor"]` pauses after the actor runs; the `Interrupt` carries the actor's output for review
  - Test: `interrupt_before + interrupt_after` together pause 2x per loop iteration
  - Test: `interrupt_before=[None]` (no matches) is a no-op
  - Test: `resume_from=Interrupt()` (no decision) is invalid → raises `ValueError`
  - Test: When the loop finishes without hitting an interrupt, returns `list[StepResult]` as today (backward compatible)
  - Test: `interrupt_*` with `state_manager` persists the `Interrupt` in `LoopState.history` so a crash+resume can replay
- **Negative Controls**:
  - `interrupt_before=[]` and `interrupt_after=None` MUST behave identically to current `AgentLoop` (regression check)
  - `LoopConfig(interrupt_before=["actor"], max_steps=0)` MUST raise `ValueError` at construction (cannot interrupt nothing)

### Milestone T1.2.2 — `AgentLoopRejected` exception

- **File to create**: in `loopy/loop.py` (or new `loopy/exceptions.py` if maintainer prefers)
- **Public surface**: `AgentLoopRejected(proposal: str, context: dict)` with `.message`, `.context`, `__str__`
- **Verification**: `python -m pytest tests/test_loop_coverage.py -v --no-header -k reject` passes
- **Acceptance Criteria**:
  - `AgentLoopRejected` is exported from `loopy`
  - The exception carries enough context for a UI to render a re-prompt

---

## Phase T1.3 — OTel Auto-Instrumentation (`loopy/observe.py`)

### Milestone T1.3.1 — `@observe()` decorator + auto-instrument `Gateway.chat`

- **Objective**: Decorator + `auto_instrument_gateway()` helper so users get tracing for free.
- **Files to modify**: `loopy/observe.py`
- **Public surface**:
  - `@observe(name: str | None = None, attributes: dict | None = None)` — async + sync decorator
  - `auto_instrument_gateway()` — patches `Gateway.chat` to wrap every call in a span
  - `auto_instrument_mcp()` — patches `MCPClient.call_tool` to wrap every call in a span
- **Verification**: `python -m pytest tests/test_observe_coverage.py --no-header` exits 0 with ≥10 new tests.
- **Acceptance Criteria**:
  - Test: `@observe()` async function produces one span; attributes are set
  - Test: `@observe()` sync function produces one span
  - Test: `@observe()` exception inside the function marks span as `ERROR` with `error.message`
  - Test: `auto_instrument_gateway()` makes `chat()` produce a `generation` span (model + tokens)
  - Test: `auto_instrument_mcp()` makes `call_tool()` produce a span (tool name + result)
  - Test: instrumentation respects `Tracer(redactor=...)` — span attributes are scrubbed
  - Test: instrumentation respects `Tracer.disabled` flag — no spans when disabled
- **Negative Controls**:
  - Calling an `@observe()`-decorated function after `Tracer.shutdown()` MUST NOT raise (graceful no-op)
  - Double-applying `@observe()` MUST NOT produce nested duplicate spans

### Milestone T1.3.2 — OTLP HTTP exporter

- **File to modify**: `loopy/observe.py::TraceExporter`
- **Public surface**: `TraceExporter(tracer, endpoint=None, headers=None, timeout=10.0, max_retries=3, protocol="otlp-http")` — `protocol="otlp-http"` sends standard OTLP JSON; default unchanged.
- **Verification**: `python -m pytest tests/test_observe_coverage.py --no-header` passes with the new test for OTLP envelope shape.
- **Acceptance Criteria**:
  - `protocol="otlp-http"` produces a valid OTLP `ExportTraceServiceRequest` JSON payload
  - Existing `protocol="otel"` (or default) behavior unchanged (regression check)

---

## Phase T1.4 — Tier 1 Verification Gate

### Milestone T1.4.1 — Full v0.8.0 acceptance gate

- **Verification**: every P0.x + every Phase T1.x verification command in sequence.
- **Acceptance Criteria (ALL must pass)**:
  - `git status --short` clean
  - `python -m pytest --no-header` exits 0 with **≥650 tests passing** (581 baseline + ≥70 new for T1.0–T1.3)
  - `python -m ruff check loopy/ tests/` exits 0
  - `python -m ruff format --check loopy/ tests/` exits 0
  - `python -m pytest --cov=loopy --cov-fail-under=90` exits 0 with coverage ≥ 92% (preserve baseline)
  - `from loopy import Node, Edge, StateGraph, Workflow, Interrupt, AgentLoopRejected, observe, auto_instrument_gateway` succeeds
- **Commit + Tag**: commit with `feat(loop): v0.8.0 - graph control flow, HITL interrupts, OTel auto-instrumentation`; tag `v0.8.0`; push (release pipeline publishes to PyPI)
- **CHANGELOG**: add `[0.8.0] - 2026-XX-XX` section per `CHANGELOG.md` template; update summary table

### Milestone T1.4.2 — Documentation updates

- **Verification**: `python scripts/generate_llms_txt.py` exits 0; `llms-full.txt` references the new symbols
- **Acceptance Criteria**:
  - `docs/modules/flow.md` exists and documents `StateGraph` with a worked example
  - `docs/getting-started.md` has an "HITL example" section
  - `docs/research/competitive-analysis-2026.md` capability matrix gets updated: loopy now has graph control flow (✓), HITL interrupts (✓), OTel auto-instrumentation (✓)
  - `README.md` mentions v0.8.0 in the "headline features" callout

---

# Tier 2 — v0.9.0 "Trust Layer"

> **Theme**: double down on what loopy uniquely does (compliance, audit, plugins) by closing the MEDIUM-severity gaps and shipping the A2A handoff + cost-aware adaptive routing.
> **Source**: Tier 2 of `docs/research/competitive-analysis-2026.md` §4.
> **Goal**: 8 MEDIUM-severity findings → 0; ship A2A handoff + Compliance-as-Code policies + cost-aware adaptive routing.

## Phase T2.0 — Characterization for A2A handoff

### Milestone T2.0.1 — Pin A2A `broadcast` + `call_agent` behavior

- **Verification**: `python -m pytest tests/test_a2a.py --no-header` exits 0
- **Acceptance Criteria**: at least 5 new characterization tests that record A2A broadcast current behavior (so v0.9.0 changes don't regress it)

---

## Phase T2.1 — A2A Handoff Protocol (extend `loopy/a2a.py`)

### Milestone T2.1.1 — Agent Card discovery

- **File to modify**: `loopy/a2a.py`
- **Public surface**:
  - `async A2AClient.fetch_agent_card(url: str) -> AgentCard`
  - `AgentCard(name, provider, version, url, skills: list[dict], authentication: dict)`
  - `A2AClient.from_agent_card(card: AgentCard) -> A2AClient` — constructor alternative
- **Verification**: ≥8 new tests in `tests/test_a2a.py` covering fetch, parse, from_card, error on malformed, SSRF (only allow `http://`/`https://` not `file://`).
- **Acceptance Criteria**:
  - Test: `fetch_agent_card("https://example.com/.well-known/agent-card.json")` returns parsed `AgentCard`
  - Test: malformed JSON raises `A2AError`
  - Test: `file://` URL rejected by `netutil.validate_outbound_url` (existing SSRF guard)
  - Test: cached `AgentCard` reused if `ttl=3600` not expired
- **Negative Controls**:
  - `A2AClient.from_agent_card(card)` with `card.authentication not in {"none","api_key","oauth2","openIdConnect"}` raises `ValueError`

### Milestone T2.1.2 — Task lifecycle + streaming

- **File to modify**: `loopy/a2a.py`
- **Public surface**:
  - `A2ATask(id, state: Literal["submitted","working","input-required","completed","failed","canceled","rejected"], artifacts: list[dict])`
  - `async A2AClient.create_task(skill_id: str, inputs: dict, *, callback_url: str | None = None) -> A2ATask`
  - `async A2AClient.get_task(task_id: str) -> A2ATask`
  - `async A2AClient.cancel_task(task_id: str) -> A2ATask`
  - `async A2AClient.stream_task(task_id: str) -> AsyncIterator[A2ATask]` — SSE streaming
- **Verification**: ≥12 new tests covering state transitions, callback URL signature verification, idempotency, cancellation mid-stream.
- **Acceptance Criteria**:
  - Test: `create_task` returns `submitted` then `working` then `completed` for a happy-path mock server
  - Test: `callback_url` requires HMAC signature on incoming webhook (verify via `hmac.compare_digest`)
  - Test: `stream_task` yields one event per `TaskStatusUpdateEvent`
  - Test: `cancel_task` transitions `working` → `canceled` and the stream stops
  - Test: `input-required` state carries a `question` artifact for the human
- **Negative Controls**:
  - Tampered webhook HMAC signature → `400 Bad Request` (handled in `A2AClient._verify_webhook`)
  - `create_task` for unknown `skill_id` raises `A2AError` immediately (no network call)

---

## Phase T2.2 — Compliance-as-Code Policies (`loopy/compliance.py` + new `loopy/policies.py`)

### Milestone T2.2.1 — Policy DSL + policy engine

- **File to create**: `loopy/policies.py` (NEW; under `loopy.compliance` conceptually)
- **Public surface**:
  - `Policy(name: str, conditions: list[Condition], severity: Literal["info","warn","block"])`
  - `Condition(kind: Literal["max_retries","max_cost_usd","pii_in_input","rate_limit"], value: Any)`
  - `PolicyEngine(policies: list[Policy], audit_sink: Callable[[PolicyDecision], None] | None = None)`
  - `engine.evaluate(context: dict) -> list[PolicyDecision]`
- **Verification**: ≥10 new tests in `tests/test_compliance.py`
- **Acceptance Criteria**:
  - Test: `PolicyEngine` evaluates 5 policies in <1ms (no I/O)
  - Test: `PolicyDecision` includes `policy_name`, `verdict`, `context`, `timestamp`
  - Test: `block` verdict raises `PolicyViolation` when used as a gate
  - Test: `warn` verdict logs but does not block
  - Test: `audit_sink` receives every decision (block + warn + info)
- **Negative Controls**:
  - Empty `policies=[]` evaluates to empty list (no false positives)
  - Policy with malformed `Condition.value` raises `ValueError` at construction

### Milestone T2.2.2 — Gate `Gateway.chat` + `AgentLoop.step` via PolicyEngine

- **Verification**: ≥8 new tests covering "policy blocks a chat call" and "policy blocks a loop step"
- **Acceptance Criteria**:
  - Test: `Gateway(..., policy_engine=engine).chat(...)` raises `PolicyViolation` when a `block` policy fires
  - Test: `AgentLoop(LoopConfig(policy_engine=...)).run()` records every `PolicyDecision` in `LoopState.history`
  - Test: `Redactor` applied AFTER policy evaluation (so audit log shows raw, storage shows scrubbed)

---

## Phase T2.3 — Cost-Aware Adaptive Routing (extend `loopy/gateway.py` + `loopy/cost.py`)

### Milestone T2.3.1 — `Gateway.chat(max_cost_usd=...)`

- **Verification**: ≥10 new tests
- **Acceptance Criteria**:
  - Test: `max_cost_usd=0.01` + estimated cost `0.05` raises `BudgetExceeded` BEFORE HTTP request fires
  - Test: `max_cost_usd=None` disables cost guard (default behavior, regression check)
  - Test: provider-fallback: when OpenAI budget exceeded, falls back to Ollama (cheapest configured provider)
  - Test: `CostTracker` records estimated cost + actual cost + savings from fallback

---

## Phase T2.4 — Tier 2 Verification Gate

### Milestone T2.4.1 — Full v0.9.0 acceptance gate

- **Acceptance Criteria**:
  - All P0.x + every Phase T2.x verification command passes
  - `python -m pytest --no-header` exits 0 with **≥750 tests passing** (650 from v0.8.0 + ≥100 new for T2.0–T2.3)
  - Coverage ≥ 92%
  - `from loopy import Policy, PolicyEngine, PolicyViolation, A2ATask` succeeds
- **Commit + Tag**: `feat: v0.9.0 - A2A handoff, Compliance-as-Code, cost-aware routing`; tag `v0.9.0`; push

---

# Tier 3 — v1.0.0 "Production-Grade by Default"

> **Theme:** make loopy a deployable **runtime** (not just a library) by shipping durable execution (Temporal-grade, in-process) and verified agent programs.
> **Source:** Tier 3 of `docs/research/competitive-analysis-2026.md` §4.
> **Goal:** ship the moonshot — durable SQLite-backed runtime + Hypothesis-based `VerifiedAgent`. Promote to `Development Status :: 5 - Production/Stable` in classifiers.

## Phase T3.1 — Durable Agent Runtime (`loopy/durable.py`)

### Milestone T3.1.1 — `DAG` + `Step` + journal

- **File to create**: `loopy/durable.py` (NEW)
- **Public surface**:
  - `DAG(name, steps: list[Step])`
  - `Step(name, run, compensation: Callable | None = None)` (Saga compensation for rollback)
  - `Workflow.run(dag, initial_state, *, journal_path: str | None = None) -> State`
  - `ResumeToken(workflow_id: str, last_completed_step: str, journal_path: str)`
  - `Workflow.resume(token: ResumeToken) -> State`
- **Verification**: ≥20 new tests in `tests/test_durable.py`
- **Acceptance Criteria**:
  - Test: 3-step DAG completes, journal records each step's output
  - Test: step 2 raises → compensation for step 1 runs (Saga pattern), state reverts
  - Test: kill process mid-step → restart → picks resume at last completed step
  - Test: `ResumeToken` round-trips via pickle/json
  - Test: `journal_path=None` runs entirely in-memory (for tests + ephemeral use)
- **Negative Controls**:
  - Calling `Workflow.resume(token)` with a malformed token raises `ValueError`
  - A `DAG` with a step whose name contains `/` (path traversal) raises `ValueError` at construction

### Milestone T3.1.2 — Time-skipping test server

- **Public surface**: `Workflow.test_env(journal_path: str | None = None) -> TestEnv`
- **Verification**: ≥5 new tests
- **Acceptance Criteria**:
  - Test: `await env.sleep(days=7)` advances virtual clock without real waiting
  - Test: `env.now()` returns current virtual timestamp

---

## Phase T3.2 — Verified Agent Programs (`loopy/evals.py` + `loopy/verifier.py`)

### Milestone T3.2.1 — `VerifiedAgent`

- **File to create**: extend `loopy/verifier.py`
- **Public surface**:
  - `VerifiedAgent(agent: AgentLoop, spec: VerificationSpec)`
  - `VerificationSpec(input_schema: type[BaseModel] | None, invariants: list[Invariant], properties: list[Property])`
  - `await verified.verify(n_cases: int = 100) -> VerificationReport`
- **Verification**: ≥15 new tests using Hypothesis for property generation
- **Acceptance Criteria**:
  - Test: spec with `output_must_contain("hello")` fails when agent returns `"world"`
  - Test: property `output_len <= 10 * input_len` enforced across100 random cases
  - Test: hypothesis-generated invalid inputs do not crash the agent

### Milestone T3.2.3 — Hypothesis optional dependency

- **Public surface**: `pip install loopy-agent[hypothesis]` adds `hypothesis>=6.0`
- **Verification**: `python -c "import hypothesis; print(hypothesis.__version__)"` after `pip install -e .[hypothesis]` exits 0
- **Acceptance Criteria**: `[hypothesis]` extra present in `pyproject.toml`

---

## Phase T3.3 — Federated Runtime (`loopy/federate.py` + `loopy serve` CLI)

### Milestone T3.3.1 — `loopy serve` exposes Agent Card

- **File to create**: `loopy/federate.py` + extend `loopy/cli.py`
- **Public surface**:
  - `python -m loopy serve --port 8080 --agent ./my_agent.py` starts an HTTP server serving `/.well-known/agent-card.json` and `POST /tasks`
  - `AgentCluster(peers: list[str])` — connects to N peers
- **Verification**: ≥10 new tests using `aiohttp` test server or similar
- **Acceptance Criteria**:
  - Test: `GET /.well-known/agent-card.json` returns a valid Agent Card
  - Test: `POST /tasks` with valid input returns task id; `GET /tasks/{id}` returns state
  - Test: peer A and peer B can hand off tasks to each other

---

## Phase T3.4 — v1.0.0 Release Gate

### Milestone T3.4.1 — Promote to Production/Stable classifier

- **Files to modify**: `pyproject.toml::classifiers`
- **Change**: `"Development Status :: 3 - Alpha"` → `"Development Status :: 5 - Production/Stable"`
- **Verification**: `pip install . && python -c "from importlib.metadata import version; print(version('loopy-agent'))"` prints `1.0.0`

### Milestone T3.4.2 — Final acceptance gate

- **Acceptance Criteria**:
  - All P0.x + every Phase T3.x verification command passes
  - `python -m pytest --no-header` exits 0 with **≥900 tests passing**
  - Coverage ≥ 92%
  - `from loopy import DAG, Step, ResumeToken, VerifiedAgent, AgentLoopRejected` all succeed
  - `pip install loopy-agent[hypothesis,voice]` works
  - SBOM + Cosign in `.github/workflows/release.yml`
- **Commit + Tag**: `feat: v1.0.0 - durable runtime, verified agents, federated topology`; tag `v1.0.0`; push

---

# Cross-Tier Execution Guardrails

These rules apply **to every milestone**, in every tier. An agent that violates any of these fails the contract.

1. **Never skip a phase.** DB migrations before auth before logic. Tier 1 gates before Tier 2.
2. **Never modify a test assertion to pass artificially.** If the test fails, diagnose the production code; the test is the spec.
3. **Never mock the database or auth in integration tests.** Use real instances. `TestModel` is fine for chat, but `StateManager` writes to disk in every loop test.
4. **Commit after every milestone.** Each `verification command exits 0` MUST result in a `feat(...)` or `fix(...)` Conventional Commit.
5. **Run characterization tests after every change to existing code.** If `test_v0710_features.py::TestSkillA2AExport` fails after a loop change, the loop change is wrong.
6. **Strangler Fig on existing modules.** When extending `AgentLoop` (T1.2), add new methods alongside; do not delete the old `run()` until the new `run()` passes characterization tests + new behavior tests.
7. **Coverage must never decrease.** v0.7.10 is 92%. Every release must end at 92% or higher.
8. **Zero new public symbols without CHANGELOG + llms-full.txt update.** When `from loopy import NewSymbol` becomes possible, `CHANGELOG.md`, `docs/api/index.md`, `scripts/generate_llms_txt.py::PUBLIC_MODULES`, and `llms-full.txt` must all reflect it before tag.
9. **Tagging without green CI is forbidden.** Every release tag must be pushed only after `python -m pytest --no-header` and `python -m ruff check loopy/ tests/` both exit 0.

---

# Failure Protocol

If a verification command fails:

1. **Stop.** Do not proceed to the next milestone.
2. **Diagnose.** Read the exact error. Re-run with `-v` or `--tb=long`. Check `git log -p` for recent changes that might have introduced the regression.
3. **Fix root cause.** Not the test. Not the lint rule. The code.
4. **Re-run from the affected milestone onward.** Do not re-run pre-flight P0.x (those are environment invariants).
5. **Commit the fix as `fix(scope): ...`**. Reference the failing milestone in the commit body.
6. **If unfixable in 30 minutes**, escalate: the milestone is under-scoped or the design is wrong. Reopen the corresponding `dev-notes/RESEARCH.md` / `dev-notes/SPEC.md` section.

If you find yourself:
- Modifying a test to "make it pass"
- Disabling a lint rule to silence it
- Skipping a verification command because "it'll work later"
- Adding `None` checks that swallow real bugs

**Stop and re-read this `GOAL.md` from the top.**