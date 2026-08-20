"""
Loopy — 21 Essential AI Concepts in one toolkit.

Modules:
    loop            - Agentic loop engine (Plan → Act → Observe → Reflect)
    gateway         - Multi-provider LLM routing with auth & rate limiting
    guardrails      - PII detection, jailbreak filtering, output safety
    evals           - Judge-based model evaluation framework
    cache           - Semantic token caching for cost optimization
    observe         - Traces, logs, and metrics for LLM observability
    mcp             - Model Context Protocol client
    agents          - Multi-agent orchestration with subagents
    middleware      - Composable request/response hooks
    plugins         - Plugin system with RAG, Tools, Memory
    state           - Durable loop state persistence
    safety          - Production safety gates (denylist, escalation)
    cost            - Token cost tracking with daily budgets
    drift           - Config/state drift detection
    skills          - Persistent agent knowledge (SKILL.md)
    verification    - Maker/Checker pattern
    audit           - Loop readiness scoring (L0-L3)
    streaming       - Real-time token-by-token output
    compliance      - SOC2, GDPR, EU AI Act checks
    explainability  - Decision audit trail
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
from loopy.mcp import LocalMCP, MCPClient, MCPToolResult
from loopy.mcp import Tool as MCPTool
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
from loopy.netutil import is_private_host, validate_outbound_url
from loopy.observe import MetricsCollector, Span, SpanStatus, Tracer
from loopy.plugins import Plugin, PluginInfo, PluginLoader, PluginRegistry
from loopy.prompting import (
    CANARY_PREFIX,
    build_prompt,
    check_canary,
    make_canary,
    mark_untrusted,
    strip_md_media,
)

# First-party plugins (lazy import to avoid circular deps)
try:
    from loopy.plugins.audio import AudioPlugin, SpeechToText, TextToSpeech
    from loopy.plugins.marketplace import MarketplacePlugin, PluginMarketplace
    from loopy.plugins.memory import Memory, MemoryPlugin, MemoryStore
    from loopy.plugins.rag import Document, RAGPlugin, Retriever
    from loopy.plugins.tools import Tool, ToolResult, ToolsPlugin
except ImportError:
    pass  # Optional dependencies — missing packages are fine

# v0.5.0 — Production readiness modules
# v0.6.0 — Critical gaps: streaming, multi-modal, compliance, explainability, A2A
from loopy._version import __version__
from loopy.a2a import (
    A2AClient,
    AgentCapability,
    AgentCard,
    AgentRegistry,
    AgentRequest,
    AgentResponse,
)
from loopy.audit import AuditReport, CheckItem, LoopAuditor, ReadinessLevel
from loopy.compliance import (
    AuditEntry,
    AuditLogger,
    ComplianceChecker,
    ComplianceFramework,
    DataClassification,
)
from loopy.cost import BudgetExceeded, CostReport, CostTracker
from loopy.drift import DriftDetector, DriftIssue, DriftReport
from loopy.explainability import DecisionStep, DecisionTrace, DecisionTracker, DecisionType
from loopy.multimodal import MediaContent, MediaType, MultiModalBuilder, MultiModalMessage
from loopy.observe import TraceExporter
from loopy.patterns import LoopPattern, PatternCadence, PatternRegistry, RiskLevel
from loopy.safety import EscalationReason, SafetyCheck, SafetyGate, SafetyResult
from loopy.skills import Skill, SkillRegistry
from loopy.state import LoopState, RunOutcome, RunRecord, StateManager
from loopy.streaming import StreamBuffer, StreamChunk, Streamer, StreamEvent
from loopy.verification import VerificationGate, VerificationStatus, VerifyResult

__all__ = [
    # Version
    "__version__",
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
    "MCPToolResult",
    "MCPTool",
    "LocalMCP",
    # Security helpers (v0.7.1)
    "is_private_host",
    "validate_outbound_url",
    "CANARY_PREFIX",
    "make_canary",
    "check_canary",
    "mark_untrusted",
    "build_prompt",
    "strip_md_media",
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
    # A2A
    "AgentCard",
    "AgentRegistry",
    "A2AClient",
    "AgentRequest",
    "AgentResponse",
    "AgentCapability",
    # Compliance
    "ComplianceFramework",
    "DataClassification",
    "AuditEntry",
    "AuditLogger",
    "ComplianceChecker",
    # Explainability
    "DecisionType",
    "DecisionStep",
    "DecisionTrace",
    "DecisionTracker",
    # Multi-modal
    "MediaType",
    "MediaContent",
    "MultiModalMessage",
    "MultiModalBuilder",
    # Streaming
    "StreamEvent",
    "StreamChunk",
    "StreamBuffer",
    "Streamer",
]
