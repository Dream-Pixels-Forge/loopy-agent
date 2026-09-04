<p align="center">
  <img src="assets/banner.png" alt="Loopy Agent - Agentic AI Framework" width="100%">
</p>

<h1 align="center">🔄 Loopy</h1>

<p align="center">
  <strong>21 Essential AI Concepts in One Toolkit</strong><br>
  <em>Plan → Act → Observe → Reflect — an intelligent agent that thinks, loops, and achieves.</em>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-the-21-concepts">Concepts</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-installation">Install</a> •
  <a href="#-cli-usage">CLI</a>
</p>

<p align="center">
  <img src="https://img.shields.io/pypi/v/loopy-agent?color=orange&label=pypi" alt="PyPI">
  <img src="https://img.shields.io/pypi/pyversions/loopy-agent" alt="Python">
  <img src="https://img.shields.io/pypi/l/loopy-agent" alt="License">
  <img src="https://github.com/Dream-Pixels-Forge/loopy-agent/actions/workflows/ci.yml/badge.svg" alt="CI">
</p>

---

<p align="center">
  <strong>Loopy</strong> is a lightweight, modular Python SDK for building production-ready agentic AI applications. It bundles twenty-one battle-tested concepts — agentic loops, multi-provider gateways, guardrails, evals, caching, observability, MCP integration, multi-agent orchestration, middleware, plugins, state management, safety gates, cost tracking, drift detection, skills, verification, audit scoring, streaming, multi-modal, compliance, and explainability — into a single install with zero heavy dependencies.
</p>

<p align="center">
  <code>pip install loopy-agent</code>&nbsp;&nbsp;or&nbsp;&nbsp;<code>pip install loopy-agent[all]</code>
</p>

---

## 🎯 The 21 Concepts

| Module | Concept | Description |
|--------|---------|-------------|
| `loop` | **Agentic Loops** | Plan → Act → Observe → Reflect cycle |
| `gateway` | **AI Gateway** | One control plane, many providers |
| `guardrails` | **Guardrails** | PII detection, jailbreak filtering |
| `evals` | **Evals** | Judge-based model evaluation |
| `cache` | **Inference Economics** | Semantic token caching |
| `observe` | **Observability** | Traces, logs, metrics |
| `mcp` | **MCP** | Model Context Protocol client |
| `agents` | **Multi-Agent** | Orchestrator + subagents |
| `middleware` | **Middleware** | Composable request/response hooks |
| `plugins` | **Plugin System** | Extend with custom plugins |
| `state` | **State Management** | Durable loop state persistence |
| `safety` | **Safety Gates** | Denylist paths, escalation triggers |
| `cost` | **Cost Tracking** | Token budgets and cost reporting |
| `drift` | **Drift Detection** | Config/state drift monitoring |
| `skills` | **Skills** | Persistent agent knowledge (SKILL.md) |
| `verification` | **Verification** | Maker/Checker pattern |
| `audit` | **Audit Scoring** | Loop readiness score (L0-L3) |
| `streaming` | **Streaming** | Real-time token-by-token output |
| `multimodal` | **Multi-modal** | Image, audio, video support |
| `compliance` | **Compliance** | SOC2, GDPR, EU AI Act checks |
| `explainability` | **Explainability** | Decision audit trail |

---

## 🚀 What's New

### v1.1.1 — "Try It More" (every error has a docs link)

- **100% error-message audit pass rate** — every public
  `raise` site in `loopy/` now carries a
  `loopy.dev/docs/...#anchor` URL with what-went-wrong and
  how-to-fix guidance. v1.1.0 shipped 12 hand-pinned exception
  messages at ~27% pass rate; v1.1.1 closes the gap to 100%
  via the new `scripts/patch_bulk.py` helper.
- **`scripts/patch_bulk.py`** — a small Python helper that
  reads `dev-notes/ERROR_AUDIT.json`, finds each `needs_work`
  raise site, and appends the docs URL while preserving the
  existing source layout (handles single-line, multi-line,
  and docstring-adjacent raise messages without corrupting them).
- `tests/test_error_messages.py::TestErrorAuditThreshold` is
  no longer `xfail`; it now passes.

### v1.1.0 — "Try It Now" (adoptability)

- **`loopy init <name>`** — one-command project bootstrap.
  Scaffolds a self-contained project directory with
  `pyproject.toml` (pinning `loopy-agent[all]>=1.0.0`), `agent.py`
  (TestModel-backed, no API key required), `loopy.yml`,
  `.gitignore`, `README.md`, and `tests/test_agent.py`. Supports
  `--no-test` to skip the test file. Refuses path-traversal,
  absolute paths, empty names, and non-empty existing
  directories.
- **10 recipes in `examples/`** — single-file, <100 lines each,
  no API key required, all runnable with
  `python examples/0X_name.py`. Covers: hello world, streaming,
  cost-cap, policies, durable, verified, federation, hitl,
  redaction, otel. See `examples/README.md` for the index.
- **Error-message audit infrastructure** — `scripts/audit_errors.py`
  walks `loopy/`, classifies every `raise` site as `passes` (has
  a `loopy.dev/docs/...#anchor` URL) or `needs_work`, and writes
  `dev-notes/ERROR_AUDIT.json`. 12 of the most-touched public
  exceptions are now hand-pinned (LoopConfig, Step, DAG,
  ResumeToken, FederatedServer, Policy, validate_outbound_url).
  Bulk pass rate is the goal of v1.1.1.
- **Stricter input validation** — `LoopConfig(max_steps<1)` is
  now universally rejected (the loop never runs anything);
  `FederatedServer.__init__` validates `port` is an `int` in
  `[0, 65535]` and fails fast.

### v1.0.0 — Production-Grade by Default (durable runtime + verified agents + federated HTTP)

- **`loopy.durable.DAG` / `Step` / `Workflow`** — declarative
  workflow graph with Saga compensation. When a step raises,
  every earlier step's `compensation` callable runs in reverse
  order so partial side effects can be rolled back. `Workflow.run`
  writes a crash-safe on-disk journal; `Workflow.resume(token)`
  picks up at the last completed step on a different process.
  `ResumeToken` round-trips through pickle + JSON.
- **`Workflow.test_env()`** returns a `TestEnv` with a virtual
  clock — `await env.sleep(days=7)` advances the clock
  604800s in well under 1s of real time. Two envs are
  independent; the clock persists to disk.
- **`VerifiedAgent(agent, spec).verify(n_cases=100)`** — drive
  the agent on a batch of inputs (default deterministic;
  Hypothesis-driven with `pip install loopy-agent[hypothesis]`)
  and return a `VerificationReport`. Built-in invariant
  factories: `output_must_contain`, `output_length_at_most`.
  Empty specs are rejected at construction.
- **`FederatedServer` + `AgentCluster`** — minimal HTTP server
  (`GET /.well-known/agent-card.json`, `POST /tasks`, `GET
  /tasks/{id}`) on the stdlib `ThreadingHTTPServer` so the core
  stays zero-deps. `AgentCluster(peers)` discovers and hands
  off tasks peer-to-peer; unreachable peers are silently
  skipped.
- **`python -m loopy serve --port N --agent path.py`** — start
  the federated server from a single Python agent module.
- **T3.4.1** — `Development Status :: 3 - Alpha` promoted to
  `Development Status :: 5 - Production/Stable`.
- **T3.4.2** — release pipeline now produces a CycloneDX SBOM
  and Cosign-signs it keylessly (OIDC / Sigstore Fulcio). SBOM,
  signature, and certificate are all attached to the GitHub
  Release so downstream consumers can audit + verify.

### v0.9.0 — Trust Layer (A2A handoff, Compliance-as-Code, cost-aware routing)

- **`A2AClient.fetch_agent_card(url)`** — parse an A2A v1.0
  `/.well-known/agent-card.json` document with SSRF protection
  and a TTL cache. `A2AClient.from_agent_card(card)` builds a
  client from a single card; rejects unsupported authentication
  methods. **`A2ATask`** carries the 7-state lifecycle
  (`submitted` → `working` → `input-required` / `completed` /
  `failed` / `canceled` / `rejected`); `create_task`, `get_task`,
  `cancel_task`, SSE `stream_task`, and HMAC-verified
  `verify_webhook` round out the surface.
- **`loopy.policies` Compliance-as-Code** — `Policy`,
  `Condition` (`max_retries` / `max_cost_usd` / `pii_in_input` /
  `rate_limit`), `PolicyEngine`, `PolicyDecision`, `PolicyViolation`.
  Wire the engine into `Gateway(policy_engine=...)` or
  `LoopConfig(policy_engine=...)` and every chat / step is gated
  *before* any side effect. The audit log keeps the raw context so
  violations are provable.
- **`Gateway.chat(..., max_cost_usd=X)` cost-aware routing** —
  every `ProviderConfig` carries a `cost_per_1k_tokens` field so
  the gateway can rank providers by cost. When the requested
  provider would exceed the cap, the gateway falls back to the
  cheapest configured provider that fits; if none fit,
  `BudgetExceeded` fires *before* any HTTP. `CostTracker` records
  the estimated / actual USD and the savings from the fallback
  (`estimated_usd` / `actual_usd` / `savings_usd` on `CostReport`).

### v0.8.0 — Agent Control Plane (graph control flow, HITL, OTel)

- **`AgentLoop` human-in-the-loop interrupts** — `LoopConfig.interrupt_before`
  / `interrupt_after` pause any of `plan / actor / observer / reflector`
  before or after it runs. `run()` returns an `Interrupt` carrying the
  proposed action and a `when` context. Resume with
  `Interrupt(decision="approve")` or raise `AgentLoopRejected` on
  `"reject"`. Approved before-gates re-enter the same step so the
  after-gate still fires. Pending interrupts persist via `StateManager`
  as `RunRecord(outcome=INTERRUPTED)` for crash+resume replay.
- **`loopy.flow` graph control flow** — typed, persistent,
  checkpointable `Node` / `Edge` / `StateGraph` / `Workflow`
  primitives that integrate with `StateManager`, `Tracer`, `Redactor`,
  and `SkillRegistry`. A uniquely scrub-aware, skill-aware graph.
- **OpenTelemetry auto-instrumentation** — `@observe()` decorator
  (sync + async) wraps any function in a span; `auto_instrument_gateway()`
  and `auto_instrument_mcp()` monkey-patch `Gateway.chat` and
  `MCPClient.call_tool` with one import. `build_otlp_envelope(spans)`
  returns the OTLP `ExportTraceServiceRequest` JSON shape. `Tracer.disabled`
  and `Tracer.shutdown()` give a clean no-op for tests and tear-down.
- **`RunOutcome.INTERRUPTED`** — new enum value for HITL-paused runs.

### v0.7.7 — Async I/O & Broadcast Safety

- **`MemoryStore` non-blocking I/O** — `add()`, `delete()`, `clear()` now run file writes in a worker thread via `asyncio.to_thread`
- **`A2AClient.broadcast` amplification guard** — `max_depth=3` default + per-call cycle detection prevents infinite broadcast loops
- **CI ruff E402 fix** — reverted import structure to single try/except block for clean lint

### v0.7.6 — Compliance, Drift & Observability Fixes

- **`ComplianceChecker` sync methods** — removed fake `async` from methods with zero `await` calls
- **`DecisionTracker` bounded memory** — `max_traces=100` with FIFO eviction prevents OOM in long sessions
- **`DriftDetector` real tracking** — dead-code callback check replaced with actual drift issue logging
- **`MemoryStore` dirty flag** — disk writes only on structural mutations, not every access
- **`TraceExporter.export_http` retry** — configurable `max_retries` with exponential backoff (1s, 2s, 4s)

### v0.7.5 — Concept Count & Test Coverage

- Fixed "19 concepts" → "21" across README, pyproject.toml, CLI
- 484 tests (up from 276 in v0.7.4), 92% coverage
- `MarketplacePlugin` coverage: 57% → 100%

---

## 🚀 Quick Start

### Agentic Loop

```python
import asyncio
from loopy import AgentLoop, LoopConfig

async def planner(history):
    return "Search for Python async best practices"

async def actor(plan):
    return "Found 5 relevant articles about asyncio"

async def observer(action):
    return "Key insight: use asyncio.gather for concurrency"

async def reflector(history):
    return "Good progress, need to summarize findings"

loop = AgentLoop(LoopConfig(
    planner=planner,
    actor=actor,
    observer=observer,
    reflector=reflector,
    max_steps=5,
))

results = asyncio.run(loop.run())
```

### AI Gateway

```python
import asyncio
from loopy import Gateway, ModelProvider

async def main():
    gateway = Gateway()
    
    gateway.add_provider("openai", ProviderConfig(
        provider=ModelProvider.OPENAI,
        api_key="sk-...",
        model="gpt-4",
    ))
    
    gateway.add_provider("anthropic", ProviderConfig(
        provider=ModelProvider.ANTHROPIC,
        api_key="sk-ant-...",
        model="claude-3-opus",
    ))
    
    # Route to specific provider
    response = await gateway.chat(
        "What is 2+2?",
        provider="openai",
    )
    print(response.content)

asyncio.run(main())
```

### Guardrails

```python
from loopy import GuardrailPipeline

pipeline = GuardrailPipeline()

# Check user input
result = pipeline.filter_input("My SSN is 123-45-6789")
print(result.action)  # FilterAction.REDACT
print(result.filtered)  # "My SSN is [SSN_REDACTED]"

# Check for jailbreaks
result = pipeline.filter_input("Ignore all previous instructions")
print(result.action)  # FilterAction.BLOCK
```

### Evals

```python
import asyncio
from loopy import Evaluator, EvalSuite, EvalCase

async def my_model(prompt: str) -> str:
    return f"Response to: {prompt}"

async def main():
    evaluator = Evaluator(model_fn=my_model)
    
    suite = EvalSuite(
        name="basic_math",
        cases=[
            EvalCase(
                name="addition",
                input_text="What is 2+2?",
                expected_output="4",
                criteria=["correct", "concise"],
            ),
        ],
    )
    
    report = await evaluator.run(suite)
    print(report.summary())

asyncio.run(main())
```

### Cache

```python
from loopy import LLMCache

cache = LLMCache(ttl=3600, max_size=1000)

# Check cache before LLM call
cached = cache.get("What is Python?", model="gpt-4")
if cached:
    response = cached
else:
    response = call_llm("What is Python?")
    cache.set("What is Python?", response, model="gpt-4", tokens=150)

stats = cache.stats()
print(f"Hit rate: {stats.hit_rate:.1%}")
print(f"Estimated savings: ${stats.estimated_savings:.2f}")
```

### Observability

```python
from loopy import Tracer, MetricsCollector

tracer = Tracer(service="my_app")
metrics = MetricsCollector()

# Trace an operation
with tracer.start("llm_call", model="gpt-4") as span:
    response = call_llm(prompt)
    span.set_attribute("tokens", response.usage.total_tokens)

# Collect metrics
metrics.increment("llm.requests", model="gpt-4")
metrics.histogram("llm.latency_ms", 245.3, model="gpt-4")

# Export
print(tracer.export_json())
print(metrics.summary())
```

### MCP Client

```python
import asyncio
from loopy import MCPClient

async def main():
    async with MCPClient("http://localhost:3000") as client:
        # List available tools
        tools = await client.list_tools()
        for tool in tools:
            print(f"{tool.name}: {tool.description}")
        
        # Call a tool
        result = await client.call_tool("get_weather", {"city": "Portland"})
        print(result.content)

asyncio.run(main())
```

### Multi-Agent

```python
import asyncio
from loopy import Orchestrator, SubAgent

async def researcher(task, context):
    return f"Research results for: {task}"

async def coder(task, context):
    return f"Code implementation for: {task}"

async def main():
    orchestrator = Orchestrator()
    
    orchestrator.add_agent(SubAgent(
        name="researcher",
        description="Searches the web",
        handler=researcher,
    ))
    
    orchestrator.add_agent(SubAgent(
        name="coder",
        description="Writes code",
        handler=coder,
    ))
    
    # Run on specific agent
    result = await orchestrator.run(
        "Build a REST API",
        agent_name="coder",
    )
    print(result.output)
    
    # Run on all agents
    results = await orchestrator.run_all("Analyze this dataset")
    for r in results:
        print(f"{r.agent_name}: {r.output[:50]}...")

asyncio.run(main())
```

---

## 🔧 Middleware

Composable request/response interceptors.

```python
import asyncio
from loopy import (
    MiddlewarePipeline,
    LoggingMiddleware,
    TimingMiddleware,
    RateLimitMiddleware,
    ValidationMiddleware,
    FunctionMiddleware,
)

# Create pipeline with built-in middleware
pipeline = MiddlewarePipeline()
pipeline.add(LoggingMiddleware())
pipeline.add(TimingMiddleware())
pipeline.add(RateLimitMiddleware(max_per_second=10))
pipeline.add(ValidationMiddleware(required_fields=["message"]))

# Add custom middleware
async def auth_middleware(ctx):
    if not ctx.data.get("api_key"):
        ctx.cancel("Missing API key")
    return ctx

pipeline.add(FunctionMiddleware(name="auth", before_fn=auth_middleware))

# Execute through pipeline
async def my_handler(data, **kwargs):
    return f"Processed: {data['message']}"

result = await pipeline.execute(
    operation="llm.chat",
    handler=my_handler,
    data={"message": "Hello", "api_key": "sk-..."},
)
```

### Built-in Middleware

| Middleware | Purpose |
|------------|---------|
| `LoggingMiddleware` | Logs all operations |
| `TimingMiddleware` | Tracks operation timing |
| `RateLimitMiddleware` | Rate limiting |
| `CacheMiddleware` | Response caching |
| `ValidationMiddleware` | Input validation |

---

## 🔌 Plugin System

Extend loopy with custom plugins.

```python
import asyncio
from loopy import Plugin, PluginRegistry, PluginInfo

# Create a plugin
class MyPlugin(Plugin):
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="my-plugin",
            version="1.0.0",
            description="My awesome plugin",
            author="Me",
            url="https://github.com/me/my-plugin",
            capabilities=["tool", "middleware"],
            requires=[],
        )
    
    async def setup(self, registry: PluginRegistry) -> None:
        # Register tools
        registry.register_tool("my_tool", my_tool_handler)
        
        # Register middleware
        registry.register_middleware("my_middleware", my_middleware)
        
        # Register extension hooks
        registry.register_extension("on_before_chat", my_hook)

# Use the plugin
async def main():
    registry = PluginRegistry()
    await registry.load(MyPlugin())
    
    # List loaded plugins
    for plugin_info in registry.list_plugins():
        print(f"Loaded: {plugin_info.name} v{plugin_info.version}")

asyncio.run(main())
```

### Plugin Discovery

```python
from loopy import PluginLoader

loader = PluginLoader()

# Discover from package
await loader.discover(package="my_package.plugins")

# Discover from directory
await loader.discover(directory="~/.loopy/plugins")
```

---

## 📝 Type Stubs

Loopy includes complete type stubs for IDE autocompletion:

```python
from loopy import Gateway, ModelProvider, GatewayResponse

# Your IDE will provide full autocompletion
gateway = Gateway()
gateway.add_provider(...)  # IDE shows all parameters
response: GatewayResponse = await gateway.chat(...)  # IDE knows return type
```

The `py.typed` marker file ensures type checkers (mypy, pyright) recognize loopy as typed.

---

## 🧪 Evaluator-Optimizer Pattern

The 2026 agentic workflow evaluator-optimizer pattern uses LLM-as-judge to evaluate outputs.

```python
import asyncio
from loopy import EvalGate, EvalGateType, JudgeConfig

async def my_llm_judge(prompt: str) -> str:
    # Call your LLM to judge the output
    return '{"score": 0.85, "pass": true, "feedback": "Good quality"}'

# Create an evaluation gate
gate = EvalGate(
    gate_type=EvalGateType.JUDGE,
    config=JudgeConfig(
        criteria=["correct", "concise", "helpful"],
        threshold=0.7,
    ),
    judge_fn=my_llm_judge,
)

async def main():
    result = await gate.evaluate(
        input_text="What is Python?",
        output="Python is a programming language known for its simplicity.",
    )
    
    print(f"Passed: {result.passed}")
    print(f"Score: {result.score}")
    print(f"Feedback: {result.feedback}")

asyncio.run(main())
```

---

## 🎯 Orchestrator-Workers Pattern

Route tasks to specialist agents and decompose complex tasks.

```python
import asyncio
from loopy import Orchestrator, SubAgent, Router, RoutingRule, TaskDecomposer

async def researcher(task, context):
    return f"Research results for: {task}"

async def coder(task, context):
    return f"Code implementation for: {task}"

async def main():
    # Create router
    router = Router()
    router.add_rule(RoutingRule(
        pattern=r"research|search|find",
        agent_name="researcher",
        priority=1,
    ))
    router.add_rule(RoutingRule(
        pattern=r"code|implement|build",
        agent_name="coder",
        priority=2,
    ))
    
    # Create orchestrator with routing
    orchestrator = Orchestrator(router=router)
    
    orchestrator.add_agent(SubAgent(
        name="researcher",
        description="Searches the web",
        handler=researcher,
    ))
    
    orchestrator.add_agent(SubAgent(
        name="coder",
        description="Writes code",
        handler=coder,
    ))
    
    # Route task automatically
    agent_name = await orchestrator.route("Research Python async patterns")
    print(f"Routed to: {agent_name}")
    
    # Run with routing
    result = await orchestrator.run("Build a REST API")
    print(result.output)
    
    # Decompose and run
    subtasks = await orchestrator.decompose("Build REST API with tests")
    results = await orchestrator.run_decomposed("Build REST API with tests")
    for r in results:
        print(f"{r.agent_name}: {r.output[:50]}...")

asyncio.run(main())
```

---

## 🔌 Async Gateway with Connection Pooling

```python
import asyncio
from loopy import Gateway, ProviderConfig, ModelProvider

async def main():
    # Async context manager - connections auto-closed
    async with Gateway() as gateway:
        gateway.add_provider("openai", ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="sk-...",
            model="gpt-4",
        ))
        
        # Connections are pooled automatically
        response = await gateway.chat("Hello!", provider="openai")
        print(response.content)
        
        # Check pool stats
        print(gateway._pool.stats())

asyncio.run(main())
```

---

## 🛡️ Middleware: Retry, Circuit Breaker & Fallback

```python
import asyncio
from loopy import (
    MiddlewarePipeline,
    RetryMiddleware,
    CircuitBreakerMiddleware,
    FallbackMiddleware,
    LoggingMiddleware,
)

async def main():
    pipeline = MiddlewarePipeline()
    
    # Auto-retry with exponential backoff
    pipeline.add(RetryMiddleware(
        max_retries=3,
        base_delay=1.0,
    ))
    
    # Circuit breaker to prevent cascade failures
    pipeline.add(CircuitBreakerMiddleware(
        failure_threshold=5,
        recovery_timeout=60.0,
    ))
    
    # Provider failover
    pipeline.add(FallbackMiddleware(
        fallback_fn=lambda ctx, err: "Fallback response",
    ))
    
    pipeline.add(LoggingMiddleware())
    
    # Execute through pipeline
    async def my_handler(data, **kwargs):
        return f"Processed: {data['message']}"
    
    result = await pipeline.execute(
        operation="llm.chat",
        handler=my_handler,
        data={"message": "Hello"},
    )
    print(result)

asyncio.run(main())
```

---

## 🔌 First-Party Plugins

### RAG Plugin — Retrieval-Augmented Generation

```python
import asyncio
from loopy.plugins.rag import RAGPlugin, Retriever, Document

async def main():
    retriever = Retriever()
    
    # Add documents
    retriever.add(Document.from_text("Python is a programming language"))
    retriever.add(Document.from_text("JavaScript is used for web development"))
    
    # Search
    results = await retriever.search("programming", top_k=5)
    for r in results:
        print(f"{r.score:.3f}: {r.document.content[:50]}")

asyncio.run(main())
```

### Tools Plugin — Function Calling

```python
import asyncio
from loopy.plugins.tools import ToolsPlugin, Tool, ToolParameter

async def calculate(expression: str) -> dict:
    return {"result": eval(expression)}

# Create tool registry
plugin = ToolsPlugin()
await plugin.setup(None)  # or load via registry

# Register custom tool
plugin.tool_registry.register(Tool(
    name="calculate",
    description="Evaluate math expression",
    handler=calculate,
    parameters=[
        ToolParameter(name="expression", type="string"),
    ],
))

async def main():
    result = await plugin.tool_registry.execute(
        "calculate",
        {"expression": "2 + 2"}
    )
    print(result.output)  # {"result": 4}

asyncio.run(main())
```

### Memory Plugin — Long-term Memory

```python
import asyncio
from loopy.plugins.memory import MemoryPlugin, MemoryStore, Memory

# Create persistent memory store
store = MemoryStore(storage_path="./agent_memory.json")

# Store memories
store.add(Memory(
    id="user_pref_1",
    content="User prefers concise responses",
    category="preferences",
    importance=0.8,
))

# Recall memories
memories = store.recall("response style", top_k=5)
for m in memories:
    print(f"{m.importance:.1f}: {m.content}")

asyncio.run(main())
```

---

## 📡 OpenTelemetry Export

```python
import asyncio
from loopy import Tracer, TraceExporter

async def main():
    tracer = Tracer(service="my_app")
    
    # Trace some operations
    with tracer.start("llm_call") as span:
        span.set_attribute("model", "gpt-4")
        # ... do work ...
    
    # Export to various backends
    exporter = TraceExporter(tracer)
    
    # Export to file
    exporter.export_file("traces.json")
    
    # Export to stdout
    exporter.export_stdout()
    
    # Export to Jaeger/Zipkin
    await exporter.export_http("http://localhost:14268/api/traces")

asyncio.run(main())
```

---

## 📦 Installation

```bash
# Core (minimal)
pip install loopy-agent

# With optional features
pip install loopy-agent[gateway]    # tenacity for retry logic
pip install loopy-agent[cache]      # diskcache for persistence
pip install loopy-agent[guardrails] # regex for advanced patterns
pip install loopy-agent[observe]    # rich for pretty output
pip install loopy-agent[all]        # everything

# Development
pip install loopy-agent[dev]
```

---

## 🏗️ Architecture

```
loopy/
├── __init__.py        # Public API exports (21 modules)
├── _version.py        # Canonical version (single source of truth)
├── _types.pyi         # Type stubs for IDE support
├── py.typed           # PEP 561 marker
├── loop.py            # Agentic loop engine (Plan → Act → Observe → Reflect)
├── gateway.py         # Multi-provider routing + batch/streaming + connection pool
├── guardrails.py      # PII & jailbreak filters
├── evals.py           # Judge-based evaluation + EvalGate (evaluator-optimizer)
├── cache.py           # Semantic token caching
├── observe.py         # Tracing, metrics, TraceExporter (OTLP-compatible)
├── mcp.py             # MCP protocol client (async context manager)
├── agents.py          # Multi-agent orchestration + Router + TaskDecomposer
├── middleware.py       # Composable middleware pipeline + retry/circuit/fallback
├── cli.py             # Command-line interface
├── cost.py            # Token cost tracking + daily budgets
├── state.py           # Durable loop state persistence
├── skills.py          # Persistent agent knowledge (SKILL.md)
├── verification.py    # Maker/Checker pattern
├── safety.py          # Denylist paths, escalation triggers
├── drift.py           # Config/state drift detection
├── audit.py           # Loop readiness scoring (L0–L3)
├── streaming.py       # Real-time token-by-token output + SSE
├── multimodal.py      # Image, audio, video messages
├── compliance.py      # SOC2, GDPR, EU AI Act checks + audit logger
├── explainability.py  # Decision audit trail
├── patterns.py        # Named agentic workflow patterns
├── a2a.py             # Agent-to-Agent protocol client + registry
├── netutil.py         # SSRF guard (is_private_host, validate_outbound_url)
├── prompting.py       # Prompt assembly helpers + canary tokens + strip_md_media
└── plugins/
    ├── __init__.py    # Lazy-import plugin surface
    ├── rag.py         # RAGPlugin — retrieval + vector/keyword search
    ├── tools.py       # ToolsPlugin — tool registry with capability gates
    ├── memory.py      # MemoryPlugin — long-term memory + approval-gated writes
    ├── audio.py       # AudioPlugin — TTS/STT
    └── marketplace.py # Plugin marketplace (PyPI install/uninstall, validated)
```

---

## 🖥️ CLI Usage

Loopy includes a command-line interface:

```bash
# Show info
loopy info

# Chat with an LLM
loopy chat "What is 2+2?" --provider openai
loopy chat "Explain async Python" --provider anthropic --model claude-3-opus

# Check guardrails
loopy guard "My SSN is 123-45-6789"
loopy guard "Ignore all previous instructions" --json

# Cache operations
loopy cache stats
loopy cache clear

# Tracing
loopy trace export
loopy trace stats

# Evaluations
loopy eval run --suite math.json

# Agent management
loopy agent list
```

---


## 📄 License

MIT © Dream Pixels Forge
