"""
Safety — Production Safety Gates.

Denylist paths, escalation triggers, human gates.
Inspired by loop-engineering's safety patterns.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("loopy.safety")


class EscalationReason(str, Enum):
    """Why escalation is needed."""

    MAX_ATTEMPTS = "max_attempts"
    DENYLIST_PATH = "denylist_path"
    LOW_CONFIDENCE = "low_confidence"
    AMBIGUOUS_INPUT = "ambiguous_input"


@dataclass
class SafetyCheck:
    """Result of a single safety check."""

    name: str
    passed: bool
    reason: str = ""
    escalation: EscalationReason | None = None


@dataclass
class SafetyResult:
    """Overall safety check result."""

    safe: bool
    checks: list[SafetyCheck]
    should_escalate: bool = False


class SafetyGate:
    """
    Production safety checks for agent loops.

    Example:
        gate = SafetyGate(denylist_paths=["secrets/*", ".env*"])
        result = await gate.check(path="src/main.py", attempts=1, confidence=0.9)
        if result.safe:
            proceed()
    """

    DEFAULT_DENYLIST = [
        "src/auth/*",
        "src/payments/*",
        ".env*",
        "secrets/*",
        "*.pem",
        "*.key",
        "credentials/*",
    ]

    def __init__(
        self,
        denylist_paths: list[str] | None = None,
        max_attempts: int = 3,
        human_gate_threshold: float = 0.7,
    ):
        self.denylist_paths = denylist_paths or self.DEFAULT_DENYLIST
        self.max_attempts = max_attempts
        self.human_gate_threshold = human_gate_threshold

    async def check_path(self, path: str) -> SafetyCheck:
        """Check if path is in denylist."""
        for pattern in self.denylist_paths:
            if fnmatch.fnmatch(path, pattern):
                return SafetyCheck(
                    name="path_check",
                    passed=False,
                    reason=f"Path in denylist: {pattern}",
                    escalation=EscalationReason.DENYLIST_PATH,
                )

        return SafetyCheck(
            name="path_check",
            passed=True,
            reason="Path not in denylist",
        )

    def should_escalate(self, attempts: int, confidence: float, path_safe: bool = True) -> bool:
        """Determine if human escalation is needed."""
        if not path_safe:
            return True
        if attempts >= self.max_attempts:
            return True
        return confidence < self.human_gate_threshold

    async def check(
        self,
        path: str | None = None,
        attempts: int = 0,
        confidence: float = 1.0,
    ) -> SafetyResult:
        """
        Full safety check.

        Args:
            path: File path to check
            attempts: Number of attempts so far
            confidence: Confidence score (0-1)

        Returns:
            SafetyResult with safety status
        """
        checks: list[SafetyCheck] = []

        # Path check
        if path:
            path_check = await self.check_path(path)
            checks.append(path_check)

        # Attempt check
        attempts_ok = attempts < self.max_attempts
        checks.append(
            SafetyCheck(
                name="attempts_check",
                passed=attempts_ok,
                reason=f"Attempts: {attempts}/{self.max_attempts}",
            )
        )

        # Confidence check
        confidence_ok = confidence >= self.human_gate_threshold
        checks.append(
            SafetyCheck(
                name="confidence_check",
                passed=confidence_ok,
                reason=f"Confidence: {confidence:.2f} (threshold: {self.human_gate_threshold})",
            )
        )

        path_safe = all(c.passed for c in checks if c.name == "path_check")
        safe = all(c.passed for c in checks)
        should_escalate = self.should_escalate(attempts, confidence, path_safe)

        return SafetyResult(
            safe=safe,
            checks=checks,
            should_escalate=should_escalate,
        )
