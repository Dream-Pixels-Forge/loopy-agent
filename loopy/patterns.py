"""
Patterns — Production Loop Patterns.

Built-in patterns inspired by loop-engineering's 7 production patterns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("loopy.patterns")


class PatternCadence(str, Enum):
    """How often the pattern runs."""

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


class PatternRegistry:
    """
    Built-in production patterns.

    Example:
        registry = PatternRegistry()
        patterns = registry.list_all()
        daily = registry.get("daily-triage")
    """

    def __init__(self):
        self._patterns: dict[str, LoopPattern] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in patterns."""
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

        for pattern in builtins:
            self._patterns[pattern.name] = pattern

    def get(self, name: str) -> LoopPattern | None:
        """Get pattern by name."""
        return self._patterns.get(name)

    def list_all(self) -> list[LoopPattern]:
        """List all patterns."""
        return list(self._patterns.values())

    def list_by_risk(self, risk: RiskLevel) -> list[LoopPattern]:
        """List patterns by risk level."""
        return [p for p in self._patterns.values() if p.risk == risk]

    def list_by_cadence(self, cadence: PatternCadence) -> list[LoopPattern]:
        """List patterns by cadence."""
        return [p for p in self._patterns.values() if p.cadence == cadence]
