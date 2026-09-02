# API reference

`loopy-agent` exposes 21 modules. Every public symbol is exported
from the top-level `loopy` package.

## Top-level exports

```python
from loopy import (
    # Agentic loop
    AgentLoop, LoopConfig, StepResult, StepStatus,
    # Gateway + TestModel + structured outputs
    Gateway, GatewayResponse, ModelProvider, ProviderConfig,
    TestModel, TEST_MODEL_SENTINEL, ConnectionPool,
    # Guardrails + safety
    GuardrailPipeline, InputFilter, OutputFilter, FilterAction,
    SafetyGate, SafetyCheck, SafetyResult, EscalationReason,
    # Evals
    EvalSuite, EvalCase, EvalResult, EvalReport,
    Evaluator, EvalGate, EvalGateResult, EvalGateType,
    JudgeConfig, Verdict,
    # Cache
    LLMCache, CacheStats,
    # Observability + Redactor
    Tracer, Span, SpanStatus, MetricsCollector,
    Redactor, RedactionMatch,
    # MCP
    MCPClient, MCPToolResult, LocalMCP, MCPTool,
    # Multi-agent
    Orchestrator, Router, TaskDecomposer,
    # Middleware
    Pipeline, RetryMiddleware, CircuitBreakerMiddleware,
    FallbackMiddleware, CacheMiddleware, LoggingMiddleware,
    TimingMiddleware, ValidationMiddleware, RateLimitMiddleware,
    # Plugins
    PluginRegistry, PluginLoader, Plugin, PluginInfo,
    # State
    StateManager, LoopState, RunRecord, RunOutcome,
    # Cost / drift
    CostTracker, CostReport, BudgetExceeded,
    DriftDetector, DriftIssue, DriftReport,
    # Skills + A2A
    Skill, SkillRegistry,
    # Verification + audit
    Verifier, AssertionResult,
    AuditReport, CheckItem, ReadinessLevel,
    # Streaming
    StreamBuffer, StreamEvent, StreamChunk,
    # Multi-modal + Realtime
    MultiModalMessage, MultiModalBuilder, MediaContent, MediaType,
    ImageFormat,
    RealtimeSession, RealtimeEvent, RealtimeEventType, RealtimeTransport,
    # Compliance
    ComplianceChecker, AuditLogger,
    # Explainability
    DecisionTracker, DecisionTrace, DecisionStep, DecisionType,
    # Patterns
    PatternRegistry, LoopPattern, PatternCadence, RiskLevel,
)
```

## Module-by-module

| Module | What it does |
|---|---|
| `loopy.loop` | Agentic loop engine |
| `loopy.gateway` | Multi-provider LLM gateway |
| `loopy.guardrails` | PII / jailbreak filters |
| `loopy.evals` | Eval suites + gates + JSON I/O |
| `loopy.cache` | Semantic token cache |
| `loopy.observe` | Tracing + Redactor |
| `loopy.mcp` | MCP client |
| `loopy.agents` | Multi-agent orchestrator |
| `loopy.middleware` | Pipeline + retry/circuit-breaker |
| `loopy.plugins` | Plugin registry |
| `loopy.state` | State persistence |
| `loopy.safety` | Safety gate |
| `loopy.cost` | Cost tracking |
| `loopy.drift` | Drift detection |
| `loopy.skills` | Skill registry + A2A |
| `loopy.verification` | Maker/checker |
| `loopy.audit` | Readiness scoring |
| `loopy.streaming` | Token streaming |
| `loopy.multimodal` | Image/audio + Realtime |
| `loopy.compliance` | SOC2/GDPR/EU-AI-Act |
| `loopy.explainability` | Decision traces |