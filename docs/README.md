# 🔄 Loopy Documentation

**8 Essential AI Concepts in One Toolkit**

A modular Python SDK for building production-ready LLM applications.

[![PyPI version](https://badge.fury.io/py/loopy.svg)](https://pypi.org/project/loopy/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

---

## 📚 Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Core Concepts](#core-concepts)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Plugins](#plugins)
- [CLI Reference](#cli-reference)
- [Contributing](#contributing)

---

## 🚀 Quick Start

```python
import asyncio
from loopy import AgentLoop, LoopConfig

# Define your agent loop
async def planner(history):
    return "Search for Python best practices"

async def actor(plan):
    return "Found 5 relevant articles"

async def observer(action):
    return "Key insight: use asyncio.gather"

async def reflector(history):
    return "Good progress, need to summarize"

# Run the loop
loop = AgentLoop(LoopConfig(
    planner=planner,
    actor=actor,
    observer=observer,
    reflector=reflector,
    max_steps=5,
))

results = asyncio.run(loop.run())
```

---

## 📦 Installation

```bash
# Core (minimal)
pip install loopy

# With optional features
pip install loopy[gateway]    # tenacity for retry logic
pip install loopy[cache]      # diskcache for persistence
pip install loopy[guardrails] # regex for advanced patterns
pip install loopy[observe]    # rich for pretty output
pip install loopy[all]        # everything

# Development
pip install loopy[dev]
```

---

## 🎯 Core Concepts

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

---

## 📖 API Reference

### Agentic Loop

```python
from loopy import AgentLoop, LoopConfig, StepResult, StepStatus

class LoopConfig:
    max_steps: int = 10
    max_retries: int = 3
    stop_on_error: bool = False
    planner: Callable[[list[StepResult]], Awaitable[str]] | None
    actor: Callable[[str], Awaitable[str]] | None
    observer: Callable[[str], Awaitable[str]] | None
    reflector: Callable[[list[StepResult]], Awaitable[str]] | None
    should_stop: Callable[[list[StepResult]], Awaitable[bool]] | None

class AgentLoop:
    def __init__(self, config: LoopConfig)
    async def run(self, initial_context: str = "") -> list[StepResult]

class StepResult:
    step: int
    status: StepStatus
    plan: str
    action: str
    observation: str
    reflection: str
    data: dict[str, Any]
    error: str | None
```

### AI Gateway

```python
from loopy import Gateway, ModelProvider, ProviderConfig, GatewayResponse, ConnectionPool

class ProviderConfig:
    provider: ModelProvider
    api_key: str | None
    base_url: str
    model: str
    rpm: int  # requests per minute
    tpm: int  # tokens per minute

class Gateway:
    def __init__(self)
    async def __aenter__(self) -> Gateway
    async def __aexit__(self, *args) -> None
    def add_provider(self, name: str, config: ProviderConfig) -> None
    async def chat(
        self,
        message: str,
        provider: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> GatewayResponse
    async def chat_batch(
        self,
        messages: list[str],
        provider: str | None = None,
        max_concurrent: int = 5,
    ) -> list[GatewayResponse]
    async def chat_streaming(self, message: str, ...) -> AsyncGenerator[str]
    async def close(self) -> None

class GatewayResponse:
    content: str
    model: str
    provider: ModelProvider
    tokens_used: int
    latency_ms: float
    cached: bool

class ConnectionPool:
    def __init__(self, max_size: int = 10)
    async def get_connection(self, provider: str) -> httpx.AsyncClient
    async def close(self) -> None
    def stats(self) -> dict
```

### Guardrails

```python
from loopy import GuardrailPipeline, InputFilter, OutputFilter, FilterAction

class GuardrailPipeline:
    def __init__(self)
    def filter_input(self, text: str) -> FilterResult
    def filter_output(self, text: str) -> FilterResult
    def add_filter(self, filter: InputFilter | OutputFilter) -> None

class FilterResult:
    action: FilterAction  # ALLOW, BLOCK, REDACT
    filtered: str
    original: str
    reason: str

class FilterAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
```

### Evals (with Evaluator-Optimizer Pattern)

```python
from loopy import (
    Evaluator, EvalCase, EvalResult, EvalSuite, Verdict,
    EvalGate, EvalGateType, JudgeConfig, EvalGateResult,
)

class EvalGate:
    def __init__(
        self,
        gate_type: EvalGateType,
        config: JudgeConfig | None = None,
        judge_fn: Callable[[str], Awaitable[str]] | None = None,
    )
    async def evaluate(
        self,
        input_text: str,
        output: str,
        criteria: list[str] | None = None,
    ) -> EvalGateResult

class JudgeConfig:
    evaluator_model: str
    criteria: list[str]
    threshold: float  # 0.0 to 1.0
    prompt_template: str

class EvalGateResult:
    gate_type: EvalGateType
    passed: bool
    score: float
    feedback: str
    metadata: dict

class Evaluator:
    def __init__(
        self,
        judge_fn: Callable[[str], Awaitable[str]] | None = None,
        model_fn: Callable[[str], Awaitable[str]] | None = None,
    )
    async def run(self, suite: EvalSuite, model_fn: Callable | None = None) -> EvalReport
```

### Cache

```python
from loopy import LLMCache, CacheStats

class LLMCache:
    def __init__(self, ttl: int = 3600, max_size: int = 1000)
    def get(self, key: str, model: str = "") -> str | None
    def set(self, key: str, value: str, model: str = "", tokens: int = 0) -> None
    def delete(self, key: str) -> bool
    def clear(self) -> None
    def stats(self) -> CacheStats

class CacheStats:
    hits: int
    misses: int
    hit_rate: float
    estimated_savings: float
```

### Observability (with OpenTelemetry Export)

```python
from loopy import Tracer, Span, SpanStatus, MetricsCollector, TraceExporter

class Tracer:
    def __init__(self, service: str = "loopy")
    def start_span(self, name: str, **attributes) -> Span
    def start(self, name: str, **attributes) -> SpanContext
    def get_spans(self) -> list[Span]
    def export_json(self) -> str
    def export_otlp(self) -> list[dict]
    def export_opentelemetry(self) -> dict
    def clear(self) -> None

class TraceExporter:
    def __init__(self, tracer: Tracer)
    def export_file(self, path: str) -> None
    def export_stdout(self) -> str
    async def export_http(self, endpoint: str, timeout: float = 10.0) -> bool

class MetricsCollector:
    def increment(self, name: str, value: float = 1, **tags) -> None
    def histogram(self, name: str, value: float, **tags) -> None
    def gauge(self, name: str, value: float, **tags) -> None
    def summary(self) -> dict
    def export(self) -> list[dict]
```

### MCP Client

```python
from loopy import MCPClient, Tool, LocalMCP

class MCPClient:
    def __init__(self, server_url: str)
    async def list_tools(self) -> list[Tool]
    async def call_tool(self, name: str, arguments: dict) -> ToolResult
    async def close(self) -> None

class Tool:
    name: str
    description: str
    input_schema: dict
```

### Multi-Agent (with Orchestrator-Workers Pattern)

```python
from loopy import (
    Orchestrator, SubAgent, AgentResult, AgentStatus,
    Router, RoutingRule, TaskDecomposer, SubTask,
)

class Orchestrator:
    def __init__(self, max_concurrent: int = 5, router: Router | None = None)
    def add_agent(self, agent: SubAgent) -> None
    async def route(self, task: str) -> str
    async def decompose(self, task: str) -> list[SubTask]
    async def run(
        self,
        task: str,
        agent_name: str | None = None,
        context: dict | None = None,
    ) -> AgentResult
    async def run_all(self, task: str, context: dict | None = None) -> list[AgentResult]
    async def run_decomposed(self, task: str, context: dict | None = None) -> list[AgentResult]

class Router:
    def __init__(self, classify_fn: Callable | None = None)
    def add_rule(self, rule: RoutingRule) -> None
    async def classify(self, task: str) -> str

class TaskDecomposer:
    async def decompose(self, task: str) -> list[SubTask]

class SubTask:
    id: str
    description: str
    dependencies: list[str]
    required_agent: str | None
```

### Middleware

```python
from loopy import (
    Middleware, MiddlewarePipeline, MiddlewareContext,
    FunctionMiddleware, LoggingMiddleware, TimingMiddleware,
    RateLimitMiddleware, CacheMiddleware, ValidationMiddleware,
    RetryMiddleware, CircuitBreakerMiddleware, FallbackMiddleware,
)

class MiddlewarePipeline:
    def __init__(self)
    def add(self, middleware: Middleware) -> None
    def remove(self, name: str) -> bool
    async def execute(
        self,
        operation: str,
        handler: Callable,
        data: dict | None = None,
    ) -> Any

class RetryMiddleware:
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retryable_exceptions: tuple = (Exception,),
    )

class CircuitBreakerMiddleware:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    )

class FallbackMiddleware:
    def __init__(
        self,
        fallback_fn: Callable | None = None,
        fallback_data: dict | None = None,
    )
```

### Plugin System

```python
from loopy import Plugin, PluginRegistry, PluginLoader, PluginInfo

class Plugin(ABC):
    @property
    def info(self) -> PluginInfo: ...
    async def setup(self, registry: PluginRegistry) -> None: ...
    async def teardown(self) -> None: ...

class PluginRegistry:
    async def load(self, plugin: Plugin) -> None
    async def load_package(self, module_path: str) -> None
    async def load_directory(self, directory: str | Path) -> int
    def register_tool(self, name: str, handler: Callable) -> None
    def get_tool(self, name: str) -> Callable | None
    def list_plugins(self) -> list[PluginInfo]

class PluginLoader:
    async def discover(
        self,
        package: str | None = None,
        directory: str | Path | None = None,
    ) -> int
```

---

## 💡 Examples

### Async Gateway with Connection Pooling

```python
import asyncio
from loopy import Gateway, ProviderConfig, ModelProvider

async def main():
    async with Gateway() as gateway:
        gateway.add_provider("openai", ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="sk-...",
            model="gpt-4",
        ))
        
        response = await gateway.chat("Hello!", provider="openai")
        print(response.content)

asyncio.run(main())
```

### Evaluator-Optimizer Pattern

```python
import asyncio
from loopy import EvalGate, EvalGateType, JudgeConfig

async def my_judge(prompt: str) -> str:
    return '{"score": 0.85, "pass": true, "feedback": "Good quality"}'

gate = EvalGate(
    gate_type=EvalGateType.JUDGE,
    config=JudgeConfig(
        criteria=["correct", "concise", "helpful"],
        threshold=0.7,
    ),
    judge_fn=my_judge,
)

async def main():
    result = await gate.evaluate(
        input_text="What is Python?",
        output="Python is a programming language.",
    )
    print(f"Passed: {result.passed}, Score: {result.score}")

asyncio.run(main())
```

### Orchestrator-Workers Pattern

```python
import asyncio
from loopy import Orchestrator, SubAgent, Router, RoutingRule

async def researcher(task, ctx):
    return f"Research: {task}"

async def coder(task, ctx):
    return f"Code: {task}"

router = Router()
router.add_rule(RoutingRule(pattern=r"research", agent_name="researcher"))
router.add_rule(RoutingRule(pattern=r"code|build", agent_name="coder"))

orchestrator = Orchestrator(router=router)
orchestrator.add_agent(SubAgent(name="researcher", handler=researcher))
orchestrator.add_agent(SubAgent(name="coder", handler=coder))

async def main():
    result = await orchestrator.run("Build a REST API")
    print(result.output)

asyncio.run(main())
```

### Middleware Pipeline with Retry

```python
import asyncio
from loopy import MiddlewarePipeline, RetryMiddleware, CircuitBreakerMiddleware

pipeline = MiddlewarePipeline()
pipeline.add(RetryMiddleware(max_retries=3, base_delay=1.0))
pipeline.add(CircuitBreakerMiddleware(failure_threshold=5))

async def my_handler(data, **kwargs):
    return f"Processed: {data['message']}"

async def main():
    result = await pipeline.execute(
        operation="llm.chat",
        handler=my_handler,
        data={"message": "Hello"},
    )
    print(result)

asyncio.run(main())
```

### OpenTelemetry Export

```python
import asyncio
from loopy import Tracer, TraceExporter

async def main():
    tracer = Tracer(service="my_app")
    
    with tracer.start("llm_call") as span:
        span.set_attribute("model", "gpt-4")
        # ... do work ...
    
    exporter = TraceExporter(tracer)
    exporter.export_file("traces.json")
    await exporter.export_http("http://localhost:14268/api/traces")

asyncio.run(main())
```

### RAG Plugin

```python
import asyncio
from loopy.plugins.rag import Retriever, Document

retriever = Retriever()
retriever.add(Document.from_text("Python is a programming language"))
retriever.add(Document.from_text("JavaScript is for web"))

async def main():
    results = await retriever.search("programming", top_k=5)
    for r in results:
        print(f"{r.score:.3f}: {r.document.content}")

asyncio.run(main())
```

### Memory Plugin

```python
from loopy.plugins.memory import MemoryStore, Memory

store = MemoryStore(storage_path="./memory.json")

store.add(Memory(
    id="pref_1",
    content="User prefers dark mode",
    category="preferences",
    importance=0.8,
))

memories = store.recall("dark mode", top_k=5)
for m in memories:
    print(f"{m.importance:.1f}: {m.content}")
```

---

## 🔌 Plugins

### First-Party Plugins

| Plugin | Description | Capabilities |
|--------|-------------|--------------|
| `loopy-rag` | Retrieval-Augmented Generation | tool, retriever |
| `loopy-tools` | Tool registry + function calling | tool, registry |
| `loopy-memory` | Persistent agent memory | tool, storage |
| `loopy-audio` | STT/TTS integration | tool, audio |
| `loopy-marketplace` | Plugin discovery/installation | tool, marketplace |

### Installing Plugins

```python
from loopy import PluginRegistry
from loopy.plugins.rag import RAGPlugin

registry = PluginRegistry()
await registry.load(RAGPlugin())
```

### Creating Custom Plugins

```python
from loopy import Plugin, PluginInfo, PluginRegistry

class MyPlugin(Plugin):
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            capabilities=["tool"],
        )
    
    async def setup(self, registry: PluginRegistry) -> None:
        registry.register_tool("my_tool", my_handler)
    
    async def teardown(self) -> None:
        # Cleanup
        pass

async def my_handler(data):
    return f"Handled: {data}"
```

---

## 🖥️ CLI Reference

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
