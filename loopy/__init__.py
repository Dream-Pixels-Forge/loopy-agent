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

# v1.0.0 — the durable runtime's ``Workflow`` (T3.1) shadows the
# graph-flow ``Workflow`` (T1.1) so end-users get the right
# symbol. The flow Workflow is still reachable as
# ``loopy.flow.Workflow``.
import loopy.durable
import loopy.durable as _durable
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
    EvalReport,
    EvalResult,
    EvalSuite,
    Evaluator,
    JudgeConfig,
    Verdict,
)
from loopy.flow import Context, Edge, Node, StateGraph
from loopy.gateway import (
    TEST_MODEL_SENTINEL,
    ConnectionPool,
    Gateway,
    GatewayResponse,
    ModelProvider,
    ProviderConfig,
    TestModel,
)
from loopy.guardrails import FilterAction, GuardrailPipeline, InputFilter, OutputFilter
from loopy.loop import (
    AgentLoop,
    AgentLoopRejected,
    Interrupt,
    LoopConfig,
    StepResult,
    StepStatus,
)
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
from loopy.observe import (
    MetricsCollector,
    RedactionMatch,
    Redactor,
    Span,
    SpanStatus,
    Tracer,
    auto_instrument_gateway,
    auto_instrument_mcp,
    build_otlp_envelope,
    get_default_tracer,
    observe,
    set_default_tracer,
)
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
    A2AError,
    A2ATask,
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
from loopy.durable import DAG, ResumeToken, Step, TestEnv
from loopy.explainability import DecisionStep, DecisionTrace, DecisionTracker, DecisionType
from loopy.federate import AgentCluster, FederatedServer
from loopy.multimodal import (
    MediaContent,
    MediaType,
    MultiModalBuilder,
    MultiModalMessage,
    RealtimeEvent,
    RealtimeEventType,
    RealtimeSession,
    RealtimeTransport,
)
from loopy.observe import TraceExporter
from loopy.patterns import LoopPattern, PatternCadence, PatternRegistry, RiskLevel
from loopy.policies import (
    Condition,
    Policy,
    PolicyDecision,
    PolicyEngine,
    PolicyViolation,
)
from loopy.safety import EscalationReason, SafetyCheck, SafetyGate, SafetyResult
from loopy.skills import Skill, SkillRegistry
from loopy.state import LoopState, RunOutcome, RunRecord, StateManager
from loopy.streaming import StreamBuffer, StreamChunk, Streamer, StreamEvent
from loopy.verification import VerificationGate, VerificationStatus, VerifyResult
from loopy.verifier import (
    Invariant,
    Property,
    VerificationReport,
    VerificationSpec,
    VerifiedAgent,
    output_length_at_most,
    output_must_contain,
)

__all__ = [
    # Version
    "__version__",
    # Agentic Loop
    "AgentLoop",
    "StepResult",
    "LoopConfig",
    "StepStatus",
    "Interrupt",  # v0.8.0
    "AgentLoopRejected",  # v0.8.0
    # Gateway
    "Gateway",
    "ModelProvider",
    "ProviderConfig",
    "GatewayResponse",
    "ConnectionPool",
    "TestModel",  # v0.7.9
    "TEST_MODEL_SENTINEL",  # v0.7.9
    # Guardrails
    "GuardrailPipeline",
    "InputFilter",
    "OutputFilter",
    "FilterAction",
    # v0.8.0 - Graph control flow
    "Node",
    "Edge",
    "StateGraph",
    "Context",
    "Workflow",
    "State",
    # Evals (including v0.2.0 evaluator-optimizer)
    "Evaluator",
    "EvalCase",
    "EvalReport",
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
    "Redactor",  # v0.7.9
    "RedactionMatch",  # v0.7.9
    "observe",  # v0.8.0
    "auto_instrument_gateway",  # v0.8.0
    "auto_instrument_mcp",  # v0.8.0
    "build_otlp_envelope",  # v0.8.0
    "get_default_tracer",  # v0.8.0
    "set_default_tracer",  # v0.8.0
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
    # Policies (v0.9.0)
    "Policy",
    "PolicyEngine",
    "PolicyDecision",
    "PolicyViolation",
    "Condition",
    # Safety
    "SafetyGate",
    "SafetyCheck",
    "SafetyResult",
    "EscalationReason",
    # A2A
    "AgentCard",
    "AgentRegistry",
    "A2AClient",
    "A2AError",  # v0.9.0
    "A2ATask",  # v0.9.0
    "AgentRequest",
    "AgentResponse",
    "AgentCapability",
    # v1.0.0 — durable runtime
    "DAG",
    "Step",
    "State",
    "Workflow",
    "ResumeToken",
    "TestEnv",
    "AgentCluster",
    "FederatedServer",
    # v1.0.0 — verified agents
    "VerifiedAgent",
    "VerificationSpec",
    "VerificationReport",
    "Invariant",
    "Property",
    "output_must_contain",
    "output_length_at_most",
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
    "RealtimeEvent",  # # v0.7.10
    "RealtimeEventType",  # # v0.7.10
    "RealtimeSession",  # # v0.7.10
    "RealtimeTransport",  # # v0.7.10
    # Streaming
    "StreamEvent",
    "StreamChunk",
    "StreamBuffer",
    "Streamer",
]


# v1.0.0 — the durable runtime's ``Workflow`` / ``State`` (T3.1)
# shadow the graph-flow ``Workflow`` / ``State`` (T1.1) so
# end-users get the right symbol from a top-level import. The
# flow ones remain reachable as ``loopy.flow.Workflow`` /
# ``loopy.flow.State`` for backwards compatibility.

Workflow = _durable.Workflow
State = _durable.State
