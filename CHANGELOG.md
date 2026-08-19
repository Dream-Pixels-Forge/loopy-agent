# 📋 Changelog

All notable changes to loopy-agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.7.7] - 2026-08-19

### Fixed

- **`MemoryStore` blocking I/O in event loop** — `add()`, `delete()`, `clear()` called `_save()` synchronously, blocking the event loop during disk writes. Refactored to `asyncio.to_thread` so file I/O runs in a worker thread.
- **`A2AClient.broadcast` amplification** — unbounded broadcast could cause infinite loops when agents re-broadcast back. Added `max_depth` (default 3) and per-call cycle detection via a `visited` set.

---

## [0.7.6] - 2026-08-19

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

### v0.6.0 (Planned)
- Streaming improvements
- WebSocket support
- Advanced vector embeddings
- Rate limiting improvements
- Multi-modal support
- Image generation tools
- Code execution sandbox
- Enhanced security features

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
| 0.7.6 | 484 | Compliance async fix, DecisionTracker bounds, drift detection, memory dirty flag, trace retry |
| 0.7.7 | 484 | Memory async I/O, broadcast amplification guard |
