"""
Patterns — Dynamic workflow patterns for agentic loops.

Extends the static PatternRegistry with executable, composable
workflow patterns: fan-out-and-synthesize, classify-and-act,
adversarial verification, and tournament. Each pattern is a
callable that takes an Orchestrator + input and returns structured
results.

Inspired by claude-agent-sdk's dynamic workflow patterns.
Docs: https://loopy.dev/docs/patterns
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from loopy.agents import AgentResult, AgentStatus, Orchestrator, SubAgent

logger = logging.getLogger("loopy.patterns")


# ---------------------------------------------------------------------------
# Legacy compat: static pattern registry (v1.2)
# ---------------------------------------------------------------------------


class PatternCadence(str, Enum):
    """How often the static pattern runs."""

    MINUTES_5 = "5m"
    MINUTES_15 = "15m"
    HOURS_1 = "1h"
    HOURS_6 = "6h"
    DAILY = "1d"


class RiskLevel(str, Enum):
    """Risk level of the pattern."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class LoopPattern:
    """A reusable loop pattern template."""

    name: str
    description: str
    cadence: PatternCadence
    risk: RiskLevel
    readiness_level: str  # L1, L2, or L3

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "cadence": self.cadence.value,
            "risk": self.risk.value,
            "readiness_level": self.readiness_level,
        }


class _LegacyPatternRegistry:
    """Backward-compatible static pattern registry."""

    def __init__(self) -> None:
        self._patterns: dict[str, LoopPattern] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        builtins = [
            LoopPattern(
                name="daily-triage",
                description="Triage issues and PRs on a daily cadence",
                cadence=PatternCadence.DAILY,
                risk=RiskLevel.LOW,
                readiness_level="L1",
            ),
            LoopPattern(
                name="pr-babysitter",
                description="Monitor and respond to PR events",
                cadence=PatternCadence.MINUTES_15,
                risk=RiskLevel.MEDIUM,
                readiness_level="L1",
            ),
            LoopPattern(
                name="ci-sweeper",
                description="Sweep CI failures and create fixes",
                cadence=PatternCadence.MINUTES_15,
                risk=RiskLevel.MEDIUM,
                readiness_level="L2",
            ),
            LoopPattern(
                name="dependency-sweeper",
                description="Check and update dependencies",
                cadence=PatternCadence.HOURS_6,
                risk=RiskLevel.MEDIUM,
                readiness_level="L2",
            ),
            LoopPattern(
                name="changelog-drafter",
                description="Draft changelog from commits",
                cadence=PatternCadence.DAILY,
                risk=RiskLevel.LOW,
                readiness_level="L1",
            ),
            LoopPattern(
                name="post-merge-cleanup",
                description="Clean up after merges",
                cadence=PatternCadence.HOURS_6,
                risk=RiskLevel.LOW,
                readiness_level="L1",
            ),
            LoopPattern(
                name="issue-triage",
                description="Triage new issues",
                cadence=PatternCadence.HOURS_1,
                risk=RiskLevel.LOW,
                readiness_level="L1",
            ),
        ]
        for p in builtins:
            self._patterns[p.name] = p

    def get(self, name: str) -> LoopPattern | None:
        return self._patterns.get(name)

    def list_all(self) -> list[LoopPattern]:
        return list(self._patterns.values())

    def list_by_risk(self, risk: RiskLevel) -> list[LoopPattern]:
        return [p for p in self._patterns.values() if p.risk == risk]

    def list_by_cadence(self, cadence: PatternCadence) -> list[LoopPattern]:
        return [p for p in self._patterns.values() if p.cadence == cadence]


# Re-export the legacy registry as PatternRegistry for backwards compat.
PatternRegistry = _LegacyPatternRegistry


class PatternType(str, Enum):
    """Built-in workflow pattern identifiers."""

    FAN_OUT_SYNTHESIZE = "fan_out_synthesize"
    CLASSIFY_AND_ACT = "classify_and_act"
    ADVERSARIAL_VERIFICATION = "adversarial_verification"
    TOURNAMENT = "tournament"


@dataclass
class PatternResult:
    """Result from a dynamic workflow pattern execution."""

    pattern: PatternType
    input: str
    results: list[AgentResult] = field(default_factory=list)
    synthesized: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "input": self.input,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "synthesized": self.synthesized,
            "result_count": len(self.results),
        }


class WorkflowPattern(Protocol):
    """Interface for all dynamic workflow patterns."""

    pattern_type: PatternType

    async def run(
        self,
        orchestrator: Orchestrator,
        input: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> PatternResult: ...


# ---------------------------------------------------------------------------
# Fan-out-and-synthesize
# ---------------------------------------------------------------------------


class FanOutSynthesize:
    """Fan-out pattern: run multiple agents in parallel, synthesize results.

    Spawns every registered agent with the same input, collects all
    outputs, then synthesizes them into a single consolidated response.
    """

    pattern_type = PatternType.FAN_OUT_SYNTHESIZE

    def __init__(
        self,
        synthesizer: Any | None = None,
        max_fans: int = 10,
    ) -> None:
        self._synthesizer = synthesizer
        self.max_fans = max_fans

    async def run(
        self,
        orchestrator: Orchestrator,
        input: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> PatternResult:
        agents = orchestrator.list_agents()[: self.max_fans]
        if not agents:
            return PatternResult(
                pattern=self.pattern_type,
                input=input,
                success=False,
                error="No agents registered with the orchestrator",
            )

        start = time.monotonic()
        tasks = [orchestrator.run(input, agent_name=a.name, context=context or {}) for a in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        parsed: list[AgentResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                agent_name = agents[i].name if i < len(agents) else f"agent_{i}"
                parsed.append(
                    AgentResult(
                        agent_name=agent_name,
                        status=AgentStatus.FAILED,
                        error=str(r),
                        duration_ms=elapsed_ms / max(len(agents), 1),
                    )
                )
            else:
                parsed.append(r)

        synthesized = ""
        if self._synthesizer is not None:
            try:
                synthesized = await self._synthesizer(parsed)
            except Exception as e:
                logger.warning("Synthesis failed: %s", e)
                synthesized = ""

        all_success = all(r.status == AgentStatus.COMPLETED for r in parsed)
        return PatternResult(
            pattern=self.pattern_type,
            input=input,
            results=parsed,
            synthesized=synthesized,
            duration_ms=elapsed_ms,
            success=all_success,
        )


# ---------------------------------------------------------------------------
# Classify-and-act
# ---------------------------------------------------------------------------


class ClassifyAndAct:
    """Classify-and-act pattern: route each sub-request to the best agent.

    Uses the orchestrator's Router to classify the input, dispatches
    to the matched agent, and collects per-class results.
    """

    pattern_type = PatternType.CLASSIFY_AND_ACT

    def __init__(self, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence

    async def run(
        self,
        orchestrator: Orchestrator,
        input: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> PatternResult:
        start = time.monotonic()
        try:
            agent_name = await orchestrator.route(input)
        except Exception as e:
            elapsed = round((time.monotonic() - start) * 1000, 2)
            return PatternResult(
                pattern=self.pattern_type,
                input=input,
                success=False,
                error=f"Routing failed: {e}",
                duration_ms=elapsed,
            )

        result = await orchestrator.run(input, agent_name=agent_name, context=context or {})
        elapsed = round((time.monotonic() - start) * 1000, 2)
        return PatternResult(
            pattern=self.pattern_type,
            input=input,
            results=[result],
            synthesized=result.output if result.status == AgentStatus.COMPLETED else "",
            duration_ms=elapsed,
            success=result.status == AgentStatus.COMPLETED,
            error=result.error,
        )


# ---------------------------------------------------------------------------
# Adversarial verification
# ---------------------------------------------------------------------------


class AdversarialVerification:
    """Adversarial verification pattern: agent produces output, critic challenges it.

    Runs the primary agent, then runs any registered 'critic' agents
    to challenge the output. Returns both the primary result and
    adversarial feedback.
    """

    pattern_type = PatternType.ADVERSARIAL_VERIFICATION

    def __init__(self, critic_label: str = "critic") -> None:
        self.critic_label = critic_label

    async def run(
        self,
        orchestrator: Orchestrator,
        input: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> PatternResult:
        start = time.monotonic()

        # Run primary agent (first registered, or the one matching the input).
        primary = await orchestrator.run(input, context=context or {})
        if primary.status != AgentStatus.COMPLETED:
            elapsed = round((time.monotonic() - start) * 1000, 2)
            return PatternResult(
                pattern=self.pattern_type,
                input=input,
                results=[primary],
                success=False,
                error=primary.error,
                duration_ms=elapsed,
            )

        # Run critic(s).
        critics = [a for a in orchestrator.list_agents() if self.critic_label in a.name.lower()]
        critic_tasks = [
            orchestrator.run(
                (
                    "Review and critique the following output for errors, "
                    "bias, or missing information:\n\n"
                    f"{primary.output}"
                ),
                agent_name=c.name,
                context=context or {},
            )
            for c in critics
        ]
        critic_results = (
            await asyncio.gather(*critic_tasks, return_exceptions=True) if critics else []
        )

        all_critics_ok: list[AgentResult] = []
        for i, cr in enumerate(critic_results):
            if isinstance(cr, Exception):
                all_critics_ok.append(
                    AgentResult(
                        agent_name=critics[i].name if i < len(critics) else "critic",
                        status=AgentStatus.FAILED,
                        error=str(cr),
                    )
                )
            else:
                all_critics_ok.append(cr)

        # Build synthesized output: primary + critic feedback.
        synthesized_lines = [primary.output]
        for cr in all_critics_ok:
            if cr.status == AgentStatus.COMPLETED and cr.output:
                synthesized_lines.append(f"\n[{cr.agent_name}] Feedback: {cr.output}")

        synthesized = "\n---\n".join(synthesized_lines)
        elapsed = round((time.monotonic() - start) * 1000, 2)
        return PatternResult(
            pattern=self.pattern_type,
            input=input,
            results=[primary, *all_critics_ok],
            synthesized=synthesized,
            duration_ms=elapsed,
            success=True,
        )


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------


class Tournament:
    """Tournament pattern: pairwise agent comparison, winner advances.

    Pairs up agents, runs each on the input, and keeps the one with
    the shorter (or otherwise preferred) result. Repeats until one
    agent remains.
    """

    pattern_type = PatternType.TOURNAMENT

    def __init__(
        self,
        prefer_shorter: bool = True,
        max_rounds: int = 5,
    ) -> None:
        self.prefer_shorter = prefer_shorter
        self.max_rounds = max_rounds

    async def run(
        self,
        orchestrator: Orchestrator,
        input: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> PatternResult:
        agents = orchestrator.list_agents()
        if len(agents) < 2:
            single = agents[0] if agents else None
            if single:
                result = await orchestrator.run(
                    input, agent_name=single.name, context=context or {}
                )
                return PatternResult(
                    pattern=self.pattern_type,
                    input=input,
                    results=[result],
                    synthesized=result.output if result.status == AgentStatus.COMPLETED else "",
                    success=result.status == AgentStatus.COMPLETED,
                    error=result.error,
                )
            return PatternResult(
                pattern=self.pattern_type,
                input=input,
                success=False,
                error="Need at least 2 agents for a tournament",
            )

        start = time.monotonic()
        round_num = 0
        contenders: list[SubAgent] = list(agents)

        while len(contenders) > 1 and round_num < self.max_rounds:
            round_num += 1
            next_contenders: list[SubAgent] = []

            for i in range(0, len(contenders) - 1, 2):
                a, b = contenders[i], contenders[i + 1]
                ra = await orchestrator.run(input, agent_name=a.name, context=context or {})
                rb = await orchestrator.run(input, agent_name=b.name, context=context or {})

                winner = self._pick_winner(ra, rb)
                winner_agent = a if winner is ra else b
                next_contenders.append(winner_agent)

            if len(contenders) % 2 == 1:
                next_contenders.append(contenders[-1])

            contenders = next_contenders

        elapsed = round((time.monotonic() - start) * 1000, 2)
        final_agent = contenders[0] if contenders else None
        if final_agent is None:
            return PatternResult(
                pattern=self.pattern_type,
                input=input,
                success=False,
                error="No agents remained after tournament",
                duration_ms=elapsed,
            )

        final_result = await orchestrator.run(
            input, agent_name=final_agent.name, context=context or {}
        )
        return PatternResult(
            pattern=self.pattern_type,
            input=input,
            results=[final_result],
            synthesized=final_result.output if final_result.status == AgentStatus.COMPLETED else "",
            duration_ms=elapsed,
            success=final_result.status == AgentStatus.COMPLETED,
            error=final_result.error,
        )

    def _pick_winner(self, ra: AgentResult, rb: AgentResult) -> AgentResult:
        if ra.status != AgentStatus.COMPLETED and rb.status != AgentStatus.COMPLETED:
            return ra
        if rb.status != AgentStatus.COMPLETED:
            return ra
        if ra.status != AgentStatus.COMPLETED:
            return rb
        if self.prefer_shorter:
            return ra if len(ra.output or "") <= len(rb.output or "") else rb
        return ra


# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------


class DynamicPatternRegistry:
    """Registry and executor for dynamic workflow patterns."""

    def __init__(self) -> None:
        self._patterns: dict[PatternType, WorkflowPattern] = {
            PatternType.FAN_OUT_SYNTHESIZE: FanOutSynthesize(),
            PatternType.CLASSIFY_AND_ACT: ClassifyAndAct(),
            PatternType.ADVERSARIAL_VERIFICATION: AdversarialVerification(),
            PatternType.TOURNAMENT: Tournament(),
        }

    def register(self, pattern: WorkflowPattern) -> None:
        self._patterns[pattern.pattern_type] = pattern

    def get(self, pattern_type: PatternType) -> WorkflowPattern | None:
        return self._patterns.get(pattern_type)

    def list_all(self) -> list[PatternType]:
        return list(self._patterns.keys())

    async def run(
        self,
        pattern_type: PatternType,
        orchestrator: Orchestrator,
        input: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> PatternResult:
        pattern = self._patterns.get(pattern_type)
        if pattern is None:
            return PatternResult(
                pattern=pattern_type,
                input=input,
                success=False,
                error=f"Unknown pattern: {pattern_type.value}",
            )
        return await pattern.run(orchestrator, input, context=context)
