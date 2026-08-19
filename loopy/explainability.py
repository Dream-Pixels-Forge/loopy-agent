"""
Explainability — Full decision audit trail.

Why did the agent make this decision?
Critical gap: 2026 agents must explain their reasoning.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger("loopy.explainability")


class DecisionType(str, Enum):
    """Types of agent decisions."""
    PLAN = "plan"
    ACTION = "action"
    TOOL_USE = "tool_use"
    ROUTE = "route"
    ESCALATE = "escalate"
    STOP = "stop"
    RETRY = "retry"


@dataclass
class DecisionStep:
    """A single decision in the reasoning chain."""
    type: DecisionType
    reasoning: str
    input_summary: str
    output_summary: str
    confidence: float = 1.0
    alternatives: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "reasoning": self.reasoning,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class DecisionTrace:
    """Full trace of agent decision-making."""
    task: str
    steps: list[DecisionStep] = field(default_factory=list)
    final_output: str = ""
    total_time_ms: float = 0
    success: bool = True

    def add_step(self, step: DecisionStep) -> None:
        self.steps.append(step)

    @property
    def summary(self) -> str:
        """Human-readable summary of decision chain."""
        lines = [f"Task: {self.task}"]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"  {i}. [{step.type.value}] {step.reasoning}")
        lines.append(f"Output: {self.final_output[:100]}...")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "final_output": self.final_output,
            "total_time_ms": self.total_time_ms,
            "success": self.success,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class DecisionTracker:
    """
    Track and explain agent decisions.

    Example:
        tracker = DecisionTracker(max_traces=100)
        trace = tracker.start("Summarize document")
        tracker.add_step(trace, DecisionType.PLAN, "Will extract key points")
        # ... agent works ...
        tracker.finish(trace, "Summary complete")
        print(trace.summary)
    """

    def __init__(self, max_traces: int = 100):
        self.traces: list[DecisionTrace] = []
        self._max_traces = max_traces

    def start(self, task: str) -> DecisionTrace:
        """Start tracking a new task."""
        trace = DecisionTrace(task=task)
        self.traces.append(trace)

        # Evict oldest when at capacity
        if len(self.traces) > self._max_traces:
            evicted = self.traces.pop(0)
            logger.debug("Evicted old trace: %s", evicted.task)

        return trace

    def add_step(
        self,
        trace: DecisionTrace,
        type: DecisionType,
        reasoning: str,
        input_summary: str = "",
        output_summary: str = "",
        confidence: float = 1.0,
        alternatives: list[str] | None = None,
        **metadata: Any,
    ) -> DecisionStep:
        """Add a decision step to the trace."""
        step = DecisionStep(
            type=type,
            reasoning=reasoning,
            input_summary=input_summary,
            output_summary=output_summary,
            confidence=confidence,
            alternatives=alternatives or [],
            metadata=metadata,
        )
        trace.add_step(step)
        return step

    def finish(self, trace: DecisionTrace, output: str, success: bool = True) -> None:
        """Finish tracking a task."""
        trace.final_output = output
        trace.success = success

    def explain(self, trace: DecisionTrace) -> str:
        """Generate human-readable explanation."""
        lines = [
            f"## Decision Trace: {trace.task}",
            "",
            "### Reasoning Chain:",
        ]

        for i, step in enumerate(trace.steps, 1):
            lines.append(f"\n**Step {i}: {step.type.value}**")
            lines.append(f"- Reasoning: {step.reasoning}")
            if step.alternatives:
                lines.append(f"- Alternatives considered: {', '.join(step.alternatives)}")
            lines.append(f"- Confidence: {step.confidence:.0%}")

        lines.extend([
            "",
            "### Final Output:",
            trace.final_output[:500],
            "",
            "### Stats:",
            f"- Steps: {len(trace.steps)}",
            f"- Time: {trace.total_time_ms:.0f}ms",
            f"- Success: {'✅' if trace.success else '❌'}",
        ])

        return "\n".join(lines)

    def export(self, trace: DecisionTrace, path: str) -> None:
        """Export a decision trace to a JSON file.

        Args:
            trace: The DecisionTrace to export.
            path: Destination file path.
        """
        from pathlib import Path
        Path(path).write_text(trace.to_json())
