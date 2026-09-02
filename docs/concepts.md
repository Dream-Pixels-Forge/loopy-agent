# Concepts — the 21 modules

`loopy-agent` ships **21 modules**, each implementing one essential AI
concept. Every module is **opt-in** — use what you need, ignore the rest.

The core package depends on **just `httpx` + `pydantic`**; optional
extras cover gateway retries, caching, guardrails, observability, and
voice/realtime.

## At a glance

| # | Module | Concept | Public surface |
|---|---|---|---|
| 1 | `loopy.loop` | **Agentic loop** | `AgentLoop`, `LoopConfig`, `StepResult` |
| 2 | `loopy.gateway` | **LLM gateway + TestModel + StructuredOutput** | `Gateway`, `TestModel`, `GatewayResponse` |
| 3 | `loopy.guardrails` | **PII / jailbreak filters** | `GuardrailPipeline`, `InputFilter`, `OutputFilter` |
| 4 | `loopy.evals` | **Eval suites + EvalGate + JSON I/O** | `EvalSuite`, `EvalGate`, `EvalReport` |
| 5 | `loopy.cache` | **Semantic token cache (async I/O)** | `LLMCache`, `CacheStats` |
| 6 | `loopy.observe` | **Tracing + metrics + Redactor** | `Tracer`, `Redactor`, `TraceExporter` |
| 7 | `loopy.mcp` | **MCP client + capability gates** | `MCPClient`, `MCPToolResult` |
| 8 | `loopy.agents` | **Multi-agent orchestrator + router** | `Orchestrator`, `Router`, `TaskDecomposer` |
| 9 | `loopy.middleware` | **Pipeline + retry / circuit-breaker / cache** | `Pipeline`, `RetryMiddleware` |
| 10 | `loopy.plugins` | **Plugin system** | `PluginRegistry`, `PluginLoader` |
| 11 | `loopy.state` | **State persistence + resume** | `StateManager`, `LoopState`, `RunRecord` |
| 12 | `loopy.safety` | **Safety gate (paths, escalations)** | `SafetyGate`, `SafetyCheck` |
| 13 | `loopy.cost` | **Cost tracking + budget** | `CostTracker`, `CostReport`, `BudgetExceeded` |
| 14 | `loopy.drift` | **Drift detection** | `DriftDetector`, `DriftIssue`, `DriftReport` |
| 15 | `loopy.skills` | **Skill registry + ranked matching + A2A interop** | `SkillRegistry`, `Skill` |
| 16 | `loopy.verification` | **Maker/checker + assertions** | `Verifier`, `AssertionResult` |
| 17 | `loopy.audit` | **Readiness scoring + audit report** | `AuditReport`, `ReadinessLevel` |
| 18 | `loopy.streaming` | **Token streaming + buffering** | `StreamBuffer`, `StreamEvent` |
| 19 | `loopy.multimodal` | **Image/audio + RealtimeSession (voice)** | `MultiModalBuilder`, `RealtimeSession` |
| 20 | `loopy.compliance` | **SOC2 / GDPR / EU-AI-Act checks** | `ComplianceChecker`, `AuditLogger` |
| 21 | `loopy.explainability` | **Decision traces + replays** | `DecisionTracker`, `DecisionTrace` |

## What you build with them

The headline 0.7.9 trio that makes loopy uniquely competitive:

1. **TestModel** — `loopy.gateway.TestModel` — zero-network LLM for unit tests
2. **StructuredOutput** — `Gateway.chat(response_format=...)` — pydantic-validated outputs
3. **Redactor** — `Tracer(redactor=Redactor())` — PII/secret scrubbing for traces

Combined, these three are **the unique compliance-grade story** that
no other Python agent SDK ships.

## Install just what you need

```bash
pip install loopy-agent              # core: gateway, eval, skills, observe, etc.
pip install loopy-agent[cache]      # adds diskcache for LLMCache persistence
pip install loopy-agent[guardrails] # adds regex for PII filters
pip install loopy-agent[voice]      # adds websockets for RealtimeSession
pip install loopy-agent[all]        # everything
```

The extras are **never required for the core to work** — they unlock
the persistent cache, faster PII regex matching, or the WebSocket
transport for RealtimeSession.

## Where to go next

- **Build an agent**: [Getting started](getting-started.md)
- **Plug in a model**: see [Gateway](modules/gateway.md)
- **Connect tools**: see [MCP](modules/mcp.md)
- **Evaluate and observe**: see [Skills](modules/skills.md), [Audit](modules/audit.md), [Compliance](modules/audit.md)
- **Ship to production**: see [Research](research/competitive-analysis-2026.md) for the gap analysis that drives our roadmap