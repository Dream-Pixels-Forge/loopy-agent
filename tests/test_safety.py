"""Tests for loopy.safety — Production Safety Gates."""

import asyncio

import pytest

from loopy.safety import (
    EscalationReason,
    PermissionMode,
    SafetyCheck,
    SafetyGate,
    SafetyResult,
)


class TestEscalationReason:
    def test_reason_enum(self):
        """Test escalation reason values."""
        assert EscalationReason.MAX_ATTEMPTS.value == "max_attempts"
        assert EscalationReason.DENYLIST_PATH.value == "denylist_path"
        assert EscalationReason.LOW_CONFIDENCE.value == "low_confidence"
        assert EscalationReason.AMBIGUOUS_INPUT.value == "ambiguous_input"
        assert EscalationReason.PERMISSION_DENIED.value == "permission_denied"


class TestPermissionMode:
    def test_all_modes_exist(self):
        assert hasattr(PermissionMode, "READ_ONLY")
        assert hasattr(PermissionMode, "PLAN")
        assert hasattr(PermissionMode, "ACCEPT_EDITS")
        assert hasattr(PermissionMode, "DONT_ASK")
        assert hasattr(PermissionMode, "BYPASS")

    def test_mode_values(self):
        assert PermissionMode.READ_ONLY.value == "read_only"
        assert PermissionMode.PLAN.value == "plan"
        assert PermissionMode.ACCEPT_EDITS.value == "accept_edits"
        assert PermissionMode.DONT_ASK.value == "dont_ask"
        assert PermissionMode.BYPASS.value == "bypass"


class TestSafetyCheck:
    def test_check_creation(self):
        """Test safety check creation."""
        check = SafetyCheck(
            name="path_check",
            passed=True,
            reason="Path not in denylist",
        )
        assert check.name == "path_check"
        assert check.passed is True

    def test_check_failed(self):
        """Test failed safety check."""
        check = SafetyCheck(
            name="path_check",
            passed=False,
            reason="Path in denylist: src/auth/",
            escalation=EscalationReason.DENYLIST_PATH,
        )
        assert check.passed is False
        assert check.escalation == EscalationReason.DENYLIST_PATH


class TestSafetyResult:
    def test_result_safe(self):
        """Test safe result."""
        result = SafetyResult(
            safe=True,
            checks=[],
            should_escalate=False,
        )
        assert result.safe is True
        assert result.should_escalate is False

    def test_result_unsafe(self):
        """Test unsafe result with escalation."""
        checks = [
            SafetyCheck(
                name="path",
                passed=False,
                reason="Denylist",
                escalation=EscalationReason.DENYLIST_PATH,
            ),
        ]
        result = SafetyResult(
            safe=False,
            checks=checks,
            should_escalate=True,
        )
        assert result.safe is False
        assert result.should_escalate is True


class TestSafetyGate:
    def test_gate_creation(self):
        """Test gate creation with defaults."""
        gate = SafetyGate()
        assert gate is not None
        assert len(gate.denylist_paths) > 0  # Has defaults

    def test_gate_custom_denylist(self):
        """Test gate with custom denylist."""
        gate = SafetyGate(denylist_paths=["src/auth/*", "secrets/*"])
        assert len(gate.denylist_paths) == 2

    def test_safe_path(self):
        """Test safe path passes."""
        gate = SafetyGate()

        async def run_test():
            result = await gate.check_path("src/utils/helpers.py")
            assert result.passed is True

        asyncio.run(run_test())

    def test_denylist_path(self):
        """Test denylist path fails."""
        gate = SafetyGate()

        async def run_test():
            result = await gate.check_path("src/auth/login.py")
            assert result.passed is False
            assert result.escalation == EscalationReason.DENYLIST_PATH

        asyncio.run(run_test())

    def test_should_escalate_max_attempts(self):
        """Test escalation on max attempts."""
        gate = SafetyGate(max_attempts=3)

        should = gate.should_escalate(attempts=2, confidence=0.9)
        assert should is False

        should = gate.should_escalate(attempts=3, confidence=0.9)
        assert should is True

    def test_should_escalate_low_confidence(self):
        """Test escalation on low confidence."""
        gate = SafetyGate(human_gate_threshold=0.7)

        should = gate.should_escalate(attempts=1, confidence=0.8)
        assert should is False

        should = gate.should_escalate(attempts=1, confidence=0.5)
        assert should is True

    def test_full_safety_check(self):
        """Test full safety check flow."""
        gate = SafetyGate(denylist_paths=["secrets/*"])

        async def run_test():
            result = await gate.check(
                path="src/main.py",
                attempts=1,
                confidence=0.9,
            )
            assert result.safe is True
            assert result.should_escalate is False

        asyncio.run(run_test())

    def test_full_safety_check_denylist(self):
        """Test full safety check with denylist violation."""
        gate = SafetyGate(denylist_paths=["secrets/*"])

        async def run_test():
            result = await gate.check(
                path="secrets/api_key.py",
                attempts=1,
                confidence=0.9,
            )
            assert result.safe is False
            assert result.should_escalate is True

        asyncio.run(run_test())

    def test_default_denylist_contains_common_paths(self):
        """Test default denylist includes common sensitive paths."""
        gate = SafetyGate()
        default_paths = " ".join(gate.denylist_paths).lower()
        assert "auth" in default_paths or "secret" in default_paths or ".env" in default_paths

    # ── Permission mode checks ──────────────────────────────────────

    def test_check_permission_bypass_allows_side_effecting(self):
        gate = SafetyGate()
        check = gate.check_permission(PermissionMode.BYPASS, "side_effecting")
        assert check.passed is True

    def test_check_permission_read_only_mode_denies_side_effecting(self):
        gate = SafetyGate()
        check = gate.check_permission(PermissionMode.READ_ONLY, "side_effecting")
        assert check.passed is False
        assert check.escalation == EscalationReason.PERMISSION_DENIED

    def test_check_permission_plan_mode_denies_side_effecting(self):
        gate = SafetyGate()
        check = gate.check_permission(PermissionMode.PLAN, "side_effecting")
        assert check.passed is False
        assert check.escalation == EscalationReason.PERMISSION_DENIED

    def test_check_permission_accept_edits_allows_side_effecting(self):
        gate = SafetyGate()
        check = gate.check_permission(PermissionMode.ACCEPT_EDITS, "side_effecting")
        assert check.passed is True

    def test_check_permission_dont_ask_allows_side_effecting(self):
        gate = SafetyGate()
        check = gate.check_permission(PermissionMode.DONT_ASK, "side_effecting")
        assert check.passed is True

    def test_check_permission_read_only_mode_allows_read_only_tool(self):
        gate = SafetyGate()
        check = gate.check_permission(PermissionMode.READ_ONLY, "read_only")
        assert check.passed is True

    def test_default_permission_mode_is_read_only(self):
        gate = SafetyGate()
        assert gate.default_permission_mode == PermissionMode.READ_ONLY

    @pytest.mark.asyncio
    async def test_full_check_with_permission_denied(self):
        gate = SafetyGate()
        result = await gate.check(
            permission_mode=PermissionMode.READ_ONLY,
            tool_scope="side_effecting",
        )
        assert result.safe is False
        assert result.should_escalate is True

    @pytest.mark.asyncio
    async def test_full_check_with_permission_accepted(self):
        gate = SafetyGate()
        result = await gate.check(
            permission_mode=PermissionMode.ACCEPT_EDITS,
            tool_scope="side_effecting",
        )
        assert result.safe is True
        assert not result.should_escalate

    @pytest.mark.asyncio
    async def test_full_check_permission_in_combined_result(self):
        gate = SafetyGate(denylist_paths=["secrets/*"])
        result = await gate.check(
            path="src/main.py",
            attempts=1,
            confidence=0.9,
            permission_mode=PermissionMode.READ_ONLY,
            tool_scope="side_effecting",
        )
        assert result.safe is False  # permission denied
        perm_checks = [c for c in result.checks if c.name == "permission_check"]
        assert len(perm_checks) == 1
        assert perm_checks[0].passed is False
        assert perm_checks[0].escalation == EscalationReason.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_full_check_respects_default_permission_mode(self):
        """When no permission_mode is passed, defaults to READ_ONLY."""
        gate = SafetyGate()
        result = await gate.check(tool_scope="side_effecting")
        assert result.safe is False  # default mode is READ_ONLY
