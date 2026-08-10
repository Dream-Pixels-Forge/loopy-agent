"""
Type stubs for loopy package.

Provides complete type hints for IDE autocompletion and static analysis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
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

class ConnectionPool:
    def __init__(self, max_size: int = ...) -> None: ...
    async def get_connection(self, provider: str) -> Any: ...
    async def close(self) -> None: ...
    def stats(self) -> dict[str, Any]: ...

class Gateway:
    def __init__(self) -> None: ...
    def add_provider(self, name: str, config: ProviderConfig) -> None: ...
    async def chat(
        self, message: str, provider: str | None = ...,
        system: str | None = ..., temperature: float = ...,
        max_tokens: int = ..., **kwargs: Any,
    ) -> GatewayResponse: ...
    async def chat_batch(
        self, messages: list[str], provider: str | None = ...,
        system: str | None = ..., temperature: float = ...,
        max_tokens: int = ..., max_concurrent: int = ...,
    ) -> list[GatewayResponse]: ...
    async def chat_streaming(
        self, message: str, provider: str | None = ...,
        system: str | None = ..., temperature: float = ...,
        max_tokens: int = ...,
    ) -> AsyncGenerator[str]: ...
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

class EvalGateType(str, Enum):
    JUDGE: str
    MANUAL: str

@dataclass
class JudgeConfig:
    evaluator_model: str
    criteria: list[str]
    threshold: float
    prompt_template: str

@dataclass
class EvalGateResult:
    gate_type: EvalGateType
    passed: bool
    score: float
    feedback: str
    metadata: dict[str, Any]

class EvalGate:
    def __init__(
        self, gate_type: EvalGateType, config: JudgeConfig | None = ...,
        judge_fn: Callable[[str], Awaitable[str]] | None = ...,
    ) -> None: ...
    async def evaluate(
        self, input_text: str, output: str, criteria: list[str] | None = ...,
    ) -> EvalGateResult: ...

class Evaluator:
    def __init__(
        self, judge_fn: Callable[[str], Awaitable[str]] | None = ...,
        model_fn: Callable[[str], Awaitable[str]] | None = ...,
    ) -> None: ...
    async def run(
        self, suite: EvalSuite, model_fn: Callable[[str], Awaitable[str]] | None = ...,
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
        self, ttl: int = ..., max_size: int = ...,
        persist_path: str | Path | None = ...,
    ) -> None: ...
    def get(self, prompt: str, model: str, **kwargs: Any) -> str | None: ...
    def set(
        self, prompt: str, response: str, model: str,
        tokens: int = ..., **kwargs: Any,
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

class SpanContext:
    span: Span
    def __enter__(self) -> Span: ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

class Tracer:
    def __init__(self, service: str = ...) -> None: ...
    def start_span(self, name: str, parent_id: str | None = ..., **attributes: Any) -> Span: ...
    def start(self, name: str, **attributes: Any) -> SpanContext: ...
    def get_spans(self) -> list[Span]: ...
    def get_trace(self, trace_id: str) -> list[Span]: ...
    def export_json(self) -> str: ...
    def export_otlp(self) -> dict[str, Any]: ...
    def clear(self) -> None: ...

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

class TraceExporter:
    def __init__(self, tracer: Tracer) -> None: ...
    def export_file(self, path: str) -> None: ...
    def export_stdout(self) -> None: ...
    async def export_http(self, endpoint: str) -> None: ...
    def export_opentelemetry(self) -> dict[str, Any]: ...

# ============================================================
# MCP Types
# ============================================================

@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any]

@dataclass
class MCPToolCall:
    name: str
    arguments: dict[str, Any]

@dataclass
class MCPToolResult:
    content: str | list[dict[str, Any]]
    is_error: bool
    metadata: dict[str, Any]

class MCPClient:
    def __init__(
        self, server_url: str, api_key: str | None = ...,
        *, allow_private: bool = ...,
    ) -> None: ...
    async def list_tools(self) -> list[MCPTool]: ...
    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = ...,
    ) -> MCPToolResult: ...
    async def health_check(self) -> bool: ...
    async def close(self) -> None: ...
    async def __aenter__(self) -> MCPClient: ...
    async def __aexit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any,
    ) -> None: ...

class LocalMCP:
    def __init__(self) -> None: ...
    def tool(
        self, name: str, description: str = ...,
        input_schema: dict[str, Any] | None = ...,
    ) -> Callable: ...
    async def list_tools(self) -> list[MCPTool]: ...
    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = ...,
    ) -> MCPToolResult: ...

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

class SubTask:
    id: str
    description: str
    dependencies: list[str]
    required_agent: str | None
    status: str
    result: str | None

class RoutingRule:
    pattern: str
    agent_name: str
    priority: int
    description: str

class Router:
    rules: list[RoutingRule]
    classify_fn: Callable[[str, list[RoutingRule]], Awaitable[str]] | None
    def __init__(
        self, classify_fn: Callable[[str, list[RoutingRule]], Awaitable[str]] | None = ...,
    ) -> None: ...
    def add_rule(self, rule: RoutingRule) -> None: ...
    async def classify(self, task: str) -> str: ...

class TaskDecomposer:
    classify_fn: Callable[[str], Awaitable[str]] | None
    def __init__(self, classify_fn: Callable[[str], Awaitable[str]] | None = ...) -> None: ...
    async def decompose(self, task: str) -> list[SubTask]: ...

class Orchestrator:
    def __init__(self, max_concurrent: int = ..., router: Router | None = ...) -> None: ...
    def add_agent(self, agent: SubAgent) -> None: ...
    def get_agent(self, name: str) -> SubAgent | None: ...
    def list_agents(self) -> list[SubAgent]: ...
    async def route(self, task: str) -> str: ...
    async def decompose(self, task: str) -> list[SubTask]: ...
    async def run(
        self, task: str, agent_name: str | None = ...,
        context: dict[str, Any] | None = ...,
    ) -> AgentResult: ...
    async def run_all(
        self, task: str, context: dict[str, Any] | None = ...,
    ) -> list[AgentResult]: ...
    async def run_decomposed(
        self, task: str, context: dict[str, Any] | None = ...,
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
        self, name: str = ...,
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
        self, operation: str, handler: Callable[..., Awaitable[Any]],
        data: dict[str, Any] | None = ..., **kwargs: Any,
    ) -> Any: ...

class LoggingMiddleware(Middleware): ...
class TimingMiddleware(Middleware): ...

class RateLimitMiddleware(Middleware):
    def __init__(self, max_per_second: int = ...) -> None: ...

class CacheMiddleware(Middleware):
    def __init__(self, ttl: int = ...) -> None: ...

class ValidationMiddleware(Middleware):
    def __init__(
        self, required_fields: list[str] | None = ...,
        validators: dict[str, Callable[[Any], bool]] | None = ...,
    ) -> None: ...

class RetryMiddleware(Middleware):
    def __init__(
        self, max_retries: int = ..., base_delay: float = ...,
        max_delay: float = ...,
        retryable_exceptions: tuple[type[Exception], ...] = ...,
    ) -> None: ...

class CircuitBreakerMiddleware(Middleware):
    def __init__(
        self, failure_threshold: int = ..., recovery_timeout: float = ...,
    ) -> None: ...

class FallbackMiddleware(Middleware):
    def __init__(
        self, fallback_fn: Callable[[MiddlewareContext, Any], Awaitable[Any]] | None = ...,
        fallback_data: dict[str, Any] | None = ...,
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
    def register_tool(
        self, name: str, handler: Callable, *, agent_visible: bool = ...,
        requires_approval: bool = ..., scope: str = ...,
        allowed_values: dict[str, set[str]] | None = ...,
    ) -> None: ...
    def get_tool(self, name: str) -> Callable | None: ...
    def list_tools(self) -> list[str]: ...
    def list_all_tools(self) -> list[str]: ...
    def register_middleware(self, name: str, middleware: Any) -> None: ...
    def get_middleware(self, name: str) -> Any: ...
    def register_provider(self, name: str, provider: Any) -> None: ...
    def get_provider(self, name: str) -> Any: ...
    def register_extension(self, hook_name: str, callback: Callable) -> None: ...
    async def trigger_extension(
        self, hook_name: str, *args: Any, **kwargs: Any,
    ) -> list[Any]: ...
    def get_plugin(self, name: str) -> Plugin | None: ...
    def list_plugins(self) -> list[PluginInfo]: ...
    async def unload(self, name: str) -> bool: ...
    async def unload_all(self) -> None: ...
    def denials(self) -> list[dict[str, Any]]: ...
    async def execute_tool(
        self, name: str, arguments: dict[str, Any] | None = ...,
        *, approver: Callable[[str, dict[str, Any]], Awaitable[bool]] | None = ...,
    ) -> Any: ...

class PluginLoader:
    def __init__(self, registry: PluginRegistry | None = ...) -> None: ...
    async def discover(
        self, package: str | None = ..., directory: str | Path | None = ...,
    ) -> int: ...

# ============================================================
# NetUtil Types (Security)
# ============================================================

def is_private_host(host: str) -> bool: ...
def validate_outbound_url(
    url: str, *, allow_private: bool = ...,
    allow_schemes: tuple[str, ...] = ...,
) -> str: ...

# ============================================================
# Prompting Types (Security)
# ============================================================

CANARY_PREFIX: str
def make_canary(prefix: str = ...) -> str: ...
def check_canary(text: str, canary: str | None) -> bool: ...
def mark_untrusted(content: str, marker: str = ...) -> str: ...
def build_prompt(
    user_message: str, *, system: str | None = ...,
    untrusted_docs: list[str] | tuple[str, ...] | None = ...,
    canary: str | None = ...,
) -> list[dict[str, Any]]: ...
def strip_md_media(text: str) -> str: ...

# ============================================================
# State Types
# ============================================================

class RunOutcome(str, Enum):
    SUCCESS: str
    FAILURE: str
    ESCALATED: str

@dataclass
class RunRecord:
    task: str
    outcome: RunOutcome
    tokens_used: int
    duration_ms: float
    timestamp: str
    metadata: dict[str, Any]
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord: ...

@dataclass
class LoopState:
    current_task: str | None
    attempts: int
    max_attempts: int
    history: list[RunRecord]
    metadata: dict[str, Any]
    @property
    def total_tokens(self) -> int: ...
    @property
    def last_run(self) -> RunRecord | None: ...
    def add_record(self, record: RunRecord) -> None: ...
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopState: ...

class StateManager:
    def __init__(self, path: str = ...) -> None: ...
    def load(self) -> LoopState: ...
    def save(self, state: LoopState) -> None: ...
    def prune(self, max_age_days: int = ...) -> int: ...

# ============================================================
# Verification Types
# ============================================================

class VerificationStatus(str, Enum):
    PASSED: str
    FAILED: str
    ERROR: str

@dataclass
class VerifyResult:
    status: VerificationStatus
    feedback: str
    score: float
    output: Any
    duration_ms: float
    @property
    def passed(self) -> bool: ...

class VerificationGate:
    def __init__(
        self, implementer: Callable[[str], Awaitable[Any]],
        verifier: Callable[[Any], Awaitable[VerifyResult]],
        test_fn: Callable[[Any], Awaitable[bool]] | None = ...,
        threshold: float = ...,
    ) -> None: ...
    async def run(self, task: str) -> VerifyResult: ...

# ============================================================
# Cost Types
# ============================================================

class BudgetExceeded(Exception):
    limit: int
    used: int

@dataclass
class CostReport:
    used: int
    limit: int
    remaining: int
    usage_percent: float
    def summary(self) -> dict[str, Any]: ...

class CostTracker:
    def __init__(self, daily_limit: int = ..., persist_path: str | None = ...) -> None: ...
    @property
    def used_today(self) -> int: ...
    @property
    def remaining(self) -> int: ...
    @property
    def should_stop(self) -> bool: ...
    def record(self, tokens: int) -> None: ...
    def report(self) -> CostReport: ...
    def reset(self) -> None: ...

# ============================================================
# Skills Types
# ============================================================

@dataclass
class Skill:
    name: str
    description: str
    triggers: list[str]
    instructions: str
    source_path: str | None
    @classmethod
    def from_markdown(cls, text: str, source_path: str | None = ...) -> Skill: ...
    def matches(self, task: str) -> bool: ...

class SkillRegistry:
    def __init__(self) -> None: ...
    def add_skill(self, skill: Skill) -> None: ...
    def get_skill(self, name: str) -> Skill | None: ...
    def match_skills(self, task: str, top_k: int = ...) -> list[Skill]: ...
    def load_from_directory(self, directory: str | Path) -> int: ...
    def load_from_file(self, path: str | Path) -> Skill | None: ...

# ============================================================
# Drift Types
# ============================================================

@dataclass
class DriftIssue:
    field: str
    expected: Any
    actual: Any
    severity: str
    suggestion: str

@dataclass
class DriftReport:
    drifted: bool
    issues: list[DriftIssue]
    config_snapshot: dict[str, Any]
    state_snapshot: dict[str, Any]
    def summary(self) -> dict[str, Any]: ...

class DriftDetector:
    def __init__(self, required_fields: list[str] | None = ...) -> None: ...
    def detect(self, config: dict[str, Any], state: dict[str, Any]) -> DriftReport: ...

# ============================================================
# Patterns Types
# ============================================================

class RiskLevel(str, Enum):
    LOW: str
    MEDIUM: str
    HIGH: str

class PatternCadence(str, Enum):
    DAILY: str
    WEEKLY: str
    ON_DEMAND: str

@dataclass
class LoopPattern:
    name: str
    description: str
    cadence: PatternCadence
    risk_level: RiskLevel
    readiness_level: str
    tags: list[str]

class PatternRegistry:
    def __init__(self) -> None: ...
    def register(self, pattern: LoopPattern) -> None: ...
    def get(self, name: str) -> LoopPattern | None: ...
    def list_patterns(self) -> list[LoopPattern]: ...
    def filter_by_risk(self, risk: RiskLevel) -> list[LoopPattern]: ...

# ============================================================
# Safety Types
# ============================================================

class EscalationReason(str, Enum):
    MAX_ATTEMPTS: str
    DENYLIST_PATH: str
    LOW_CONFIDENCE: str
    AMBIGUOUS_INPUT: str

@dataclass
class SafetyCheck:
    name: str
    passed: bool
    reason: str
    escalation: EscalationReason | None

@dataclass
class SafetyResult:
    safe: bool
    checks: list[SafetyCheck]
    should_escalate: bool

class SafetyGate:
    DEFAULT_DENYLIST: list[str]
    def __init__(
        self, denylist_paths: list[str] | None = ...,
        max_attempts: int = ..., human_gate_threshold: float = ...,
    ) -> None: ...
    async def check_path(self, path: str) -> SafetyCheck: ...
    def should_escalate(
        self, attempts: int, confidence: float, path_safe: bool = ...,
    ) -> bool: ...
    async def check(
        self, path: str | None = ..., attempts: int = ..., confidence: float = ...,
    ) -> SafetyResult: ...

# ============================================================
# Audit Types
# ============================================================

class ReadinessLevel(str, Enum):
    L0: str
    L1: str
    L2: str
    L3: str
    @classmethod
    def from_score(cls, score: int) -> ReadinessLevel: ...

@dataclass
class CheckItem:
    name: str
    passed: bool
    weight: int
    description: str
    @property
    def score(self) -> int: ...

@dataclass
class AuditReport:
    score: int
    level: ReadinessLevel
    checks: list[CheckItem]
    suggestions: list[str]
    def summary(self) -> dict[str, Any]: ...

class LoopAuditor:
    CHECKS: list[tuple[str, str, int]]
    async def audit(self, config: dict[str, Any]) -> AuditReport: ...

# ============================================================
# Streaming Types
# ============================================================

class StreamEvent(str, Enum):
    TOKEN: str
    TOOL_CALL: str
    TOOL_RESULT: str
    THINKING: str
    ERROR: str
    DONE: str

@dataclass
class StreamChunk:
    event: StreamEvent
    data: Any
    index: int
    metadata: dict[str, Any]
    def to_dict(self) -> dict[str, Any]: ...
    def to_sse(self) -> str: ...

class StreamBuffer:
    def __init__(self, flush_threshold: int = ...) -> None: ...
    tokens: list[str]
    total_tokens: int
    def add(self, token: str) -> str | None: ...
    def flush(self) -> str: ...
    @property
    def pending(self) -> str: ...

class Streamer:
    def __init__(self, buffer_size: int = ...) -> None: ...
    buffer: StreamBuffer
    chunks: list[StreamChunk]
    index: int
    async def stream(
        self, generator: Callable[[str], AsyncIterator[str]], prompt: str,
    ) -> AsyncIterator[StreamChunk]: ...
    async def collect(self, stream: AsyncIterator[StreamChunk]) -> str: ...
    def to_sse_stream(
        self, stream: AsyncIterator[StreamChunk],
    ) -> AsyncIterator[str]: ...

# ============================================================
# Compliance Types
# ============================================================

class ComplianceFramework(str, Enum):
    SOC2: str
    GDPR: str
    EU_AI_ACT: str

class DataClassification(str, Enum):
    PUBLIC: str
    INTERNAL: str
    CONFIDENTIAL: str
    RESTRICTED: str

@dataclass
class AuditEntry:
    timestamp: str
    action: str
    agent: str
    input_summary: str
    output_summary: str
    classification: DataClassification
    metadata: dict[str, Any]

class AuditLogger:
    def __init__(self, log_path: str | None = ...) -> None: ...
    def log(self, entry: AuditEntry) -> None: ...
    def query(self, agent: str | None = ..., action: str | None = ...) -> list[AuditEntry]: ...

class ComplianceChecker:
    def __init__(self, frameworks: list[ComplianceFramework] | None = ...) -> None: ...
    def check_soc2(self, config: dict[str, Any]) -> dict[str, Any]: ...
    def check_gdpr(self, config: dict[str, Any]) -> dict[str, Any]: ...
    def check_eu_ai_act(self, config: dict[str, Any]) -> dict[str, Any]: ...
    def check_all(self, config: dict[str, Any]) -> dict[str, dict[str, Any]]: ...

# ============================================================
# Explainability Types
# ============================================================

class DecisionType(str, Enum):
    TOOL_SELECTION: str
    PROMPT_SELECTION: str
    MODEL_SELECTION: str
    ROUTING: str
    FILTERING: str
    CUSTOM: str

@dataclass
class DecisionStep:
    decision_type: DecisionType
    description: str
    alternatives: list[str]
    chosen: str
    confidence: float
    reasoning: str
    timestamp: str
    def to_dict(self) -> dict[str, Any]: ...

@dataclass
class DecisionTrace:
    task: str
    steps: list[DecisionStep]
    metadata: dict[str, Any]
    def add_step(self, step: DecisionStep) -> None: ...
    def summary(self) -> dict[str, Any]: ...

class DecisionTracker:
    def __init__(self) -> None: ...
    def start(self, task: str) -> DecisionTrace: ...
    def add_step(self, trace: DecisionTrace, step: DecisionStep) -> None: ...
    def finish(self, trace: DecisionTrace) -> None: ...
    def explain(self, task: str) -> DecisionTrace | None: ...
    def export(self) -> list[dict[str, Any]]: ...

# ============================================================
# Multi-modal Types
# ============================================================

class MediaType(str, Enum):
    IMAGE: str
    AUDIO: str
    VIDEO: str
    FILE: str

@dataclass
class MediaContent:
    media_type: MediaType
    mime_type: str
    data: str
    filename: str | None
    metadata: dict[str, Any]
    def to_openai_format(self) -> dict[str, Any]: ...
    def to_anthropic_format(self) -> dict[str, Any]: ...

@dataclass
class MultiModalMessage:
    text: str
    media: list[MediaContent]
    role: str
    def to_openai(self) -> list[dict[str, Any]]: ...
    def to_anthropic(self) -> dict[str, Any]: ...

class MultiModalBuilder:
    def __init__(self) -> None: ...
    def add_image(
        self, source: str, *, mime_type: str = ..., filename: str | None = ...,
    ) -> MultiModalBuilder: ...
    def add_audio(
        self, source: str, *, mime_type: str = ..., filename: str | None = ...,
    ) -> MultiModalBuilder: ...
    def add_video(
        self, source: str, *, mime_type: str = ..., filename: str | None = ...,
    ) -> MultiModalBuilder: ...
    def build(self, text: str = ..., role: str = ...) -> MultiModalMessage: ...
