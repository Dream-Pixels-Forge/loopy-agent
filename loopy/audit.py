"""
Audit — Loop Readiness Scoring.

Score agent loops 0-100 for production readiness.
Inspired by loop-engineering's Loop Ready Score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("loopy.audit")


class ReadinessLevel(str, Enum):
    """Loop readiness levels."""

    L0 = "L0"  # 0-29: Draft
    L1 = "L1"  # 30-59: Report only
    L2 = "L2"  # 60-79: Assisted fixes
    L3 = "L3"  # 80-100: Unattended

    @classmethod
    def from_score(cls, score: int) -> ReadinessLevel:
        """Derive readiness level from score."""
        if score < 30:
            return cls.L0
        if score < 60:
            return cls.L1
        if score < 80:
            return cls.L2
        return cls.L3


@dataclass
class CheckItem:
    """A single audit check."""

    name: str
    passed: bool
    weight: int
    description: str

    @property
    def score(self) -> int:
        return self.weight if self.passed else 0


@dataclass
class AuditReport:
    """Full audit report with score and suggestions."""

    score: int
    level: ReadinessLevel
    checks: list[CheckItem]
    suggestions: list[str]

    def summary(self) -> dict[str, Any]:
        """Return summary dict."""
        return {
            "score": self.score,
            "level": self.level.value,
            "passed": sum(1 for c in self.checks if c.passed),
            "failed": sum(1 for c in self.checks if not c.passed),
            "total": len(self.checks),
            "suggestions": self.suggestions,
        }


class LoopAuditor:
    """
    Audit agent loops for production readiness.

    Scores loops 0-100 based on 10 checklist categories.
    Inspired by loop-engineering's Loop Ready Score.

    Example:
        auditor = LoopAuditor()
        report = await auditor.audit(loop_config)
        print(f"Score: {report.score}/100 ({report.level.value})")
    """

    CHECKS = [
        ("single_goal", "Loop has a single clear goal", 5),
        ("planner", "Has planner callback", 10),
        ("actor", "Has actor callback", 10),
        ("observer", "Has observer callback", 5),
        ("reflector", "Has reflector callback", 5),
        ("max_steps", "Has reasonable max_steps (1-20)", 5),
        ("error_handling", "Has stop_on_error configured", 5),
        ("state_path", "Has state persistence path", 10),
        ("budget_limit", "Has token budget limit", 10),
        ("verification", "Has verification/test function", 10),
        ("skills", "Has skills loaded", 5),
        ("safety", "Has safety denylist configured", 5),
        ("logging", "Has logging configured", 5),
    ]

    async def audit(self, config: dict[str, Any]) -> AuditReport:
        """
        Audit a loop configuration.

        Args:
            config: Loop configuration dict (LoopConfig fields + extras)

        Returns:
            AuditReport with score 0-100
        """
        checks: list[CheckItem] = []
        suggestions: list[str] = []

        # Check: Single goal
        has_goal = bool(config.get("goal") or config.get("description"))
        checks.append(
            CheckItem(
                name="single_goal",
                passed=has_goal,
                weight=5,
                description="Loop has a single clear goal",
            )
        )
        if not has_goal:
            suggestions.append("Add a 'goal' or 'description' to define the loop's purpose")

        # Check: Planner
        has_planner = config.get("planner") is not None
        checks.append(
            CheckItem(
                name="planner",
                passed=has_planner,
                weight=10,
                description="Has planner callback",
            )
        )
        if not has_planner:
            suggestions.append("Add a planner callback for Plan→Act→Observe→Reflect cycle")

        # Check: Actor
        has_actor = config.get("actor") is not None
        checks.append(
            CheckItem(
                name="actor",
                passed=has_actor,
                weight=10,
                description="Has actor callback",
            )
        )
        if not has_actor:
            suggestions.append("Add an actor callback to execute planned actions")

        # Check: Observer
        has_observer = config.get("observer") is not None
        checks.append(
            CheckItem(
                name="observer",
                passed=has_observer,
                weight=5,
                description="Has observer callback",
            )
        )
        if not has_observer:
            suggestions.append("Add an observer callback to observe action results")

        # Check: Reflector
        has_reflector = config.get("reflector") is not None
        checks.append(
            CheckItem(
                name="reflector",
                passed=has_reflector,
                weight=5,
                description="Has reflector callback",
            )
        )
        if not has_reflector:
            suggestions.append("Add a reflector callback to reflect on progress")

        # Check: Max steps
        max_steps = config.get("max_steps", 0)
        has_valid_steps = 1 <= max_steps <= 20
        checks.append(
            CheckItem(
                name="max_steps",
                passed=has_valid_steps,
                weight=5,
                description="Has reasonable max_steps (1-20)",
            )
        )
        if not has_valid_steps:
            suggestions.append("Set max_steps between 1 and 20")

        # Check: Error handling
        has_error_config = "stop_on_error" in config
        checks.append(
            CheckItem(
                name="error_handling",
                passed=has_error_config,
                weight=5,
                description="Has stop_on_error configured",
            )
        )
        if not has_error_config:
            suggestions.append("Configure stop_on_error for error handling")

        # Check: State path
        has_state = bool(config.get("state_path"))
        checks.append(
            CheckItem(
                name="state_path",
                passed=has_state,
                weight=10,
                description="Has state persistence path",
            )
        )
        if not has_state:
            suggestions.append("Add state_path for durable state across runs")

        # Check: Budget limit
        has_budget = config.get("budget_limit") is not None or config.get("max_tokens") is not None
        checks.append(
            CheckItem(
                name="budget_limit",
                passed=has_budget,
                weight=10,
                description="Has token budget limit",
            )
        )
        if not has_budget:
            suggestions.append("Add budget_limit to control token spending")

        # Check: Verification
        has_verification = config.get("test_fn") is not None or config.get("verifier") is not None
        checks.append(
            CheckItem(
                name="verification",
                passed=has_verification,
                weight=10,
                description="Has verification/test function",
            )
        )
        if not has_verification:
            suggestions.append("Add test_fn or verifier for Maker/Checker pattern")

        # Check: Skills
        has_skills = bool(config.get("skills"))
        checks.append(
            CheckItem(
                name="skills",
                passed=has_skills,
                weight=5,
                description="Has skills loaded",
            )
        )
        if not has_skills:
            suggestions.append("Load skills for persistent agent knowledge")

        # Check: Safety
        has_safety = bool(config.get("denylist_paths"))
        checks.append(
            CheckItem(
                name="safety",
                passed=has_safety,
                weight=5,
                description="Has safety denylist configured",
            )
        )
        if not has_safety:
            suggestions.append("Configure denylist_paths for safety")

        # Check: Logging
        has_logging = config.get("logging") is not None or config.get("log_path") is not None
        checks.append(
            CheckItem(
                name="logging",
                passed=has_logging,
                weight=5,
                description="Has logging configured",
            )
        )
        if not has_logging:
            suggestions.append("Configure logging for observability")

        # Calculate score
        total_weight = sum(c.weight for c in checks)
        earned_weight = sum(c.score for c in checks)
        score = int((earned_weight / total_weight) * 100) if total_weight > 0 else 0

        level = ReadinessLevel.from_score(score)

        return AuditReport(
            score=score,
            level=level,
            checks=checks,
            suggestions=suggestions,
        )
