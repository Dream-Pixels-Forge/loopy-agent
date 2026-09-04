# 📋 Changelog

All notable changes to loopy-agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.1] - 2026-09-04

**v1.1.1 — "Try It More"** is a patch release that takes the
error-message audit pass rate from ~27% to 100%. Every public
``raise`` site in ``loopy/`` now carries a
``loopy.dev/docs/...#anchor`` URL with what-went-wrong and
how-to-fix guidance.

### Added

- **`scripts/patch_bulk.py`** — a small Python helper that
  reads ``dev-notes/ERROR_AUDIT.json``, finds each
  ``needs_work`` raise site, and appends the docs URL while
  preserving the existing source layout (handles single-line,
  multi-line, and docstring-adjacent raise messages without
  corrupting them).

### Changed

- **Every ``raise`` site in ``loopy/`` is now docs-linked**.
  Audit pass rate: 100% (71/71 non-exempt raise sites).
  The audit script (``scripts/audit_errors.py``) has an
  ``EXEMPT_LINES`` table for re-raises, internal sentinels,
  and AST-unparse false positives (e.g. ``Interrupt(...)``
  instantiation sites).

### Tests

- ``tests/test_error_messages.py::TestErrorAuditThreshold::
  test_audit_at_least_95_percent_pass_rate`` is no longer
  marked ``xfail``; it now passes.

## [1.1.0] - 2026-09-04

**v1.1.0 — "Try It Now"** ships the three adoptability
primitives: ``loopy init`` (one-command project scaffold),
10 hand-written copy-pasteable recipes, and the error-message
audit infrastructure. The Playground UI is deferred to v1.1.1.

### Added

- **`loopy init <name>`** (T1.1) — new CLI subcommand that
  scaffolds a self-contained project directory with
  ``pyproject.toml`` (pinning ``loopy-agent[all]>=1.0.0``),
  ``agent.py`` (TestModel-backed, no API key required),
  ``loopy.yml``, ``.gitignore``, ``README.md``, and
  ``tests/test_agent.py``. Supports ``--no-test`` to skip the
  test file. Refuses path-traversal, absolute paths, empty
  names, and non-empty existing directories.
- **`loopy.config.LoopyConfig` + `load(path)`** (T1.1) — the
  ``loopy.yml`` config dataclass with `provider`, `model`,
  `max_steps`, `interrupt_before`, `interrupt_after`,
  `policy_engine_path`, `state_manager_path`, `redactor_config`
  fields. ``load()`` parses + validates with structured error
  messages that include docs URLs.
- **10 recipes in `examples/`** (T1.2) — single-file, < 100
  lines each, no API key required, all runnable with
  ``python examples/0X_name.py``: ``00_hello_world``,
  ``01_streaming``, ``02_cost_capped``, ``03_policies``,
  ``04_durable``, ``05_verified``, ``06_federation``,
  ``07_hitl``, ``08_redaction``, ``09_otel``.
- **`scripts/audit_errors.py`** (T1.3) — walks ``loopy/``,
  classifies every ``raise`` site as ``passes`` (contains a
  ``loopy.dev/docs/...#anchor`` URL) or ``needs_work``, writes
  ``dev-notes/ERROR_AUDIT.json``. Exposes an ``EXEMPT_LINES``
  table for re-raises and internal sentinels.

### Changed

- **Error messages on 12 public exceptions** (T1.3) now include
  a ``loopy.dev/docs/...`` URL with what-went-wrong / how-to-fix
  guidance: ``LoopConfig(max_steps<1)`` (new universal rule),
  ``LoopConfig(unknown phase)``, ``Step(name empty)``,
  ``Step(name contains '/')``, ``DAG(steps empty)``,
  ``DAG(duplicate step name)``, ``ResumeToken(malformed)``,
  ``Workflow.resume(not a ResumeToken)``,
  ``FederatedServer(port wrong type)``, ``Policy(name empty)``,
  ``Policy(conditions empty)``, ``validate_outbound_url(...)``.
- **`LoopConfig(max_steps<1)` is now universally rejected**
  (v1.1.0). Previously only enforced when interrupts were
  configured; a zero-step loop never runs anything.
- **`FederatedServer.__init__` validates `port`** (v1.1.0): must
  be an ``int`` in ``[0, 65535]``. Fails fast rather than
  surfacing a confusing socket error later.

### Fixed

- ``tests/test_loop_interrupt.py::test_max_steps_zero_without_interrupts_allowed``
  replaced by ``test_max_steps_zero_raises_v1_1`` to reflect
  the new universal ``max_steps >= 1`` rule.

### Deferred to v1.1.1

- Bulk error-message audit pass rate (≥ 95% of all raise
  sites). v1.1.0 ships the 12 most-touched public messages +
  the tooling; the bulk pass is the goal of v1.1.1. The
  ``test_audit_at_least_95_percent_pass_rate`` test is marked
  ``xfail``.
- The Playground UI is being built in a separate repo
  (`loopy-playground`) and ships as v1.1.1.

## [1.0.1] - 2026-09-03

Patch release fixing a public-import collision in v1.0.0.

### Fixed

- **Public `Workflow` / `State` import collision** — v1.0.0
  exported `Workflow` from `loopy.durable` (the new
  durable runtime) and `loopy.flow` (the v0.8.0 graph-flow
  primitive) at the same public name. Because `loopy.flow`
  was imported first in `__init__.py`, a top-level
  `from loopy import Workflow` returned the wrong class —
  `Workflow.run(dag, ...)` looked up `dag.state_manager` and
  raised `AttributeError`. The fix: re-bind `Workflow` and
  `State` to the durable versions **after** every other
  import in `loopy/__init__.py`. The flow primitives remain
  reachable at `loopy.flow.Workflow` / `loopy.flow.State`
  for backwards compatibility.

### Verified

- New functional smoke test against the installed wheel
  exercises every v1.0.0 public surface (DAG, ResumeToken,
  TestEnv, VerifiedAgent, FederatedServer) end-to-end.

## [1.0.0] - 2026-09-03

**v1.0.0 — Production-Grade by Default.** loopy ships the three
remaining 2026 production primitives so it can be deployed as a
runtime, not just a library: a durable workflow engine with
crash-safe journaling, property-based verification for agent
programs, and a federated HTTP runtime that lets multiple
agents discover and hand off tasks peer-to-peer.

### Added

- **Durable Agent Runtime (T3.1)** — new ``loopy.durable`` module.
  - ``DAG`` + ``Step`` + Saga compensation: when a step raises,
    every earlier step's ``compensation`` callable runs in
    reverse order so partial side effects can be rolled back.
  - ``Workflow.run`` / ``Workflow.resume(token, dag, state)``:
    a crash-safe on-disk journal lets a crashed run resume
    from the last completed step on a different process.
  - ``ResumeToken`` round-trips through pickle + JSON.
  - ``Workflow.test_env()`` returns a :class:`TestEnv` with a
    virtual clock: ``await env.sleep(days=7)`` advances the
    clock 604800s in well under 1s of real time, and the two
    envs are independent.
  - 27 new tests (DAG construction, 3-step happy path, journal
    persistence, Saga compensation, crash + resume,
    ResumeToken round-trip, in-memory mode, TestEnv).
- **Verified Agent Programs (T3.2)** — new ``loopy.verifier``
  module.
  - ``VerifiedAgent(agent, spec).verify(n_cases=100)`` drives
    the agent on a batch of inputs and returns a
    ``VerificationReport``.
  - ``VerificationSpec(invariants, properties)`` bundles
    rules; built-in ``output_must_contain`` and
    ``output_length_at_most`` factories.
  - 15 new tests covering spec construction, helper
    factories, the passing / failing invariant paths,
    multi-invariant evaluation, properties across N cases,
    and a Hypothesis integration (skipped when the
    ``[hypothesis]`` extra is not installed).
- **Federated Runtime (T3.3)** — new ``loopy.federate`` module.
  - ``FederatedServer`` exposes a minimal HTTP server
    (``GET /.well-known/agent-card.json``, ``POST /tasks``,
    ``GET /tasks/{id}``) on the stdlib ``ThreadingHTTPServer``
    so core stays zero-deps.
  - ``AgentCluster(peers)`` discovers and hands off tasks
    peer-to-peer; unreachable peers are silently skipped.
  - ``python -m loopy serve --port N --agent path.py`` new
    subcommand: loads the optional agent module, binds the
    federated server, prints the endpoints, and blocks on
    Ctrl+C. 10 new tests.
- **Optional extras** (T3.2.3 / T3.4.2):
  - ``pip install loopy-agent[hypothesis,voice]`` adds
    ``hypothesis>=6.0`` and ``websockets>=12.0``.
- **T3.4.1** — ``Development Status :: 3 - Alpha`` promoted to
  ``Development Status :: 5 - Production/Stable``.
- **T3.4.2** — release pipeline now generates a CycloneDX SBOM
  and Cosign-signs it keylessly (OIDC / Sigstore Fulcio).
  Artifacts (wheel, sdist, SBOM, signature, certificate) are
  all attached to the GitHub Release.
- **New public types**: ``DAG``, ``Step``, ``State``,
  ``Workflow``, ``ResumeToken``, ``TestEnv``, ``AgentCluster``,
  ``FederatedServer``, ``VerifiedAgent``, ``VerificationSpec``,
  ``VerificationReport``, ``Invariant``, ``Property``,
  ``output_must_contain``, ``output_length_at_most``.

## [0.9.0] - 2026-09-03

The **Trust Layer** release — ships A2A handoff (Agent Card discovery
+ task lifecycle), Compliance-as-Code policies, and cost-aware
adaptive routing so loopy is deployable in multi-tenant production.

### Added

- **A2A handoff (T2.1)** — `A2AClient.fetch_agent_card(url)` parses
  A2A v1.0 `/.well-known/agent-card.json` documents with SSRF
  protection and a TTL cache (`card_ttl=3600` default).
  `A2AClient.from_agent_card(card)` builds a client from a single
  card, rejecting unsupported authentication methods
  (`none` / `api_key` / `oauth2` / `openIdConnect`).
  `A2ATask` carries the 7-state lifecycle
  (`submitted` / `working` / `input-required` / `completed` /
  `failed` / `canceled` / `rejected`); `create_task`, `get_task`,
  `cancel_task`, and SSE `stream_task` round out the surface.
  Inbound webhooks are verified with HMAC-SHA256
  (`verify_webhook`).
- **Compliance-as-Code (T2.2)** — new `loopy.policies` module
  ships `Policy`, `Condition`, `PolicyEngine`, `PolicyDecision`,
  and `PolicyViolation`. Policies evaluate against a context
  dict and emit decisions with `info` / `warn` / `block`
  verdicts. `Gateway(policy_engine=...)` and
  `LoopConfig(policy_engine=...)` gate every chat and step
  *before* any side effect; the audit log keeps the raw context
  so violations are provable. 5 policies evaluate in <1ms.
- **Cost-Aware Adaptive Routing (T2.3)** — new
  `ProviderConfig.cost_per_1k_tokens` field ranks providers by
  cost. `Gateway.chat(..., max_cost_usd=X)` raises
  `BudgetExceeded` *before* any HTTP when the estimate exceeds
  the cap, and falls back to the cheapest configured provider
  that fits. `CostTracker.record_estimated(usd)` and
  `record_actual(usd, savings_from_fallback=...)` track the
  routing decisions; `CostReport` exposes `estimated_usd`,
  `actual_usd`, and `savings_usd` fields.
- **New public types**: `A2AError`, `A2ATask`, `Policy`,
  `PolicyEngine`, `PolicyDecision`, `PolicyViolation`, `Condition`.
- **T1.0.2 characterization flip** — `Tracer.disabled` is now
  a public flag (was a negative contract pin).

## [0.8.0] - 2026-09-02

The **Agent Control Plane** release — ships the missing 2026 primitives
so loopy is production-deployable as a runtime, not just a library.

### Added

- **Graph control flow (T1.1)** — `loopy.flow` now exports `Node`, `Edge`,
  `StateGraph`, and `Workflow` primitives. Compose typed, persistent,
  checkpointable workflows that integrate with `StateManager`, `Tracer`,
  `Redactor`, and `SkillRegistry` — a uniquely scrub-aware, skill-aware
  graph primitive set. Closes the **Graph control flow** row in the
  2026 capability matrix.

- **Human-in-the-loop interrupts (T1.2)** — `AgentLoop` gains
  `LoopConfig.interrupt_before` and `LoopConfig.interrupt_after` to
  pause any of `plan / actor / observer / reflector` before or after
  it runs. `run()` returns an `Interrupt` carrying the proposed action
  and a `when` context (`"before"` or `"after"`); resume with
  `run(resume_from=Interrupt(decision="approve"))` to continue or
  `decision="reject"` to raise `AgentLoopRejected`. Approved
  before-gates re-enter the same step so the after-gate can still
  fire. When `state_manager` is configured, pending interrupts
  persist as `RunRecord(outcome=INTERRUPTED)` and
  `LoopState.metadata["interrupts"]` so a crashed run can be replayed.
  21 new tests in `tests/test_loop_interrupt.py`. Closes the
  **HITL interrupts** row in the 2026 capability matrix.

- **`RunOutcome.INTERRUPTED`** — new enum value giving `RunRecord`
  a typed outcome for HITL-paused steps.

- **OpenTelemetry auto-instrumentation (T1.3)** — `Tracer` gains a
  `disabled: bool` flag and a one-way `shutdown()` latch. New
  public surface: `@observe(name=..., attributes=..., tracer=...)`
  decorator (sync + async, idempotent, exception-safe), and
  `auto_instrument_gateway()` / `auto_instrument_mcp()` monkey-patch
  `Gateway.chat` and `MCPClient.call_tool` so every call is wrapped
  in a span with one import. `build_otlp_envelope(spans, service=...)`
  returns the OTLP `ExportTraceServiceRequest` JSON shape, ready
  for `POST /v1/traces`. `get_default_tracer()` / `set_default_tracer()`
  drive the process-wide tracer the @observe() decorator resolves
  to. 10 new tests in `tests/test_observe_coverage.py`. Closes the
  OTel-native observability row of the 2026 capability matrix
  (now ✅✅).

---

## [0.7.10] - 2026-09-02

### Added

- **A2A Skill interop** — `Skill.to_a2a_card()` / `Skill.from_a2a_card()`
  serialize to / from the A2A Skill primitive shape. `SkillRegistry.to_a2a_skills()`
  exports every skill as A2A primitives, suitable for embedding in an
  Agent Card served at `/.well-known/agent-card.json` (A2A v1.0 spec).
  Names slugify to ids, modality metadata round-trips, and JSON serialization
  is verified by tests. Positions loopy as the **interoperability hub**
  between MCP and A2A.

- **`RealtimeSession` for voice-first agents** — new async iterator in
  `loopy.multimodal.RealtimeSession` wrapping any `RealtimeTransport`
  implementation (Protocol class). Yields normalized `RealtimeEvent`
  objects (SESSION_CREATED / TRANSCRIPT_DELTA / AUDIO_DELTA / TOOL_CALL /
  ERROR / CLOSED). The WebSocket transport itself is pluggable; loopy
  ships no hard `web` dep, users wire in their preferred client.
  Background pump runs as a task; `contextlib.suppress` ensures graceful
  shutdown. New optional extra: `pip install loopy-agent[voice]`
  (installs `websockets>=12.0`).

- **Docs site (`docs/`)** — mkdocs-material configuration at
  `docs/mkdocs.yml`. Pages: `index.md`, `getting-started.md`,
  `concepts.md`, `modules/{loop,gateway,multimodal,skills,safety,mcp,state,audit}.md`,
  `recipes/index.md`, `api/index.md`, `research/competitive-analysis-2026.md`.

- **`llms-full.txt` + per-module dumps** — `scripts/generate_llms_txt.py`
  emits the public API surface as plain text that AI coding assistants
  (Cursor, Claude Code, Continue, Aider, Cody, etc.) can ingest. 22 per-module
  files (`llms-loopy-loop.txt` ... `llms-loopy-patterns.txt`) for finer
  context. Generated automatically; CI-friendly.

- **`AGENTS.md`** — context document for Cursor / Cline / Continue /
  Aider / Windsurf, including coding conventions, test patterns, and
  release process.

- **`skills/loopy-router.md`** — routing skill for Claude Code / Copilot /
  Codex / Windsurf / Gemini CLI that maps user requests to the right
  loopy module.

- **Strategic research doc** — `docs/research/competitive-analysis-2026.md`
  captures the deep analysis of Pydantic AI, LangGraph, LlamaIndex,
  CrewAI, OpenAI Agents SDK, AutoGen, Atomic Agents, plus Temporal,
  Langfuse, MCP, and A2A. Includes a 3-tier roadmap for v0.8.0 /
  v0.9.0 / v1.0.0 with implementation anchors.

### Changed

- `pyproject.toml` adds new optional `voice` extra
- Test count: **547 → 581** (+34 new tests in `tests/test_v0710_features.py`)
- Coverage: **92%** (loopy/multimodal.py 94%, loopy/skills.py 86%)
- Top-level exports: `RealtimeSession`, `RealtimeEvent`,
  `RealtimeEventType`, `RealtimeTransport`

---

## [0.7.9] - 2026-09-02

### Added

- **`TestModel` — zero-network LLM for unit tests** — drop-in replacement
  for the HTTP path. Pass `TestModel(responses=[...])` or the sentinel
  `"test"` string to `Gateway.chat(model=...)` and the gateway returns
  canned `GatewayResponse` objects with no network, no API keys, no
  rate limits. Supports callable responses, simulated latency, tool
  calls, and `raise_on_message` for testing error paths. Logs the
  call under `provider="test"` so `Gateway.get_logs()` / cost tracking
  still see it. *`-`No other agentic library SDK ships a TestModel
  primitive with this level of configurability.*

- **`StructuredOutput` via `response_format`** — pass any Pydantic
  `BaseModel` subclass to `Gateway.chat(response_format=MyModel)` and
  the gateway validates the model reply and returns the typed instance
  in `GatewayResponse.structured`. Failures set `structured=None` and
  log a warning so callers can detect + retry. Works with `TestModel`
  too (the canned response is validated as JSON), enabling end-to-end
  agent testing **with zero network and full type safety**.

- **`Redactor` — PII / secret aware scrubbing** — new
  `Redactor` dataclass with 9 built-in patterns (email, phone, SSN,
  credit card, OpenAI key, AWS key, JWT, Bearer, IPv4). Wire it via
  `Tracer(redactor=Redactor())` and span attributes are scrubbed
  before storage; `redactor.add_pattern(name, regex)` for custom
  patterns, `redactor.disable(name)` to opt out. `Redactor.redact()`
  is pure (never mutates input), `find_all()` returns matches for
  inspection, and `redact_value()` walks dicts / lists / tuples
  recursively. **Compliance gap closed**: traces no longer leak
  PII / credentials by default.

### Changed

- `GatewayResponse` gains a `structured: Any | None = None` field
- `Tracer` gains `redactor: Redactor | None = None` kwarg
- Test count: **508 → 547** (+39 new tests in `tests/test_v079_features.py`)
- Coverage: **92%** (loopy/observe.py 92% → 98%, loopy/gateway.py 94%)
- Top-level exports: `TestModel`, `TEST_MODEL_SENTINEL`, `Redactor`,
  `RedactionMatch`

---

## [0.7.8] - 2026-09-02

### Added

- **`AgentLoop` resume + checkpoint** — `LoopConfig` gains `resume_from: int`,
  `state_manager: StateManager`, and `task: str`. When `state_manager` is set,
  every completed step is recorded as a `RunRecord` (FIFO-bounded at 100) so
  crashed runs can be resumed by passing `resume_from=N` to pick up at step N+1.
  Compatible with the existing v0.5.0 `StateManager` / `LoopState` /
  `RunRecord` surface — no API churn for callers that don't opt in.
- **`SkillRegistry.match_ranked()` / `match_one()`** — ranked variant of
  `match()` returning `list[tuple[Skill, float]]` ordered by relevance
  (desc), plus a convenience `match_one()` that returns the best match or
  `None`. Backed by a new `Skill.score()` (multi-word triggers weight
  higher than single-word, normalized by trigger count, clamped at 1.0).
  `Skill.matches()` is preserved as a boolean API built on `score()`.
- **`LLMCache.aget()` / `aset()`** — async wrappers around the sync
  `get`/`set`. `aset()` runs disk persistence via `asyncio.to_thread` so a
  slow filesystem cannot block the event loop (mirrors the v0.7.7
  `MemoryStore` async-save pattern).
- **`EvalReport` JSON I/O** — `to_dict()`, `from_dict()`, `to_json()`,
  `from_json()`, `save(path)`, `load(path)`. Round-trips a full report
  (including every `EvalResult` and nested `EvalCase`) so eval reports can
  be archived, attached to PRs, and diffed across CI runs. `load()` returns
  an empty report on missing/unreadable files (with a warning) instead of
  raising. `EvalReport` is now exported from the top-level `loopy` package.

### Changed

- `EvalReport` added to public API surface (`loopy` re-export + `__all__`)
- Test count: **484 → 508** (+24 new tests in `tests/test_v078_features.py`)
- Coverage: 92% → ~93% (loop, skills, cache, evals paths all covered)

---

## [0.7.7] - 2026-08-19

### Fixed

- **`MemoryStore` blocking I/O in event loop** — `add()`, `delete()`, `clear()` called `_save()` synchronously, blocking the event loop during disk writes. Refactored to `asyncio.to_thread` so file I/O runs in a worker thread.
- **`A2AClient.broadcast` amplification** — unbounded broadcast could cause infinite loops when agents re-broadcast back. Added `max_depth` (default 3) and per-call cycle detection via a `visited` set.

> **Note:** This release also ships every fix listed under the `[0.7.6]` section below. The `0.7.6` commit landed on master but was never tagged or published to PyPI — those changes rode along with `v0.7.7` instead.

---

## [0.7.6] - 2026-08-19

> **Note:** This section documents fixes that were committed but **never released as a standalone version**. There is no `v0.7.6` tag on GitHub and no `0.7.6` on PyPI; these changes shipped as part of **`v0.7.7`** on 2026-08-19. They are preserved here as a historical record of what was merged in chronological order.

### Fixed

- **`ComplianceChecker` fake async** — `check_soc2`, `check_gdpr`, `check_eu_ai_act`, and `AuditLogger.log`/`query`/`summary` were declared `async def` but contained zero `await` calls. Removed `async` keyword so callers get correct sync behavior without the overhead of coroutines.
- **`DecisionTracker` unbounded memory** — `DecisionTracker.traces` grew without bound; long-running sessions would OOM. Added `max_traces` parameter (default 100) with FIFO eviction of oldest traces.
- **`DriftDetector` dead code** — callback-presence check loop (`pass`) replaced with actual drift issue tracking: missing callbacks now emit warning-severity `DriftIssue` entries with remediation suggestions.
- **`MemoryStore` redundant disk I/O** — `recall()` and `get()` triggered full JSON serialization on every access for transient stats. Added dirty-flag gating so disk writes only happen on structural mutations (add/delete/clear).
- **`TraceExporter.export_http` no retry** — HTTP export failures silently dropped traces. Added configurable `max_retries` (default 3) with exponential backoff (1s, 2s, 4s).

---

## [0.7.5] - 2026-08-16

### Fixed

- **"19 Essential AI Concepts" → "21"** — corrected concept count across `README.md`, `pyproject.toml` description, `loopy/__init__.py` module docstring, and `loopy/cli.py` (argparse description + CLI banner). The actual module count is 21.
- **README architecture diagram out of date** — refreshed from 11 modules to the full v0.7.x tree of 27 source files (includes `_version.py`, `a2a.py`, `compliance.py`, `multimodal.py`, `netutil.py`, `patterns.py`, `prompting.py`, `streaming.py`, `explainability.py`, and `plugins/`).
- **`RuntimeWarning: coroutine never awaited` in CLI tests** — `tests/test_cli_coverage.py` swapped `instance = AsyncMock()` for `instance = MagicMock()` on non-async attributes; only the actually-awaited methods (`chat`, `close`) remain `AsyncMock`. Removed redundant `__aenter__` / `__aexit__` mocks (the CLI calls `gateway.close()` directly, not via `async with`).

### Added

- **`tests/test_marketplace_coverage.py`** — 44 new tests covering `PluginPackage`, package-name validation (6 valid + 14 invalid PEP 508 forms including URLs, `git+`/`hg+`/`svn+` refs, leading dashes, path separators, dot-dot, empty/long names, shell metacharacters), `install` / `uninstall` success-failure paths plus subprocess exception and `--upgrade` flag handling, cache I/O (load missing file, save→reload round-trip, corrupt JSON, update existing/new entries), and the `MarketplacePlugin` surface (`info`, `setup` only registers `read_only` tools, search/list/install helpers).

### Changed

- `loopy/plugins/marketplace.py` coverage: **57% → 100%**
- Total test count: **440 → 484**
- Total coverage: **90% → 92%**

---

## [0.7.4] - 2026-08-10

### Fixed

- **`ToolResult` name collision** — renamed `loopy.mcp.ToolResult` to `MCPToolResult` to resolve conflict with `loopy.plugins.tools.ToolResult`
- **Duplicate `Tool` export** — MCP version now exported as `MCPTool` via `__init__.py`
- **"8 Essential AI Concepts" → "19"** — corrected count in `pyproject.toml`, `__init__.py`, and `cli.py`
- **`hashlib.md5` → `hashlib.sha256`** — switched hash algorithm in `middleware.py` and `plugins/rag.py` for security scanner compliance

### Added

- **Complete `_types.pyi` rewrite** — 15+ missing type definitions including `MCPToolResult`, `Span`, `SpanStatus`, `CheckItem`, `ReadinessLevel`, and more
- **`py.typed` verification step** in CI workflow
- **12 new test files** — 440 tests (from 276) covering all 19 modules
- **90% code coverage** (from 78%) — major gains in gateway (43→96%), plugins (44→88%), middleware (66→92%)

### Changed

- Lint cleanup across all test and example files (ruff import ordering, unused imports, line length)

---

## [0.7.3] - 2026-08-05

### Fixed

- **`strip_md_media` nesting-aware** — link/image destinations containing
  balanced parentheses (`javascript:alert(1)`, `https://en.wikipedia.org/wiki/Foo_(bar)`)
  are now consumed whole, eliminating the trailing `)` residue in sanitized output

---

## [0.7.2] - 2026-08-05

### Security

- **`strip_md_media` strips all link destinations** — previously only `http(s)://` targets were dropped; `javascript:` / `data:` / `mailto:` destinations now also stripped (anti-XSS / anti-exfiltration when output is rendered)
- **Denial audit trail hardened** — `ToolRegistry` / `PluginRegistry` denial logs now redact secret-looking argument values (`api_key`, `token`, `password`, `authorization`, ...) and are bounded to the newest 1000 entries (`DENIAL_LOG_MAX`, `redact_arguments`)
- **Marketplace `uninstall` validated** — applies the same strict PEP 508 name check as `install`, closing option injection into `pip uninstall`

---

## [0.7.1] - 2026-08-05

### Security

- **Removed universal `execute_tool` meta-tool** — the Tools plugin no longer exposes a model-callable "run any tool" capability (prevents excessive agency after prompt injection)
- **Marketplace installer hardened** — `install_plugin` is no longer registered as an agent tool; `install()` accepts only bare PEP 508 package names (URLs, `git+` refs, local paths, and `--` option injection are rejected — `pip install` executes build code)
- **Capability gates on tool execution** — `ToolRegistry` and `PluginRegistry` enforce deny-by-default (disabled tools never run), per-parameter allow-lists, and a human-in-the-loop approval gate for consequential tools, with a denial audit trail
- **Memory hardened** — memory writes and the new clear kill-switch require approval; `MemoryStore.clear()` added for poisoning resets
- **SSRF guard** — new `validate_outbound_url` / `is_private_host` applied to MCP client, A2A endpoints, and multimodal URLs (rejects loopback/private/link-local when `allow_private=False`)
- **Calculator without `eval`** — replaced the char-allowlist `eval` with an AST-whitelisted evaluator (numeric literals + arithmetic only; arbitrary code cannot run)

### Added

- **Prompt assembly helpers** — `build_prompt` (privileged/unprivileged split with `[DATA]` spotlighting), `make_canary` / `check_canary` (leak detection), `strip_md_media` (anti-exfiltration output sanitization)
- **Security regression suite** — 48 tests covering the above (tool gates, SSRF, safe eval, marketplace validation, memory approval, prompting helpers)

---

## [0.7.0] - 2026-08-05

### Added

- **MCPClient as async context manager** — `async with MCPClient(...) as client:` for automatic connection teardown

### Fixed

- **CI lint** — resolved all `ruff` violations (import sorting, unused exports, type-stub gaps, line length)
- **CI tests** — added `pytest-asyncio` to dev dependencies so the async test suites run in CI
- **Type stubs** — added missing `Router`, `RoutingRule`, and `SubTask` definitions to `_types.pyi`

### Changed

- **Release pipeline** — single-trigger workflow (`v*` tag → tests → build → GitHub Release → PyPI) using trusted publishing (OIDC) with job-scoped permissions and pinned action versions
- **Version source** — canonical version lives in `loopy/_version.py`; `scripts/release.sh` updated accordingly

---

## [0.6.0] - 2026-04-22

### Added

- **Streaming** — Real-time token-by-token output
  - `Streamer` — Async stream collector with buffering
  - `StreamChunk` — Token/tool/thinking/error events
  - `StreamBuffer` — Configurable flush threshold
  - SSE format export for HTTP streaming
  
- **Multi-modal** — Image, audio, video support
  - `MediaContent` — Base64/URL media with OpenAI/Anthropic format conversion
  - `MultiModalMessage` — Text + media messages
  - `MultiModalBuilder` — Fluent API for building multi-modal messages
  - File loading with auto MIME detection
  
- **Compliance** — Regulatory frameworks built-in
  - `ComplianceChecker` — SOC2, GDPR, EU AI Act checks
  - `AuditLogger` — JSONL audit trail for all agent actions
  - `AuditEntry` — Structured audit records
  - `DataClassification` — PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED
  
- **Explainability** — Decision audit trail
  - `DecisionTracker` — Track reasoning chains
  - `DecisionTrace` — Full decision history with alternatives
  - `DecisionStep` — Individual decisions with confidence scores
  - JSON export for debugging and compliance
  
- **A2A Protocol** — Agent-to-Agent communication
  - `AgentCard` — Agent identity and capabilities
  - `AgentRegistry` — Discover agents by capability/pricing
  - `A2AClient` — Call other agents with request/response
  - `AgentCapability` — TEXT_GENERATION, CODE_GENERATION, etc.
  
- **Tests** — 50 new tests (198 total)

### Changed

- Version bumped to 0.6.0
- Updated all exports in __init__.py (154 total)

---

## [0.5.0] - 2026-04-22

### Added

- **Audit** - Loop Readiness Score (0-100) with L0-L3 levels
  - `LoopAuditor` - Score agent loops against 13 checklist items
  - `AuditReport` - Score, level, passed/failed checks, suggestions
  - `ReadinessLevel` - L0 (Draft), L1 (Report), L2 (Assisted), L3 (Unattended)
  - Inspired by loop-engineering's Loop Ready Score

- **State** - Durable state management
  - `LoopState` - Persistent loop state (task, attempts, history)
  - `StateManager` - Read/write state to JSON files
  - `RunRecord` - Record of each loop run (task, outcome, tokens, duration)
  - `RunOutcome` - success, failure, escalated
  - Auto-prune old records by age

- **Verification** - Maker/Checker pattern
  - `VerificationGate` - Separate implementer and verifier agents
  - `VerifyResult` - Pass/fail with score and feedback
  - Optional test function integration
  - Inspired by loop-engineering's maker/checker split

- **Cost** - Token cost tracking
  - `CostTracker` - Daily token budgets with persistence
  - `CostReport` - Usage, limit, remaining, percentage
  - `BudgetExceeded` - Exception when budget is exceeded
  - Inspired by loop-engineering's loop-cost tool

- **Skills** - Persistent agent knowledge
  - `Skill` - Parse SKILL.md files (name, description, triggers, instructions)
  - `SkillRegistry` - Load, match, and manage skills
  - Trigger-based matching for task routing
  - Inspired by loop-engineering's skills system

- **Drift** - Config/state drift detection
  - `DriftDetector` - Detect mismatches between config and runtime state
  - `DriftReport` - Issues list with severity and suggestions
  - Checks: max_steps, attempts, required fields

- **Patterns** - Production loop patterns
  - `PatternRegistry` - 7 built-in production patterns
  - `LoopPattern` - Name, description, cadence, risk, readiness level
  - Patterns: daily-triage, pr-babysitter, ci-sweeper, dependency-sweeper, changelog-drafter, post-merge-cleanup, issue-triage
  - Filter by risk level and cadence

- **Safety** - Production safety gates
  - `SafetyGate` - Denylist paths, escalation triggers, human gates
  - `SafetyCheck` - Path, attempts, and confidence checks
  - `SafetyResult` - Safe/unsafe with escalation recommendation
  - Default denylist for auth, payments, secrets
  - Inspired by loop-engineering's safety patterns

- **Tests** - 90 new tests (149 total)

### Changed

- Version bumped to 0.5.0
- Updated all exports in __init__.py (119 total)
- Updated CHANGELOG with v0.5.0 features

---

## [0.4.0] - 2026-07-24

### Added

- **AudioPlugin** - Speech-to-text and text-to-speech integration
  - `SpeechToText` - Whisper-compatible transcription
  - `TextToSpeech` - Multi-voice synthesis
  - Configurable providers (OpenAI, ElevenLabs, local)
  
- **MarketplacePlugin** - Plugin discovery and installation
  - `PluginMarketplace` - Search, install, uninstall plugins
  - PyPI integration for plugin distribution
  - Cache for installed plugins
  
- **New tests** - 4 additional tests (59 total)

### Changed

- Version bumped to 0.4.0
- Updated plugin lazy imports
- **Package renamed to `loopy-agent`** on PyPI (import name remains `loopy`)

---

## [0.3.0] - 2026-07-24

### Added

- **TraceExporter** - Export traces to external backends
  - `export_file()` - Export to JSON file
  - `export_stdout()` - Export to console
  - `export_http()` - Export to Jaeger/Zipkin via HTTP
  
- **RAGPlugin** - Retrieval-Augmented Generation
  - `Retriever` - Vector/keyword document search
  - `Document` - Document storage with metadata
  
- **ToolsPlugin** - Tool registry for function calling
  - `ToolRegistry` - Register and execute tools
  - `Tool` - Tool schema generation (OpenAI format)
  - Built-in calculator and JSON tools
  
- **MemoryPlugin** - Long-term agent memory
  - `MemoryStore` - Persistent memory storage
  - `Memory` - Memory entries with importance scoring
  - JSON file persistence
  
- **New tests** - 6 additional tests (55 total)

### Changed

- Version bumped to 0.3.0
- Updated plugins/__init__.py with lazy imports

---

## [0.2.0] - 2026-07-24

### Added

- **Evaluator-Optimizer Pattern** (2026 agentic workflow)
  - `EvalGate` - LLM-as-judge evaluation gate
  - `EvalGateType` - COMMAND, ARTIFACT, MANUAL, JUDGE
  - `JudgeConfig` - Configure evaluation criteria and thresholds
  - `EvalGateResult` - Pass/fail with score and feedback
  
- **Orchestrator-Workers Pattern**
  - `Router` - Pattern-based task routing to specialist agents
  - `RoutingRule` - Define routing patterns
  - `TaskDecomposer` - Break tasks into subtasks with dependencies
  - `SubTask` - Dependency-aware task execution
  
- **Async Context Managers**
  - `Gateway` now supports `async with` for automatic cleanup
  
- **Connection Pooling**
  - `ConnectionPool` - HTTP connection reuse for lower latency
  
- **New Middleware**
  - `RetryMiddleware` - Auto-retry with exponential backoff
  - `CircuitBreakerMiddleware` - Prevent cascade failures
  - `FallbackMiddleware` - Provider failover
  
- **New tests** - 12 additional tests (49 total)

### Changed

- Version bumped to 0.2.0
- Updated all exports in __init__.py
- Enhanced Orchestrator with routing and decomposition

---

## [0.1.0] - 2026-07-24

### Added

- **Agentic Loop** (`loop.py`)
  - `AgentLoop` - Plan → Act → Observe → Reflect cycle
  - `LoopConfig` - Configure callbacks and stopping conditions
  - `StepResult` - Track iteration results
  
- **AI Gateway** (`gateway.py`)
  - `Gateway` - Multi-provider LLM routing
  - `ModelProvider` - OpenAI, Anthropic, Ollama, Custom
  - `ProviderConfig` - Provider configuration
  - `GatewayResponse` - Unified response format
  - Batch requests and streaming support
  
- **Guardrails** (`guardrails.py`)
  - `GuardrailPipeline` - Input/output filtering
  - PII detection (SSN, email, phone, credit card)
  - Jailbreak detection
  
- **Evals** (`evals.py`)
  - `Evaluator` - Judge-based model evaluation
  - `EvalSuite` / `EvalCase` - Test case management
  - Simple string matching and LLM judge support
  
- **Cache** (`cache.py`)
  - `LLMCache` - Semantic token caching
  - TTL and LRU eviction
  - Hit rate tracking and cost estimation
  
- **Observability** (`observe.py`)
  - `Tracer` - Distributed tracing
  - `Span` - Operation tracking
  - `MetricsCollector` - Counter/histogram/gauge metrics
  
- **MCP Client** (`mcp.py`)
  - `MCPClient` - Model Context Protocol client
  - `LocalMCP` - Local tool execution
  
- **Multi-Agent** (`agents.py`)
  - `Orchestrator` - Agent pool management
  - `SubAgent` - Individual agent configuration
  
- **Middleware** (`middleware.py`)
  - `MiddlewarePipeline` - Composable request/response hooks
  - Built-in: Logging, Timing, RateLimit, Cache, Validation, Function
  
- **Plugin System** (`plugins.py`)
  - `Plugin` - Base plugin class
  - `PluginRegistry` - Central component registry
  - `PluginLoader` - Auto-discovery from packages/directories
  
- **CLI** (`cli.py`)
  - Commands: info, chat, guard, cache, trace, eval, agent
  
- **Type Stubs** (`py.typed`, `_types.pyi`)
  - Full IDE autocompletion support
  
- **Initial tests** - 37 tests passing

---

## Roadmap

### Future
- WebSocket support
- Advanced vector embeddings
- Code execution sandbox

---

## Version History Summary

| Version | Tests | Key Features |
|---------|-------|--------------|
| 0.1.0 | 37 | Initial 8 concepts |
| 0.2.0 | 49 | EvalGate, Router, Async, Middleware |
| 0.3.0 | 55 | Plugins, OpenTelemetry, RAG, Tools, Memory |
| 0.4.0 | 59 | Audio, Marketplace, Production Hardening |
| 0.5.0 | 149 | Audit, State, Verification, Cost, Skills, Drift, Patterns, Safety |
| 0.6.0 | 198 | Streaming, Multi-modal, Compliance, Explainability, A2A |
| 0.7.0 | 198 | Async MCPClient context manager, trusted-publishing release pipeline |
| 0.7.5 | 484 | Concept count fix, README refresh, marketplace tests |
| 0.7.6 | — | *Unreleased — shipped as part of 0.7.7* (compliance async fix, DecisionTracker bounds, drift detection, memory dirty flag, trace retry) |
| 0.7.7 | 484 | Memory async I/O, broadcast amplification guard *(also includes 0.7.6)* |
| 0.7.8 | 508 | Loop resume+checkpoint, ranked skill match, async cache, eval JSON I/O |
| 0.7.9 | 547 | TestModel (zero-network LLM), StructuredOutput, Redactor (PII/secret scrubber) |
| 0.7.10 | 581 | A2A Skill interop, RealtimeSession (voice), docs site + llms-full.txt + AGENTS.md + skills/ |
