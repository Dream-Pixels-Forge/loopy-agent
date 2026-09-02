"""
Drift — Config/State Drift Detection.

Detect drift between loop configuration and runtime state.
Inspired by loop-engineering's loop-sync tool.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("loopy.drift")


@dataclass
class DriftIssue:
    """A single drift issue."""

    component: str
    expected: str
    actual: str
    severity: str = "warning"  # "warning" or "error"


@dataclass
class DriftReport:
    """Report of drift between config and state."""

    drifted: bool
    issues: list[DriftIssue]
    suggestions: list[str]

    def summary(self) -> dict[str, Any]:
        return {
            "drifted": self.drifted,
            "error_count": sum(1 for i in self.issues if i.severity == "error"),
            "warning_count": sum(1 for i in self.issues if i.severity == "warning"),
            "issues": [
                {"component": i.component, "expected": i.expected, "actual": i.actual}
                for i in self.issues
            ],
            "suggestions": self.suggestions,
        }


class DriftDetector:
    """
    Detect drift between config and state.

    Example:
        detector = DriftDetector()
        report = await detector.check(config, state)
        if report.drifted:
            print(f"Drift detected: {len(report.issues)} issues")
    """

    async def check(
        self,
        config: dict[str, Any],
        state: dict[str, Any],
    ) -> DriftReport:
        """
        Check for drift between config and state.

        Args:
            config: Loop configuration
            state: Runtime state

        Returns:
            DriftReport with any drift issues found
        """
        issues: list[DriftIssue] = []
        suggestions: list[str] = []

        # Check max_steps drift
        config_max = config.get("max_steps")
        state_max = state.get("max_steps")
        if config_max is not None and state_max is not None and config_max != state_max:
            issues.append(
                DriftIssue(
                    component="max_steps",
                    expected=str(config_max),
                    actual=str(state_max),
                    severity="error",
                )
            )
            suggestions.append(f"Align max_steps: config={config_max}, state={state_max}")

        # Check attempts vs max
        attempts = state.get("attempts", 0)
        max_attempts = config.get("max_attempts") or state.get("max_attempts", 5)
        if attempts >= max_attempts:
            issues.append(
                DriftIssue(
                    component="attempts",
                    expected=f"< {max_attempts}",
                    actual=str(attempts),
                    severity="warning",
                )
            )
            suggestions.append(
                f"Reset attempts or increase max_attempts (currently {attempts}/{max_attempts})"
            )

        # Check required callbacks
        for callback in ["planner", "actor", "observer", "reflector"]:
            if config.get(callback) is not None and callback not in state:
                issues.append(
                    DriftIssue(
                        component=callback,
                        expected="present in state",
                        actual="missing from state",
                        severity="warning",
                    )
                )
                suggestions.append(f"Register callback '{callback}' in state for tracking")

        # Check state has required fields
        required_fields = ["current_task", "attempts", "history"]
        for field_name in required_fields:
            if field_name not in state:
                issues.append(
                    DriftIssue(
                        component=field_name,
                        expected="present",
                        actual="missing",
                        severity="error",
                    )
                )
                suggestions.append(f"Add '{field_name}' to state for better tracking")

        drifted = any(i.severity == "error" for i in issues)

        return DriftReport(
            drifted=drifted,
            issues=issues,
            suggestions=suggestions,
        )
