"""Generate ``llms-full.txt`` and per-module ``llms-*.txt`` files.

These text dumps are designed for AI coding assistants (Cursor,
Claude Code, Continue, Aider, Cody, etc.) and LLM-assisted doc tools
that need a single-file ingest of the public API surface. The pattern
is borrowed from LlamaIndex and Atomic Agents.

Usage::

    python scripts/generate_llms_txt.py            # writes llms-full.txt + llms-*.txt
    python scripts/generate_llms_txt.py --out docs # writes into ./docs instead

The script is intentionally dependency-free (no ``loopy`` import) so
it can run in CI without installing the package. It uses
``inspect.getsource`` against the installed package to read each
module's docstring + class/function signatures.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

# Hard-coded import map so this script doesn't depend on loopy being importable.
# (Same set lives in ``loopy/__init__.py`` - kept in sync manually for now.)
PUBLIC_MODULES: dict[str, list[str]] = {
    "loopy": sorted(  # Top-level __all__ entries (just the names that are exported)
        [
            "AgentLoop", "LoopConfig", "StepResult", "StepStatus",
            "Node", "Edge", "StateGraph", "Context", "Workflow", "State",
            "Gateway", "GatewayResponse", "ModelProvider", "ProviderConfig",
            "ConnectionPool", "TestModel", "TEST_MODEL_SENTINEL",
            "GuardrailPipeline", "InputFilter", "OutputFilter", "FilterAction",
            "EvalSuite", "EvalCase", "EvalResult", "EvalReport",
            "Evaluator", "EvalGate", "EvalGateResult", "EvalGateType",
            "JudgeConfig", "Verdict",
            "LLMCache", "CacheStats",
            "Tracer", "Span", "SpanStatus", "MetricsCollector",
            "Redactor", "RedactionMatch",
            "MCPClient", "MCPToolResult", "LocalMCP", "MCPTool",
            "Orchestrator", "Router", "TaskDecomposer",
            "Pipeline", "RetryMiddleware", "CircuitBreakerMiddleware",
            "FallbackMiddleware", "CacheMiddleware", "LoggingMiddleware",
            "TimingMiddleware", "ValidationMiddleware", "RateLimitMiddleware",
            "Plugin", "PluginInfo", "PluginLoader", "PluginRegistry",
            "StateManager", "LoopState", "RunRecord", "RunOutcome",
            "CostTracker", "CostReport", "BudgetExceeded",
            "DriftDetector", "DriftIssue", "DriftReport",
            "Skill", "SkillRegistry",
            "Verifier", "AssertionResult",
            "AuditReport", "CheckItem", "ReadinessLevel",
            "StreamBuffer", "StreamEvent", "StreamChunk",
            "MultiModalMessage", "MultiModalBuilder", "MediaContent",
            "MediaType", "ImageFormat",
            "RealtimeSession", "RealtimeEvent", "RealtimeEventType",
            "RealtimeTransport",
            "ComplianceChecker", "AuditLogger",
            "DecisionTracker", "DecisionTrace", "DecisionStep", "DecisionType",
            "PatternRegistry", "LoopPattern", "PatternCadence", "RiskLevel",
        ]
    ),
    "loopy.loop": ["AgentLoop", "LoopConfig", "StepResult", "StepStatus"],
    "loopy.flow": ["Node", "Edge", "StateGraph", "Context", "Workflow", "State"],
    "loopy.gateway": [
        "Gateway", "GatewayResponse", "ModelProvider", "ProviderConfig",
        "ConnectionPool", "TestModel", "TEST_MODEL_SENTINEL",
    ],
    "loopy.guardrails": [
        "GuardrailPipeline", "InputFilter", "OutputFilter", "FilterAction",
    ],
    "loopy.evals": [
        "EvalSuite", "EvalCase", "EvalResult", "EvalReport",
        "Evaluator", "EvalGate", "EvalGateResult", "EvalGateType",
        "JudgeConfig", "Verdict",
    ],
    "loopy.cache": ["LLMCache", "CacheStats"],
    "loopy.observe": [
        "Tracer", "Span", "SpanStatus", "MetricsCollector",
        "Redactor", "RedactionMatch",
    ],
    "loopy.mcp": ["MCPClient", "MCPToolResult", "LocalMCP", "MCPTool"],
    "loopy.agents": ["Orchestrator", "Router", "TaskDecomposer"],
    "loopy.middleware": [
        "Pipeline", "RetryMiddleware", "CircuitBreakerMiddleware",
        "FallbackMiddleware", "CacheMiddleware", "LoggingMiddleware",
        "TimingMiddleware", "ValidationMiddleware", "RateLimitMiddleware",
    ],
    "loopy.plugins": ["Plugin", "PluginInfo", "PluginLoader", "PluginRegistry"],
    "loopy.state": ["StateManager", "LoopState", "RunRecord", "RunOutcome"],
    "loopy.safety": ["SafetyGate", "SafetyCheck", "SafetyResult", "EscalationReason"],
    "loopy.cost": ["CostTracker", "CostReport", "BudgetExceeded"],
    "loopy.drift": ["DriftDetector", "DriftIssue", "DriftReport"],
    "loopy.skills": ["Skill", "SkillRegistry"],
    "loopy.verification": ["Verifier", "AssertionResult"],
    "loopy.audit": ["AuditReport", "CheckItem", "ReadinessLevel"],
    "loopy.streaming": ["StreamBuffer", "StreamEvent", "StreamChunk"],
    "loopy.multimodal": [
        "MultiModalMessage", "MultiModalBuilder", "MediaContent", "MediaType",
        "ImageFormat", "RealtimeSession", "RealtimeEvent",
        "RealtimeEventType", "RealtimeTransport",
    ],
    "loopy.compliance": ["ComplianceChecker", "AuditLogger"],
    "loopy.explainability": [
        "DecisionTracker", "DecisionTrace", "DecisionStep", "DecisionType",
    ],
    "loopy.patterns": [
        "PatternRegistry", "LoopPattern", "PatternCadence", "RiskLevel",
    ],
}


def _safe_doc(obj: object) -> str:
    """Return ``obj``'s docstring or a placeholder."""
    doc = inspect.getdoc(obj) or ""
    return doc.strip() or "(no docstring)"


def _format_symbol(mod_name: str, sym_name: str) -> str:
    """Format a single public symbol's source as plain text."""
    try:
        mod = __import__(mod_name, fromlist=[sym_name])
    except Exception as e:
        return f"## {sym_name}\n\n> Could not import `{mod_name}.{sym_name}`: {e}\n"
    sym = getattr(mod, sym_name, None)
    if sym is None:
        return f"## {sym_name}\n\n> Not exported by `{mod_name}`.\n"

    header = f"## `{mod_name}.{sym_name}`"
    if inspect.isclass(sym):
        header += f" (class)"
    elif callable(sym):
        header += f" (callable)"

    doc = _safe_doc(sym)
    try:
        src = inspect.getsource(sym)
    except (OSError, TypeError):
        src = "(source unavailable)"

    return f"{header}\n\n{doc}\n\n```python\n{src}```\n"


def generate_full() -> str:
    """Produce the full ``llms-full.txt`` payload."""
    lines: list[str] = []
    lines.append("# loopy-agent — public API reference for LLM ingestion\n")
    lines.append(
        "Generated by `scripts/generate_llms_txt.py`. This file captures "
        "every public symbol in the `loopy` package along with its "
        "docstring and source signature. Designed for AI coding "
        "assistants (Cursor, Claude Code, Continue, Aider, Cody, etc.) "
        "to ingest as project context.\n"
    )
    lines.append("Format: each symbol is fenced by `# Module` headers and `# Symbol` subheaders.\n")
    lines.append("\n---\n")
    for mod_name, syms in PUBLIC_MODULES.items():
        lines.append(f"\n# Module `{mod_name}`\n")
        for sym in syms:
            lines.append(_format_symbol(mod_name, sym))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate llms-*.txt files")
    parser.add_argument(
        "--out",
        default=".",
        help="output directory (default: project root)",
    )
    parser.add_argument(
        "--prefix",
        default="llms",
        help="output file prefix (default: llms)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    full_path = out_dir / f"{args.prefix}-full.txt"
    full_path.write_text(generate_full(), encoding="utf-8")
    print(f"wrote {full_path} ({full_path.stat().st_size} bytes)")

    for mod_name, syms in PUBLIC_MODULES.items():
        if mod_name == "loopy":
            continue  # skip the top-level bundle in per-file output
        safe_name = mod_name.replace(".", "-")
        per_path = out_dir / f"{args.prefix}-{safe_name}.txt"
        content = "# " + mod_name + "\n\n" + "\n".join(
            _format_symbol(mod_name, sym) for sym in syms
        )
        per_path.write_text(content, encoding="utf-8")
        print(f"wrote {per_path} ({per_path.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())