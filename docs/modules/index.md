# All modules

Quick reference for every module in `loopy-agent`.

| Module | What it does |
|---|---|
| [`loopy.loop`](loop.md) | The agentic loop engine — Plan → Act → Observe → Reflect |
| [`loopy.gateway`](gateway.md) | Multi-provider LLM gateway + TestModel + structured outputs |
| [`loopy.guardrails`](../api/index.md#loopy.guardrails) | PII and jailbreak input/output filters |
| [`loopy.evals`](../api/index.md#loopy.evals) | Eval suites, gates, JSON I/O for CI |
| [`loopy.cache`](../api/index.md#loopy.cache) | Semantic token cache with async disk persistence |
| [`loopy.observe`](../api/index.md#loopy.observe) | Tracing, metrics, PII Redactor |
| [`loopy.mcp`](../api/index.md#loopy.mcp) | MCP client with capability gates + SSRF guard |
| [`loopy.agents`](../api/index.md#loopy.agents) | Multi-agent orchestrator, router, task decomposer |
| [`loopy.middleware`](../api/index.md#loopy.middleware) | Pipeline of retry, circuit-breaker, fallback, cache |
| [`loopy.plugins`](../api/index.md#loopy.plugins) | Plugin registry, loader, marketplace |
| [`loopy.state`](../api/index.md#loopy.state) | StateManager, LoopState, RunRecord, resume tokens |
| [`loopy.safety`](../api/index.md#loopy.safety) | SafetyGate, escalations, path checks |
| [`loopy.cost`](../api/index.md#loopy.cost) | CostTracker, budget enforcement, reports |
| [`loopy.drift`](../api/index.md#loopy.drift) | DriftDetector, DriftIssue, DriftReport |
| [`loopy.skills`](../api/index.md#loopy.skills) | Skill registry, ranked matching, A2A interop |
| [`loopy.verification`](../api/index.md#loopy.verification) | Maker/checker pattern, assertions |
| [`loopy.audit`](../api/index.md#loopy.audit) | Readiness scoring, audit reports |
| [`loopy.streaming`](../api/index.md#loopy.streaming) | Token streaming + buffer |
| [`loopy.multimodal`](multimodal.md) | Image/audio + RealtimeSession (voice) |
| [`loopy.compliance`](../api/index.md#loopy.compliance) | SOC2 / GDPR / EU-AI-Act checks |
| [`loopy.explainability`](../api/index.md#loopy.explainability) | Decision traces + replays |