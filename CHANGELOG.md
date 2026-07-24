# 📋 Changelog

All notable changes to loopy-agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
  
- **Tests** — 50 new tests (199 total)

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
