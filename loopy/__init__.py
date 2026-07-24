"""
Loopy — 8 Essential AI Concepts in one toolkit.

Modules:
    loop       - Agentic loop engine (Plan → Act → Observe → Reflect)
    gateway    - Multi-provider LLM routing with auth & rate limiting
    guardrails - PII detection, jailbreak filtering, output safety
    evals      - Judge-based model evaluation framework
    cache      - Semantic token caching for cost optimization
    observe    - Traces, logs, and metrics for LLM observability
    mcp        - Model Context Protocol client
    agents     - Multi-agent orchestration with subagents

v0.2.0 additions:
    - Evaluator-optimizer pattern (EvalGate, JudgeConfig)
    - Orchestrator-workers pattern (Router, TaskDecomposer)
    - Async context managers and connection pooling
    - New middleware: Retry, CircuitBreaker, Fallback

v0.3.0 additions:
    - OpenTelemetry export for traces/metrics
    - First-party plugins: RAG, Tools, Memory
    - Plugin marketplace support
"""

from loopy.loop import AgentLoop, StepResult, LoopConfig, StepStatus
from loopy.gateway import Gateway, ModelProvider, ProviderConfig, GatewayResponse, ConnectionPool
from loopy.guardrails import GuardrailPipeline, InputFilter, OutputFilter, FilterAction
from loopy.evals import (
    Evaluator, EvalCase, EvalResult, EvalSuite, Verdict,
    EvalGate, EvalGateType, JudgeConfig, EvalGateResult,
)
from loopy.cache import LLMCache, CacheStats
from loopy.observe import Tracer, Span, SpanStatus, MetricsCollector
from loopy.mcp import MCPClient, Tool, LocalMCP
from loopy.agents import (
    Orchestrator, SubAgent, AgentResult, AgentStatus,
    Router, RoutingRule, TaskDecomposer, SubTask,
)
from loopy.middleware import (
    Middleware,
    MiddlewarePipeline,
    MiddlewareContext,
    FunctionMiddleware,
    LoggingMiddleware,
    TimingMiddleware,
    RateLimitMiddleware,
    CacheMiddleware,
    ValidationMiddleware,
    RetryMiddleware,
    CircuitBreakerMiddleware,
    FallbackMiddleware,
)
from loopy.plugins import Plugin, PluginRegistry, PluginLoader, PluginInfo

# First-party plugins (lazy import to avoid circular deps)
try:
    from loopy.plugins.rag import RAGPlugin, Document, Retriever
    from loopy.plugins.tools import ToolsPlugin, Tool, ToolResult
    from loopy.plugins.memory import MemoryPlugin, Memory, MemoryStore
    from loopy.plugins.audio import AudioPlugin, SpeechToText, TextToSpeech
    from loopy.plugins.marketplace import MarketplacePlugin, PluginMarketplace
except ImportError:
    pass  # Optional dependencies

from loopy.observe import TraceExporter

__version__ = "0.4.0"

__all__ = [
    # Agentic Loop
    "AgentLoop",
    "StepResult",
    "LoopConfig",
    "StepStatus",
    # Gateway
    "Gateway",
    "ModelProvider",
    "ProviderConfig",
    "GatewayResponse",
    "ConnectionPool",
    # Guardrails
    "GuardrailPipeline",
    "InputFilter",
    "OutputFilter",
    "FilterAction",
    # Evals (including v0.2.0 evaluator-optimizer)
    "Evaluator",
    "EvalCase",
    "EvalResult",
    "EvalSuite",
    "Verdict",
    "EvalGate",
    "EvalGateType",
    "JudgeConfig",
    "EvalGateResult",
    # Cache
    "LLMCache",
    "CacheStats",
    # Observability
    "Tracer",
    "Span",
    "SpanStatus",
    "MetricsCollector",
    # MCP
    "MCPClient",
    "Tool",
    "LocalMCP",
    # Multi-Agent (including v0.2.0 orchestrator-workers)
    "Orchestrator",
    "SubAgent",
    "AgentResult",
    "AgentStatus",
    "Router",
    "RoutingRule",
    "TaskDecomposer",
    "SubTask",
    # Middleware (including v0.2.0 new middleware)
    "Middleware",
    "MiddlewarePipeline",
    "MiddlewareContext",
    "FunctionMiddleware",
    "LoggingMiddleware",
    "TimingMiddleware",
    "RateLimitMiddleware",
    "CacheMiddleware",
    "ValidationMiddleware",
    "RetryMiddleware",
    "CircuitBreakerMiddleware",
    "FallbackMiddleware",
    # Plugins
    "Plugin",
    "PluginRegistry",
    "PluginLoader",
    "PluginInfo",
    # First-party plugins
    "RAGPlugin",
    "Document",
    "Retriever",
    "ToolsPlugin",
    "Tool",
    "ToolResult",
    "MemoryPlugin",
    "Memory",
    "MemoryStore",
    "AudioPlugin",
    "SpeechToText",
    "TextToSpeech",
    "MarketplacePlugin",
    "PluginMarketplace",
    # Observability exports
    "TraceExporter",
]
