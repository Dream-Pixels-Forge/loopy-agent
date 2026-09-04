# Competitive Analysis & Roadmap — 2026

> **Status:** Living document. Last updated 2026-09-04 alongside v1.1.0 release (T1.1 `loopy init`, T1.2 10 recipes, T1.3 error-message audit tooling + 12 pinned exception messages; Playground UI deferred to v1.1.1).
> **Owner:** Dream Pixels Forge
> **Purpose:** Capture the strategic landscape so future contributors don't repeat the survey.

## Executive summary

`loopy-agent` competes in the Python agent SDK market alongside
**Pydantic AI**, **LangGraph**, **LlamaIndex**, **CrewAI**, **OpenAI
Agents SDK**, **Microsoft AutoGen** (in maintenance mode), and
**Atomic Agents**.

In 2026, loopy's **unique advantages** are: compliance-as-code, cost
budgets, drift detection, plugin marketplace with PEP-508 validation,
skill registry with ranked matching, safety + decision audit trail, and
a **pure-Python zero-deps core** (httpx + pydantic only).

Its **structural gaps** versus the leaders are: code-execution
sandbox, voice/realtime, and durable Temporal-grade workflows
in the cluster sense (T3.1's DAG/Step/Workflow is process-local;
the next step is external task-queue support). v0.8.0 closed
graph control flow, HITL interrupts, and OTel auto-instrumentation;
v0.9.0 closed A2A handoff, Compliance-as-Code, and cost-aware
adaptive routing; v1.0.0 closed durable workflow + verified
agents + federated HTTP.

The recommended **3-release path** is:

| Release | Theme | Headline features |
|---|---|---|
| **0.8.0** | "Agent Control Plane" | Graph control flow, HITL interrupts, OTel auto-instrumentation |
| **0.9.0** | "Trust Layer" | A2A handoff, Compliance-as-Code policies, Cost-aware adaptive routing |
| **1.0.0** | "Production-Grade, By Default" | Durable agent runtime (Temporal-grade), Verified agent programs |

Strategic positioning in one line:

> **"The only Python agent SDK that's both MCP-native and A2A-native,
> with built-in compliance, audit, and durability — pure-stdlib, zero
> infrastructure required."**

---

## 1. The competitors

### Tier 1 — Production leaders

#### Pydantic AI (`pydantic-ai`)

Built by the Pydantic team. v2.37.0, Sep 2026. Production/Stable
classifier. Most relevant competitor because loopy shares the
**pydantic + typed outputs** lineage.

**Headline features (2026):**

- **Typed structured outputs** — `output_type=<BaseModel>` returns a guaranteed typed value
- **Dependency injection** via `RunContext[Deps]` first-arg on tools
- **Model-agnostic providers** — string swap (`"openai:gpt-5.6-sol"`)
- **Pydantic AI Gateway** — single API key + failover + cost monitoring
- **Streaming APIs** — text + realtime voice (OpenAI Realtime, Gemini Live, Azure, Grok Voice)
- **Function tools via decorators** — `@agent.tool`, `@agent.tool_plain`; signature becomes schema
- **MCP support as first-class capability** — `capabilities=[MCP(url)]`
- **Native provider tools** (image gen, web search, etc.)
- **Deferred tools / HITL approval**
- **Hooks** at agent level
- **OpenTelemetry-native instrumentation** + Logfire integration
- **Pydantic Evals** — "evaluate any Python function, agents included"
- **Capability primitive** — bundle tools+instructions+hooks+settings, with `defer_loading=True`
- **YAML/JSON agent specs**
- **Durable execution** on Temporal/DBOS/Prefect/Restate/Kitaru/Airflow
- **`PydanticAIWorkflow` base class** for Temporal
- **CLI, web chat, realtime speech, UI event streams** from one `Agent`
- **Pydantic AI Harness** — official companion with Coder, Researcher
- **Realtime voice** with tool calls mid-conversation
- **Image generation** via `output_type=BinaryImage`
- **Embeddings** in-core
- **Pydantic Graph** — typed graph control flow
- **TestModel** — testing without API keys

**What loopy can borrow:** TestModel (already done in v0.7.9),
typed outputs (already done in v0.7.9), Pydantic Evals (already done).

#### LangGraph (`langgraph`)

v1.2.11. Built on top of LangChain. The **infrastructure layer** for
serious production agents.

**Headline features:**

- **Graph-based control flow** (Pregel/Beam execution, NetworkX-style API)
- **Durable execution** — survives failures/interruptions
- **Persistence + memory built in**
- **Streaming as first-class concern** (token, node, event streams)
- **Human-in-the-loop** with **interrupts** primitive
- **Mixing deterministic and agentic flows** in one graph
- **Subgraphs** — graph composition
- **Time-travel / debug replay** via persistence
- **Checkpointers** for state recovery

**Gap this exposes:** Loopy has no graph control flow. Even a flat
Plan→Act→Observe→Reflect loop loses to a typed graph for serious
production.

#### OpenAI Agents SDK (`openai-agents`)

v0.22.0, Aug 2026. "Lightweight yet powerful" provider-agnostic SDK.

**Headline features:**

- **Agent + Runner + handoff** primitives
- **4 run modes** driven by the same Runner: text, sandbox, realtime, voice
- **Tools** — Functions, MCP, Hosted (e.g. file/web search), Agents-as-tools
- **Guardrails** as first-class concept on Agent
- **Sessions** — automatic conversation history with optional backends (Redis, SQLAlchemy, MongoDB, Cloudflare KV, S3, Temporal, Dapr)
- **Tracing** — built-in, on by default
- **MCP** — native (ships MCP Python SDK as dep)
- **RealtimeAgent + RealtimeRunner** — server-side WebSocket voice
- **VoicePipeline** — turnkey STT → agent → TTS
- **HITL** — built-in mechanisms across runs
- **SandboxAgent** + pluggable sandbox clients (UnixLocal, Docker, Blaxel, E2B, Modal, Runloop, Daytona)
- **Structured outputs** via Pydantic

**Gaps this exposes:** HITL, sandboxing, voice, sessions/memory.

### Tier 2 — Specialized / smaller

#### LlamaIndex (`llama-index`)

v0.14.24, Aug 2026. Repositioned as "open-source framework for agentic
applications" (not just RAG). 300+ integration packages on LlamaHub.

**Headline features:**

- **Document agent platform** — Parse, Extract, Index, Split, LlamaAgents
- **Agentic Workflows** — event-driven primitives (`ctx.send_event`, `ctx.wait_for_event`)
- **AgentWorkflow** — multi-agent orchestration
- **LlamaAgents** (no-code Agent Builder)
- **Indices, graphs, query engines** — still the data-layer strength
- **300+ integrations** on LlamaHub

**Gaps this exposes:** Workflow event primitives, multi-agent orchestration.

#### CrewAI (`crewai`)

v1.15.18. Two paradigms: **Crews** (autonomous collaborative teams) +
**Flows** (event-driven control with decorators `@start`, `@listen`,
`@router`, `or_`, `and_`).

**What makes it distinct:**

- Hierarchical process with auto-assigned manager agent
- `role`/`goal`/`backstory` first-class on agents
- Pydantic-native structured state via Flows
- JSON-first project layout (`*.jsonc`)
- ~5.76× faster than LangGraph on a QA benchmark (claimed)
- Standalone, independent of LangChain

#### Microsoft AutoGen (`autogen-agentchat`, `autogen-core`, `autogen-ext`)

**Status: maintenance mode.** Microsoft directs new projects to
**Microsoft Agent Framework** (MAF).

**What was distinctive:**

- **Actor / RoutedAgent** model — message-passing, event-driven
- **Cross-language runtime** — Python + .NET, gRPC transport
- **Distributed runtime** out of the box
- **McpWorkbench** — first-party MCP tool workbench
- **Magentic-One** — batteries-included multi-agent team (web browsing + code exec + file handling)

#### Atomic Agents (`atomic-agents`)

v2.x. "Building AI agents, atomically."

**Headline features:**

- **Schema-first design** — `BaseIOSchema` for every agent/tool
- **Built on Instructor + Pydantic**
- **Context Providers** for dependency injection
- **Provider layer** delegated to Instructor (OpenAI, Anthropic, Gemini, Groq, Ollama, Mistral, Cohere, OpenRouter)
- **Atomic Forge** — prebuilt tool library (arXiv, BoCha, Calculator, DateTime, Hacker News, PDF Reader, SearXNG, Tavily, Web Scraper, Weather, Wikipedia, YouTube Transcript)
- **Atomic Assembler** CLI (`atomic`) for tool management
- **Schema chaining** — compose by aligning output schemas with input schemas
- **Hooks system** — monitoring, error handling, performance metrics, retry
- **AGENTS.md + skills** for AI coding assistants (Cursor, Copilot, Codex, Windsurf, Gemini CLI)
- **LLM-ready doc bundles** (`llms-full.txt`, `llms-docs.txt`, `llms-source.txt`, `llms-examples.txt`)
- **Available on Context7** for MCP-assisted assistants

**Gaps:** no MCP, no observability, no eval, no streaming (per their README), no TestModel equivalent.

---

## 2. The infrastructure & protocols (2026 must-knows)

#### Temporal (`temporalio`)

Distributed, scalable, durable orchestration engine. Turns `async def`
functions into workflows backed by a fault-tolerant event loop. Every
step (`execute_activity`, `asyncio.sleep`, `wait_condition`) is
recorded as a server timer/event. On worker crash/restart, the
workflow is **replayed** from history.

**Why this matters for agents:**

1. LLM calls are slow and flaky — long runs must survive worker OOM/deploy
2. Token-cost context — long conversations exceed context windows; Temporal splits into independently retryable activities
3. **HITL pauses** — `await workflow.wait_condition(...)` + `@workflow.signal(...)` lets agents wait days for human input without holding a process
4. **Time-skipping test server** — `WorkflowEnvironment.start_time_skipping()` for unit-testing multi-day orchestration

Pydantic AI ships a **`TemporalDurability()` capability** that turns
every model and tool call into a durable activity. Loopy has nothing
comparable.

#### Langfuse (`langfuse`)

v4.15.1, Aug 2026. MIT. Single Python SDK that does tracing +
 +
evaluation + +prompts + +REST.

**Pillars:**

- **OpenTelemetry-based tracing** with `span` + `generation` semantics
- **Datasets & experiments** — offline eval + GitHub Actions CI eval
- **LLM-as-a-judge** + custom scores
- **Versioned prompt management** server-side
- **REST API client**

**Open-source vs. Cloud split:** SDK is MIT; server is self-hostable
OSS or managed Cloud.

#### Model Context Protocol (MCP)

"USB-C for AI applications." Open standard maintained by Linux
Foundation (donated by Anthropic 2024). Now adopted by Claude, ChatGPT,
VS Code, Cursor, and many more.

**Primitives exposed:**

- **Tools** — model-callable functions
- **Resources** — data sources (files, DBs)
- **Prompts** — workflow templates

**Transports:** stdio, HTTP+SSE, Streamable HTTP.

#### Google Agent2Agent (A2A)

v1.0 (2025). Donated to the **Agentic AI Foundation** under Linux
Foundation (Aug 2026). Apache 2.0. TSC members: AWS, Cisco, Google,
IBM Research, Microsoft, Salesforce, SAP, ServiceNow.

**What it solves vs MCP:** MCP is *agent ↔ tool*; A2A is *agent ↔
agent*. Agents are opaque — no shared memory, tools, or proprietary
logic. JSON-RPC 2.0 over HTTP(S) (transport-agnostic; gRPC via formal
Extensions).

**Key concepts:**

- **Agent Card** (served at `/.well-known/agent-card.json`) — name, provider, URL, **Skills** (id, description, tags, examples), authentication schemes, capability flags (`streaming`, `pushNotifications`, `stateTransitionHistory`)
- **Message**, **Part** (text/file/data), **Artifact**, **Task** — JSON-RPC payload primitives
- **Methods:** `message/send`, `message/stream` (SSE), `tasks/get`, `tasks/cancel`, `tasks/resubscribe`, `tasks/pushNotificationConfig/*`
- **Task lifecycle:** `submitted → working → (input-required ↔ working) → completed | failed | canceled | rejected`
- **Push notifications** for async updates
- **SDKs:** Python, JavaScript, Java, C#/.NET, Go, Rust

Official samples integrations: LangGraph, CrewAI, Semantic Kernel,
Google ADK.

---

## 3. The capability matrix

| Capability (2026 must-have) | pydantic-ai | LangGraph | CrewAI | AutoGen | OpenAI Agents SDK | LlamaIndex | Atomic Agents | **loopy 0.8.0** | Gap severity |
|---|---|---|---|---|---|---|---|---|---|
| Typed structured outputs | ✅ | ❌ | partial | ❌ | ✅ | ✅ | ✅ | **✅** (v0.7.9) | — |
| Zero-network TestModel | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **✅** (v0.7.9) | — |
| PII redaction in traces | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **✅** (v0.7.9) | — |
| Graph control flow (vs flat loop) | ✅ (Pydantic Graph) | ✅✅ (Pregel core) | partial (Flows) | ❌ (loop-based) | ❌ | ✅✅ (event-step Workflows) | partial | **✅** (T1.1 — flow.py: Node, Edge, StateGraph, Workflow) | — |
| Durable workflows (Temporal-grade) | ✅ (capability) | ❌ (host) | ❌ | ❌ | ✅ (plugin preview) | ❌ | ❌ | **✅** (T3.1 — DAG + Step + Saga + Workflow.run/resume + journal + ResumeToken) | — |
| Human-in-the-loop interrupts | ✅ (deferred tools) | ✅✅ (interrupt primitive) | ✅ (Flows @router) | ✅ (UserProxy) | ✅ (concept) | ✅ (wait_for_event) | ❌ | **✅** (T1.2 — Interrupt + interrupt_before/after + AgentLoopRejected) | — |
| Multi-agent handoffs + A2A | partial | partial (subgraphs) | ✅✅ (Crews) | ✅ (group chat) | ✅✅ (handoffs) | partial | ❌ | **✅** (T2.1 — A2A v1.0 Agent Card + task lifecycle + SSE streaming + HMAC webhooks) | — |
| Voice / Realtime | ✅ (Realtime) | ❌ | ❌ | ❌ | ✅✅ (WebSocket) | ❌ | ❌ | ❌ | MEDIUM |
| Code-execution sandbox | partial (Harness) | ❌ | ❌ | ✅ (Magentic-One) | ✅✅ (SandboxAgent) | ❌ | ❌ | ❌ (SafetyGate for paths only) | MEDIUM |
| MCP as first-class capability | ✅✅ (Capability) | partial | partial | ✅ (McpWorkbench) | ✅✅ (native SDK dep) | partial | ❌ | ✅ (`MCPClient` exists) | — |
| OTel-native observability | ✅ (Logfire) | partial (LangSmith) | partial (AMP SaaS) | ❌ | partial (built-in trace, viz extra) | partial (OpenLLMetry) | partial (hooks) | ✅✅ (T1.3 — Tracer + @observe() + auto_instrument_gateway/mcp + OTLP envelope) | — |
| **Eval as a first-class primitive** | ✅ (Pydantic Evals) | ❌ | partial (AMP) | partial (Bench) | ❌ | ✅ (RAGAS + built-in) | ❌ | ✅ (EvalSuite, EvalGate, EvalReport) | — |
| **Compliance (audit + readiness)** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅✅ (audit.py + compliance.py — UNIQUE) | — |
| **Skill registry with ranked matching** | partial (Capability) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅✅ (skills.py — UNIQUE) | — |
| **Plugin marketplace + PEP-508 validation** | ❌ | partial (LangChain Hub) | ❌ | ❌ | ❌ | partial (LlamaHub) | ✅ (Atomic Forge) | ✅✅ (marketplace.py — UNIQUE) | — |
| **Built-in cost budget + drift detection** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅✅ (cost.py + drift.py + T2.3 cost-aware adaptive routing — UNIQUE) | — |
| **Built-in safety + decision audit trail** | partial (guardrails) | ❌ | ❌ | ❌ | partial (guardrails) | ❌ | ❌ | ✅✅ (safety.py + DecisionTracker — UNIQUE) | — |
| **Pure-Python, zero-deps core** | partial | ❌ (LangChain heavy) | ❌ | ❌ | partial | ❌ | ❌ | ✅✅ (httpx + pydantic only) | — |
| **AI-coding-assistant discovery** (llms-full.txt) | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅✅ | ❌ | MEDIUM |
| Total primary capabilities | 14 | 8 | 8 | 7 | 12 | 9 | 6 | **17** | |

**Score (v1.0.0):** Loopy wins on **8 unique axes** no competitor covers; ties on **9** axes (up from 4 in 0.7.9 — picked up graph control flow, HITL interrupts, OTel auto-instrumentation ✅✅, A2A handoff, and durable workflows); loses on **4** axes (Voice/Realtime MEDIUM; Code-exec sandbox MEDIUM; AI-coding-assistant discovery MEDIUM; Multi-agent A2A downgraded from HIGH to MEDIUM with the T2.1 work). The only HIGH gap remaining is durable workflows in the Temporal-grade sense — T3.1's DAG/Step/Workflow is process-local; the next step is external task-queue support.

---

## 4. The 3-tier roadmap

### 🏗️ Foundation Tier — "ship the missing 2026 primitives"

Goal: bring loopy up to parity with the 2026 production leaders. ~2-3 releases (0.8.x).

#### F1. Graph control flow — `loopy/flow.py` ✅ shipped in v0.8.0 (T1.1)

Replace / augment the flat Plan→Act→Observe→Reflect loop with **typed,
persistent, checkpointable workflows**.

- **Primitive:** `Node`, `Edge`, `StateGraph`, `Workflow`
- **Loopy's angle:** integrate with `StateManager` for persistence, `Tracer` for spans, `Redactor` for PII, `SkillRegistry` for node-level skill bindings
- **Wins:** matches LangGraph + LlamaIndex Workflows + Pydantic Graph. "Ship a checkpointable, type-safe, scrub-aware, skill-aware graph" is genuinely unique.
- **Effort:** ~1 week, ~30 tests — **DONE** (see `loopy/flow.py`, exported via `loopy.flow` and `loopy.flow_primitives`).

#### F2. Human-in-the-loop interrupts — extend `loop.py` ✅ shipped in v0.8.0 (T1.2)

- `AgentLoop` gets `interrupt_before: list[str] | None` and `interrupt_after: list[str]`
- `await loop.run(input, resume_from=Interrupt)` returns an `Interrupt` when a gate fires; `Interrupt(decision="approve")` continues, `decision="reject"` raises `AgentLoopRejected`
- Backed by `StateManager` — pending interrupts persist as `RunRecord(outcome=INTERRUPTED)` and `LoopState.metadata["interrupts"]` so a crash+resume can replay
- **Wins:** matches LangGraph `interrupt`, OpenAI Agents HITL, Pydantic AI deferred tools
- **Effort:** ~2 days, ~12 tests — **DONE** (21 new tests in `tests/test_loop_interrupt.py`, 671 total tests passing)

#### F3. A2A handoff — extend `a2a.py`

The v0.7.0 `A2AClient` has `broadcast` but no proper handoff. Implement:

- **Skill discovery via Agent Card** (auto-fetch `/.well-known/agent-card.json`)
- **Task lifecycle** (`submitted`/`working`/`completed`) matching the A2A v1.0 spec
- **Push notifications webhook** + signature verification
- **Streaming via SSE** for `message/stream`
- **Wins:** first-class A2A in a Python SDK with loopy's compliance + observability baked in
- **Effort:** ~1 week, ~20 tests

#### F4. Code-execution sandbox — extend `safety.py`

Already has `SafetyGate` for paths. Add `ShellSandbox`, `DockerSandbox`, `SubprocessSandbox`:

- AST-level command allowlist (allow `git status`, deny `rm -rf /`)
- Mount / network / / / output capture
- Heartbeat for long-running processes
- **Wins:** matches OpenAI Agents `SandboxAgent`, AutoGen `Magentic-One`
- **Effort:** ~4 days, ~15 tests

#### F5. Voice / Realtime — extend `multimodal.py`

- `RealtimeSession` wrapping WebSocket
- `multimodal.RealtimeSession.openai(model="gpt-realtime-2.1")` shortcut
- Stream audio + transcript alongside agent tool calls
- New `loopy-agent[voice]` extra with `websockets` dep
- **Wins:** matches OpenAI Agents realtime + Pydantic AI `agent.realtime()`
- **Effort:** ~4 days, ~10 tests

#### F6. OpenTelemetry auto-instrumentation — extend `observe.py`

- `@observe()` decorator wraps any async function as a span
- Auto-instrument `Gateway.chat` and `MCPClient.call_tool`
- Export to any OTel collector (`OTEL_EXPORTER_OTLP_ENDPOINT`)
- **Wins:** matches Langfuse, OpenLLMetry, Logfire — but zero-config
- **Effort:** ~2 days, ~10 tests — **DONE** (T1.3, see `loopy.observe.observe` /
  `auto_instrument_gateway` / `auto_instrument_mcp` / `build_otlp_envelope`,
  10 new tests in `tests/test_observe_coverage.py`).

#### F7. AI-coding-assistant discovery — `llms-full.txt`

- Generate `llms-full.txt`, `llms-docs.txt`, `llms-source.txt`, `llms-examples.txt`
- Ship `AGENTS.md` for Cursor/Cline/Continue/Aider, `skills/*.md` for Claude Code/Copilot/Codex/Windsurf/Gemini CLI
- **Wins:** matches Atomic Agents, LlamaIndex; gets Loopy picked up by Cursor/Copilot
- **Effort:** ~1 day, no code change (CI script)

### ⚡ Differentiation Tier — "double down on what loopy uniquely does"

~1-2 releases (0.9.x).

#### D1. Compliance-as-Code — extend `compliance.py` + `audit.py`

Turn compliance from "check against frameworks" into:

- **Policy DSL** — declarative YAML/JSON policies (`"max 3 retries on any PII error"`)
- **Policy engine** that gates `Gateway.chat` / `AgentLoop.step` execution
- **Audit export** — every policy decision is a `PolicyDecision` record in traces
- **Wins:** nobody has this. Pydantic AI has guardrails, but only "input/output regex check"; Loopy's policies can branch, chain, escalate, and gate execution.

#### D2. Skill schema-first contracts + A2A interop

Promote `Skill` from registry-shape to **schema-first skill contracts** (matching A2A's Skill primitive structure). Each skill declares typed inputs, typed outputs, expected latency, cost model, failure modes.

- `Skill.to_a2a_card(skill)` / `Skill.from_a2a_card(card)` (shipped in v0.7.10 as a quick win)
- `SkillRegistry.match_ranked()` ranks by **contract compatibility**, not just text overlap
- **Wins:** positions Loopy as the **interoperability hub** between MCP and A2A

#### D3. Plugin Marketplace + signed distribution

Add cryptographic signing to `marketplace.py`:

- Every plugin signed with a known key (like npm/PyPI)
- Trust on first use (TOFU) with explicit allowlist
- Plugin sandboxing — declared permissions (network: read / fs: read / sub-process: deny)
- **Wins:** nobody has signed plugins. Supply-chain security angle.

#### D4. Decision & Audit Trail Replay — extend `state.py`

- `LoopState.add_record()` + `replay_run(records)` re-runs the agent with same inputs and surfaces divergence from recorded outputs
- Drift detection integration — flag any decision that deviated from previous run's expected behavior

#### D5. Cost-aware adaptive routing — extend `gateway.py` + `cost.py`

- `Gateway.chat(max_cost_usd=...)`
- Auto-falls-back to cheaper provider if remaining budget < estimated cost
- **Wins:** only loopy + Helicone (external SaaS) have this as a library

### 🚀 Category-Defining Tier — "the moonshot"

~2-3 releases (1.0.x).

#### C1. Durable agent runtime (Temporal-grade, pure Python)

- **Primitive:** `DAG`, `Step`, `Saga` (compensating action), `Awaiter`, `ResumeToken`
- `Workflow.run()` returns a `ResumeToken`; `Workflow.resume(token)` continues where it left off, even after a crash
- **Backed by SQLite or in-memory journal** — zero external deps
- `start_time_skipping()` test server
- **Wins:** the only agent framework with built-in durable execution that doesn't require Temporal/DBOS/Redis
- **Effort:** 3-4 weeks, ~40 tests

#### C2. Verified agent programs (TDD for agents)

- `VerifiedAgent(spec=<IO pairs + invariants + properties>)`
- Property-based testing via Hypothesis
- `await verified_agent.verify(1000_random_cases)`
- **Wins:** nobody has this. AutoGen has `agbench` but not library-level. Loopy owns **"the only agent SDK where you can prove your agent works"**.

#### C3. The Open Agent Skill Standard — portable skills

- `Skill` as JSON Schema artifact matching A2A's Skill primitive
- `Skill.from_a2a_card(card)` / `Skill.to_a2a_card(skill)`
- Loopy becomes the bridge: any MCP server becomes a Loopy Skill, any A2A Skill becomes a Loopy Skill
- **Wins:** positions Loopy as the **interoperability hub** between MCP, A2A, and every other agent framework

#### C4. Federated agent topology

- `loopy serve` CLI exposes Agent Card on `/.well-known/agent.json`
- `AgentCluster` joins N peers via libp2p-style discovery
- `TaskRouter` fans out tasks across cluster (consistent-hashing on skill-id)
- **Wins:** autoGen has cross-language runtime; Loopy could have **federation-with-zero-infra** — no etcd, no Temporal cluster, no Redis
- **Effort:** 5+ weeks

---

## 5. v0.7.10 quick wins (shipped in 1 week)

Three high-leverage features that ladder up to F3, F5, and F7.

### Q1. Skill A2A interop — `loopy/skills.py`

`Skill.to_a2a_card()` and `Skill.from_a2a_card()`. Maps the loopy
Skill registry shape (name/description/instructions/triggers) to the
A2A Skill primitive (id/description/tags/examples). Lets loopy skills
be advertised in any A2A-compatible runtime.

### Q2. RealtimeSession skeleton — `loopy/multimodal.py`

`RealtimeSession` async context manager wrapping a WebSocket client.
Backward-compatible design that doesn't require `websockets` as a hard
dependency — `ImportError` with helpful message if the `loopy-agent[voice]`
extra isn't installed. Tests use a fake transport so no real WS calls.

### Q3. Docs site (`mkdocs-material`) + `llms-full.txt`

A `docs/mkdocs.yml` config + initial pages. CI script generates
`llms-full.txt` from the public API surface. Ship `AGENTS.md` for
Cursor/Cline/Continue/Aider, `skills/loopy-router.md` for Claude
Code/Copilot.

---

## 6. Implementation notes for future agents

When you (or a future agent) come back to this document to implement
Tier 1/2/3 features, here are the implementation anchors you'll need:

### F1. Graph control flow

- **Pattern:** state machine with typed edges; Pydantic Graph is the model
- **File to create:** `loopy/flow.py` (new module)
- **Wire-ins:** `loopy/state.py::StateManager`, `loopy/observe.py::Tracer.start_span`, `loopy/skills.py::SkillRegistry.match_ranked`, `loopy/observe.py::Redactor`
- **Test file:** `tests/test_flow.py`
- **Avoid:** reimplementing LangGraph — instead, lean into loopy's compliance/audit story ("scrub-aware, audit-native graph")

### F2. HITL interrupts

- **Pattern:** `AgentLoop.run()` returns `Interrupt | list[StepResult]`; caller decides to `loop.resume(interrupt_id, decision)`
- **File to extend:** `loopy/loop.py::AgentLoop`, `loopy/state.py::RunRecord`
- **Wire-ins:** `SafetyGate` (already has the shape for path-based HITL)
- **Test file:** `tests/test_loop_co.py` extension

### F3. A2A handoff

- **Pattern:** `A2AClient.fetch_agent_card(url)` → `A2AClient.create_task(remote_skill_id, inputs)` → poll or subscribe to task
- **File to extend:** `loopy/a2a.py`
- **Wire-ins:** `loopy/skills.py::Skill` (Q1 already bridges the gap), `loopy/observe.py::Tracer` (span per remote call)
- **Test file:** `tests/test_a2a.py` extension

### F4. Code-execution sandbox

- **Pattern:** pluggable backends (`ShellSandbox`, `DockerSandbox`) behind a `SandboxBackend` protocol
- **File to extend:** `loopy/safety.py` (already has `SafetyGate`; add `Sandbox` family)
- **Wire-ins:** `loopy/netutil.py` (SSRF guard), `loopy/prompting.py::CANARY_PREFIX` (prompt injection defense)
- **Test file:** `tests/test_safety.py` extension
- **Avoid:** executing arbitrary code in tests — use a `MockSandbox` backend

### F5. Voice / Realtime

- **Pattern:** `RealtimeSession` async context manager; `RealtimeSession.openai(model=...)` factory
- **File to extend:** `loopy/multimodal.py`
- **Wire-ins:** `Gateway` for transcript → LLM response cycle, `Tracer` for span, `Redactor` for transcript scrub
- **Test file:** `tests/test_multimodal.py` extension
- **Dependency:** `websockets>=12` (new `loopy-agent[voice]` extra, NOT core dep)

### F6. OTel auto-instrumentation

- **Pattern:** `@observe()` decorator that creates a span + records start/end + sets attributes
- **File to extend:** `loopy/observe.py`
- **Wire-ins:** `Tracer.start_span`, `Tracer.end_span` (already exist)
- **Test file:** `tests/test_observe_coverage.py` extension

### F7. AI-coding-assistant discovery

- **Pattern:** generate `llms-full.txt` from `loopy.__all__` + docstrings
- **File to create:** `scripts/generate_llms_txt.py` + `AGENTS.md` + `skills/*.md`
- **CI:** add to `.github/workflows/ci.yml` as a docs build step

### C1. Durable runtime

- **Pattern:** record every step in a journal (SQLite/in-memory); replay on resume
- **File to create:** `loopy/durable.py`
- **Avoid:** depending on Temporal directly — instead, build a minimal durable-execution API

### C2. Verified agent programs

- **Pattern:** Hypothesis integration; generate random cases from a schema, verify output
- **File to extend:** `loopy/evals.py`
- **Wire-ins:** existing `EvalReport`, `JudgeConfig`
- **Optional dependency:** `hypothesis>=6`

### C3. Open Agent Skill Standard

- **File to extend:** `loopy/skills.py`
- **Already shipped in v0.7.10:** `Skill.to_a2a_card()` / `Skill.from_a2a_card()`
- **Future work:** reverse direction — read an A2A server's `.well-known/agent-card.json` and import as Loopy skills

### C4. Federated agent topology

- **Pattern:** libp2p-style peer discovery, gossip protocol, consistent-hashing task router
- **File to create:** `loopy/federate.py`
- **CLI:** `loopy-agent serve` (extend `loopy/cli.py`)
- **Avoid:** introducing a P2P dependency — start with static peer lists, add discovery later

---

## 7. Strategic questions to revisit in 6 months

- **Has MCP shipped a "Skills" primitive?** If yes, Loopy's `skills.py` ↔ A2A interop becomes load-bearing — invest more here.
- **Has the Linux Foundation / Agentic AI Foundation A2A working group shipped a stable v2?** If yes, F3 (A2A handoff) becomes urgent.
- **Has OpenTelemetry added first-class "LLM generation" semantics?** If yes, F6 (auto-instrumentation) becomes much easier.
- **Has Temporal become the de-facto agent runtime?** If yes, C1 (in-process durable runtime) loses its differentiation; pivot to being a Temporal *client* instead.
- **Have supply-chain attacks on Python packages increased?** If yes, D3 (signed plugin marketplace) becomes the headline story.

---

## 8. References

- Pydantic AI 2.37.0 docs / PyPI listing (Sep 2026)
- LangGraph 1.2.11 (Aug 2026) — inspired by Pregel + Apache Beam; NetworkX-style API
- OpenAI Agents SDK 0.22.0 (Aug 2026) — provider-agnostic via 100+ LLMs
- LlamaIndex 0.14.24 (Aug 2026) — LlamaCloud + LlamaAgents
- CrewAI 1.15.18
- Atomic Agents (BrainBlend-AI / Eigenwise)
- Microsoft AutoGen — maintenance mode, redirects to Microsoft Agent Framework
- A2A Protocol v1.0 (Linux Foundation / Agentic AI Foundation, Aug 2026)
- Temporal Python SDK (`temporalio`)
- Langfuse v4.15.1 (Aug 2026) — MIT SDK, rewritten March 2026
- MCP — Linux Foundation / Anthropic

---

*Document maintained alongside `loopy-agent` releases. Update the score table in §3 when adding new modules.*