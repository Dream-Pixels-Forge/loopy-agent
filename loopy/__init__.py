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

v0.5.0 additions:
    - Audit scoring (Loop Readiness Score 0-100)
    - Durable state management (STATE.md, run logs)
    - Maker/Checker verification gate
    - Token cost tracking with daily budgets
    - Persistent skills (SKILL.md)
    - Config/state drift detection
    - Production loop patterns (7 built-in)
    - Safety gates (denylist paths, escalation)
"""

from loopy.agents import (
    AgentResult,
    AgentStatus,
    Orchestrator,
    Router,
    RoutingRule,
    SubAgent,
    SubTask,
    TaskDecomposer,
)
from loopy.cache import CacheStats, LLMCache
from loopy.evals import (
    EvalCase,
    EvalGate,
    EvalGateResult,
    EvalGateType,
    EvalResult,
    EvalSuite,
    Evaluator,
    JudgeConfig,
    Verdict,
)
from loopy.gateway import ConnectionPool, Gateway, GatewayResponse, ModelProvider, ProviderConfig
from loopy.guardrails import FilterAction, GuardrailPipeline, InputFilter, OutputFilter
from loopy.loop import AgentLoop, LoopConfig, StepResult, StepStatus
from loopy.mcp import LocalMCP, MCPClient, Tool
from loopy.middleware import (
    CacheMiddleware,
    CircuitBreakerMiddleware,
    FallbackMiddleware,
    FunctionMiddleware,
    LoggingMiddleware,
    Middleware,
    MiddlewareContext,
    MiddlewarePipeline,
    RateLimitMiddleware,
    RetryMiddleware,
    TimingMiddleware,
    ValidationMiddleware,
)
from loopy.observe import MetricsCollector, Span, SpanStatus, Tracer
from loopy.plugins import Plugin, PluginInfo, PluginLoader, PluginRegistry

# First-party plugins (lazy import to avoid circular deps)
try:
    from loopy.plugins.audio import AudioPlugin, SpeechToText, TextToSpeech
    from loopy.plugins.marketplace import MarketplacePlugin, PluginMarketplace
    from loopy.plugins.memory import Memory, MemoryPlugin, MemoryStore
    from loopy.plugins.rag import Document, RAGPlugin, Retriever
    from loopy.plugins.tools import Tool, ToolResult, ToolsPlugin
except ImportError:
    pass  # Optional dependencies

# v0.5.0 — Production readiness modules
from loopy.audit import AuditReport, CheckItem, LoopAuditor, ReadinessLevel
from loopy.cost import BudgetExceeded, CostReport, CostTracker
from loopy.drift import DriftDetector, DriftIssue, DriftReport
from loopy.observe import TraceExporter
from loopy.patterns import LoopPattern, PatternCadence, PatternRegistry, RiskLevel
from loopy.safety import EscalationReason, SafetyCheck, SafetyGate, SafetyResult
from loopy.skills import Skill, SkillRegistry
from loopy.state import LoopState, RunOutcome, RunRecord, StateManager
from loopy.verification import VerificationGate, VerificationStatus, VerifyResult

__version__ = "0.5.0"

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
    # Audit
    "LoopAuditor",
    "AuditReport",
    "CheckItem",
    "ReadinessLevel",
    # State
    "LoopState",
    "RunRecord",
    "RunOutcome",
    "StateManager",
    # Verification
    "VerificationGate",
    "VerifyResult",
    "VerificationStatus",
    # Cost
    "CostTracker",
    "CostReport",
    "BudgetExceeded",
    # Skills
    "Skill",
    "SkillRegistry",
    # Drift
    "DriftDetector",
    "DriftReport",
    "DriftIssue",
    # Patterns
    "PatternRegistry",
    "LoopPattern",
    "PatternCadence",
    "RiskLevel",
    # Safety
    "SafetyGate",
    "SafetyCheck",
    "SafetyResult",
    "EscalationReason",
]
