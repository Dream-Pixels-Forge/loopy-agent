"""
Type stubs for loopy package.

Provides complete type hints for IDE autocompletion and static analysis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

# ============================================================
# Loop Types
# ============================================================

class StepStatus(str, Enum):
    PLANNING: str
    ACTING: str
    OBSERVING: str
    REFLECTING: str
    COMPLETE: str
    FAILED: str

@dataclass
class StepResult:
    step: int
    status: StepStatus
    plan: str
    action: str
    observation: str
    reflection: str
    data: dict[str, Any]
    error: str | None

@dataclass
class LoopConfig:
    max_steps: int
    max_retries: int
    stop_on_error: bool
    planner: Callable[[list[StepResult]], Awaitable[str]] | None
    actor: Callable[[str], Awaitable[str]] | None
    observer: Callable[[str], Awaitable[str]] | None
    reflector: Callable[[list[StepResult]], Awaitable[str]] | None
    should_stop: Callable[[list[StepResult]], Awaitable[bool]] | None

class AgentLoop:
    def __init__(self, config: LoopConfig | None = ...) -> None: ...
    async def run(self, initial_context: str = ...) -> list[StepResult]: ...

# ============================================================
# Gateway Types
# ============================================================

class ModelProvider(str, Enum):
    OPENAI: str
    ANTHROPIC: str
    OLLAMA: str
    CUSTOM: str

@dataclass
class ProviderConfig:
    provider: ModelProvider
    api_key: str | None
    base_url: str
    model: str
    rpm: int
    tpm: int

@dataclass
class GatewayResponse:
    content: str
    model: str
    provider: ModelProvider
    tokens_used: int
    latency_ms: float
    cached: bool
    metadata: dict[str, Any]

class Gateway:
    def __init__(self) -> None: ...
    def add_provider(self, name: str, config: ProviderConfig) -> None: ...
    async def chat(
        self,
        message: str,
        provider: str | None = ...,
        system: str | None = ...,
        temperature: float = ...,
        max_tokens: int = ...,
        **kwargs: Any,
    ) -> GatewayResponse: ...
    async def chat_batch(
        self,
        messages: list[str],
        provider: str | None = ...,
        system: str | None = ...,
        temperature: float = ...,
        max_tokens: int = ...,
        max_concurrent: int = ...,
    ) -> list[GatewayResponse]: ...
    async def chat_streaming(
        self,
        message: str,
        provider: str | None = ...,
        system: str | None = ...,
        temperature: float = ...,
        max_tokens: int = ...,
    ) -> AsyncGenerator[str, None]: ...
    def get_logs(self) -> list[dict[str, Any]]: ...
    async def close(self) -> None: ...

# ============================================================
# Guardrails Types
# ============================================================

class FilterAction(str, Enum):
    BLOCK: str
    REDACT: str
    WARN: str
    PASS: str

@dataclass
class FilterResult:
    action: FilterAction
    original: str
    filtered: str
    reasons: list[str]
    metadata: dict[str, Any]

@dataclass
class GuardrailConfig:
    detect_ssn: bool
    detect_email: bool
    detect_phone: bool
    detect_credit_card: bool
    detect_ip_address: bool
    detect_jailbreak: bool
    jailbreak_sensitivity: float
    blocked_patterns: list[str]
    blocked_keywords: list[str]
    custom_filters: list[Callable[[str], Awaitable[FilterResult]]]

class InputFilter:
    def __init__(self, config: GuardrailConfig | None = ...) -> None: ...
    def check(self, text: str) -> FilterResult: ...

class OutputFilter:
    def __init__(self, config: GuardrailConfig | None = ...) -> None: ...
    def check(self, text: str) -> FilterResult: ...

class GuardrailPipeline:
    def __init__(self, config: GuardrailConfig | None = ...) -> None: ...
    def filter_input(self, text: str) -> FilterResult: ...
    def filter_output(self, text: str) -> FilterResult: ...
    def get_history(self) -> list[dict[str, Any]]: ...

# ============================================================
# Evals Types
# ============================================================

class Verdict(str, Enum):
    PASS: str
    FAIL: str
    PARTIAL: str

@dataclass
class EvalCase:
    name: str
    input_text: str
    expected_output: str | None
    criteria: list[str]
    tags: list[str]
    threshold: float

@dataclass
class EvalResult:
    case: EvalCase
    actual_output: str
    verdict: Verdict
    score: float
    reasoning: str
    criteria_scores: dict[str, float]
    metadata: dict[str, Any]

@dataclass
class EvalSuite:
    name: str
    cases: list[EvalCase]
    description: str

@dataclass
class EvalReport:
    suite_name: str
    results: list[EvalResult]
    @property
    def total(self) -> int: ...
    @property
    def passed(self) -> int: ...
    @property
    def failed(self) -> int: ...
    @property
    def partial(self) -> int: ...
    @property
    def pass_rate(self) -> float: ...
    @property
    def average_score(self) -> float: ...
    def summary(self) -> dict[str, Any]: ...

class Evaluator:
    def __init__(
        self,
        judge_fn: Callable[[str], Awaitable[str]] | None = ...,
        model_fn: Callable[[str], Awaitable[str]] | None = ...,
    ) -> None: ...
    async def run(
        self,
        suite: EvalSuite,
        model_fn: Callable[[str], Awaitable[str]] | None = ...,
    ) -> EvalReport: ...

# ============================================================
# Cache Types
# ============================================================

@dataclass
class CacheEntry:
    key: str
    response: str
    model: str
    tokens_saved: int
    created_at: float
    last_accessed: float
    access_count: int
    metadata: dict[str, Any]

@dataclass
class CacheStats:
    hits: int
    misses: int
    total_saved_tokens: int
    @property
    def hit_rate(self) -> float: ...
    @property
    def estimated_savings(self) -> float: ...

class LLMCache:
    def __init__(
        self,
        ttl: int = ...,
        max_size: int = ...,
        persist_path: str | Path | None = ...,
    ) -> None: ...
    def get(self, prompt: str, model: str, **kwargs: Any) -> str | None: ...
    def set(
        self,
        prompt: str,
        response: str,
        model: str,
        tokens: int = ...,
        **kwargs: Any,
    ) -> None: ...
    def invalidate(self, prompt: str, model: str, **kwargs: Any) -> bool: ...
    def clear(self) -> None: ...
    def stats(self) -> CacheStats: ...

# ============================================================
# Observability Types
# ============================================================

class SpanStatus(str, Enum):
    OK: str
    ERROR: str
    UNSET: str

@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_id: str | None
    start_time: float
    end_time: float | None
    status: SpanStatus
    attributes: dict[str, Any]
    events: list[dict[str, Any]]
    @property
    def duration_ms(self) -> float | None: ...
    def set_attribute(self, key: str, value: Any) -> None: ...
    def add_event(self, name: str, attributes: dict[str, Any] | None = ...) -> None: ...
    def set_status(self, status: SpanStatus, message: str = ...) -> None: ...
    def end(self) -> None: ...
    def to_dict(self) -> dict[str, Any]: ...

class Tracer:
    def __init__(self, service: str = ...) -> None: ...
    def start_span(self, name: str, parent_id: str | None = ..., **attributes: Any) -> Span: ...
    def start(self, name: str, **attributes: Any) -> SpanContext: ...
    def get_spans(self) -> list[Span]: ...
    def get_trace(self, trace_id: str) -> list[Span]: ...
    def export_json(self) -> str: ...
    def export_otlp(self) -> dict[str, Any]: ...
    def clear(self) -> None: ...

class SpanContext:
    span: Span
    def __enter__(self) -> Span: ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

@dataclass
class MetricPoint:
    name: str
    value: float
    timestamp: float
    tags: dict[str, str]

class MetricsCollector:
    def __init__(self) -> None: ...
    def increment(self, name: str, value: float = ..., **tags: str) -> None: ...
    def histogram(self, name: str, value: float, **tags: str) -> None: ...
    def gauge(self, name: str, value: float, **tags: str) -> None: ...
    def summary(self) -> dict[str, Any]: ...
    def export(self) -> list[dict[str, Any]]: ...
    def clear(self) -> None: ...

# ============================================================
# MCP Types
# ============================================================

@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any]

@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]

@dataclass
class ToolResult:
    content: str | list[dict[str, Any]]
    is_error: bool
    metadata: dict[str, Any]

class MCPClient:
    def __init__(self, server_url: str, api_key: str | None = ...) -> None: ...
    async def list_tools(self) -> list[Tool]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any] | None = ...) -> ToolResult: ...
    async def health_check(self) -> bool: ...
    async def close(self) -> None: ...

class LocalMCP:
    def __init__(self) -> None: ...
    def tool(
        self,
        name: str,
        description: str = ...,
        input_schema: dict[str, Any] | None = ...,
    ) -> Callable: ...
    async def list_tools(self) -> list[Tool]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any] | None = ...) -> ToolResult: ...

# ============================================================
# Agents Types
# ============================================================

class AgentStatus(str, Enum):
    PENDING: str
    RUNNING: str
    COMPLETED: str
    FAILED: str

@dataclass
class AgentResult:
    agent_name: str
    status: AgentStatus
    output: str
    error: str | None
    metadata: dict[str, Any]
    duration_ms: float

@dataclass
class SubAgent:
    name: str
    description: str
    tools: list[str]
    system_prompt: str
    handler: Callable[[str, dict[str, Any]], Awaitable[str]] | None
    status: AgentStatus
    result: AgentResult | None

class Orchestrator:
    def __init__(self, max_concurrent: int = ..., router: Router | None = ...) -> None: ...
    def add_agent(self, agent: SubAgent) -> None: ...
    def get_agent(self, name: str) -> SubAgent | None: ...
    def list_agents(self) -> list[SubAgent]: ...
    async def route(self, task: str) -> str: ...
    async def decompose(self, task: str) -> list[SubTask]: ...
    async def run(
        self,
        task: str,
        agent_name: str | None = ...,
        context: dict[str, Any] | None = ...,
    ) -> AgentResult: ...
    async def run_all(
        self,
        task: str,
        context: dict[str, Any] | None = ...,
    ) -> list[AgentResult]: ...
    async def run_decomposed(
        self,
        task: str,
        context: dict[str, Any] | None = ...,
    ) -> list[AgentResult]: ...
    def get_history(self) -> list[AgentResult]: ...
    def get_summary(self) -> dict[str, Any]: ...

# ============================================================
# Middleware Types
# ============================================================

@dataclass
class MiddlewareContext:
    operation: str
    data: dict[str, Any]
    metadata: dict[str, Any]
    cancelled: bool
    cancel_reason: str
    def cancel(self, reason: str = ...) -> None: ...

class Middleware(ABC):
    @property
    def name(self) -> str: ...
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext: ...
    async def after(self, ctx: MiddlewareContext, result: Any) -> Any: ...
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception: ...

class FunctionMiddleware(Middleware):
    def __init__(
        self,
        name: str = ...,
        before_fn: Callable[[MiddlewareContext], Awaitable[MiddlewareContext]] | None = ...,
        after_fn: Callable[[MiddlewareContext, Any], Awaitable[Any]] | None = ...,
        error_fn: Callable[[MiddlewareContext, Exception], Awaitable[Exception]] | None = ...,
    ) -> None: ...

class MiddlewarePipeline:
    def __init__(self) -> None: ...
    def add(self, middleware: Middleware) -> None: ...
    def remove(self, name: str) -> bool: ...
    def clear(self) -> None: ...
    async def execute(
        self,
        operation: str,
        handler: Callable[..., Awaitable[Any]],
        data: dict[str, Any] | None = ...,
        **kwargs: Any,
    ) -> Any: ...

class LoggingMiddleware(Middleware): ...
class TimingMiddleware(Middleware): ...

class RateLimitMiddleware(Middleware):
    def __init__(self, max_per_second: int = ...) -> None: ...

class CacheMiddleware(Middleware):
    def __init__(self, ttl: int = ...) -> None: ...

class ValidationMiddleware(Middleware):
    def __init__(
        self,
        required_fields: list[str] | None = ...,
        validators: dict[str, Callable[[Any], bool]] | None = ...,
    ) -> None: ...

# ============================================================
# Plugin Types
# ============================================================

@dataclass
class PluginInfo:
    name: str
    version: str
    description: str
    author: str
    url: str
    capabilities: list[str]
    requires: list[str]

class Plugin(ABC):
    @property
    @abstractmethod
    def info(self) -> PluginInfo: ...
    @abstractmethod
    async def setup(self, registry: PluginRegistry) -> None: ...
    async def teardown(self) -> None: ...

class PluginRegistry:
    def __init__(self) -> None: ...
    async def load(self, plugin: Plugin) -> None: ...
    async def load_package(self, module_path: str) -> None: ...
    async def load_directory(self, directory: str | Path) -> int: ...
    def register_tool(self, name: str, handler: Callable) -> None: ...
    def get_tool(self, name: str) -> Callable | None: ...
    def list_tools(self) -> list[str]: ...
    def register_middleware(self, name: str, middleware: Any) -> None: ...
    def get_middleware(self, name: str) -> Any: ...
    def register_provider(self, name: str, provider: Any) -> None: ...
    def get_provider(self, name: str) -> Any: ...
    def register_extension(self, hook_name: str, callback: Callable) -> None: ...
    async def trigger_extension(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]: ...
    def get_plugin(self, name: str) -> Plugin | None: ...
    def list_plugins(self) -> list[PluginInfo]: ...
    async def unload(self, name: str) -> bool: ...
    async def unload_all(self) -> None: ...

class PluginLoader:
    def __init__(self, registry: PluginRegistry | None = ...) -> None: ...
    async def discover(
        self,
        package: str | None = ...,
        directory: str | Path | None = ...,
    ) -> int: ...
