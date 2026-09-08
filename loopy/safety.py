"""
Safety — Production Safety Gates.

Denylist paths, escalation triggers, human gates, and permission
modes (read-only / accept-edits / plan / dont-ask / bypass).
Inspired by loop-engineering's safety patterns and claude-agent-sdk
permission levels.
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
    PERMISSION_DENIED = "permission_denied"


class PermissionMode(str, Enum):
    """Agent permission level — controls which tool categories may run.

    Mode hierarchy (lowest → highest):
        read_only    Only read-only tools; all side-effecting tools denied.
        plan         Read-only + tools flagged requires_approval (logged).
        accept_edits Read-only + side_effecting tools flagged as safe.
        dont_ask     Side-effecting tools allowed; escalation only on
                     denylist-path or max-attempts violations.
        bypass       No gates enforced — equivalent to unrestricted mode.
    """

    READ_ONLY = "read_only"
    PLAN = "plan"
    ACCEPT_EDITS = "accept_edits"
    DONT_ASK = "dont_ask"
    BYPASS = "bypass"


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

    Enforces denylist paths, attempt limits, confidence thresholds,
    and permission-mode policy (read-only, plan, accept_edits,
    dont_ask, bypass).

    Example:
        gate = SafetyGate(denylist_paths=["secrets/*", ".env*"])
        result = await gate.check(
            path="src/main.py", attempts=1, confidence=0.9,
            permission_mode=PermissionMode.ACCEPT_EDITS,
            tool_scope="side_effecting",
        )
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
        default_permission_mode: PermissionMode = PermissionMode.READ_ONLY,
    ):
        self.denylist_paths = denylist_paths or self.DEFAULT_DENYLIST
        self.max_attempts = max_attempts
        self.human_gate_threshold = human_gate_threshold
        self.default_permission_mode = default_permission_mode

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

    def check_permission(
        self,
        mode: PermissionMode,
        tool_scope: str,
    ) -> SafetyCheck:
        """Check whether *tool_scope* is permitted under *mode*.

        Args:
            mode: Current permission mode.
            tool_scope: Tool scope — ``"read_only"`` or ``"side_effecting"``.

        Returns:
            A SafetyCheck indicating whether the tool is allowed.
        """
        if mode == PermissionMode.BYPASS:
            return SafetyCheck(name="permission_check", passed=True, reason="bypass mode")
        if tool_scope == "read_only":
            return SafetyCheck(name="permission_check", passed=True, reason="read_only tool")
        # side_effecting tool
        if mode == PermissionMode.READ_ONLY:
            return SafetyCheck(
                name="permission_check",
                passed=False,
                reason="side_effecting tool denied in read_only mode",
                escalation=EscalationReason.PERMISSION_DENIED,
            )
        if mode == PermissionMode.PLAN:
            return SafetyCheck(
                name="permission_check",
                passed=False,
                reason="side_effecting tool denied in plan mode",
                escalation=EscalationReason.PERMISSION_DENIED,
            )
        # accept_edits, dont_ask allow side_effecting
        return SafetyCheck(name="permission_check", passed=True, reason=f"allowed in {mode.value}")

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
        *,
        permission_mode: PermissionMode | None = None,
        tool_scope: str = "read_only",
    ) -> SafetyResult:
        """
        Full safety check.

        Args:
            path: File path to check.
            attempts: Number of attempts so far.
            confidence: Confidence score (0-1).
            permission_mode: Permission mode to enforce.
                Defaults to :attr:`default_permission_mode`.
            tool_scope: Tool category — ``"read_only"`` or ``"side_effecting"``.

        Returns:
            SafetyResult with safety status and per-check details.
        """
        mode = permission_mode or self.default_permission_mode
        checks: list[SafetyCheck] = []

        # Path check
        if path:
            path_check = await self.check_path(path)
            checks.append(path_check)

        # Permission check
        perm_check = self.check_permission(mode, tool_scope)
        checks.append(perm_check)

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

        path_ok_names = {"path_check", "permission_check"}
        path_safe = all(c.passed for c in checks if c.name in path_ok_names)
        safe = all(c.passed for c in checks)
        should_escalate = self.should_escalate(attempts, confidence, path_safe)

        return SafetyResult(
            safe=safe,
            checks=checks,
            should_escalate=should_escalate,
        )
