"""Tests for loopy.verification — Maker/Checker Pattern."""

import asyncio

from loopy.verification import (
    VerificationGate,
    VerificationStatus,
    VerifyResult,
)


class TestVerificationStatus:
    def test_status_enum(self):
        """Test verification status values."""
        assert VerificationStatus.PASSED.value == "passed"
        assert VerificationStatus.FAILED.value == "failed"
        assert VerificationStatus.ERROR.value == "error"


class TestVerifyResult:
    def test_result_creation(self):
        """Test verify result creation."""
        result = VerifyResult(
            status=VerificationStatus.PASSED,
            feedback="Looks good",
            score=0.9,
        )
        assert result.status == VerificationStatus.PASSED
        assert result.score == 0.9

    def test_result_passed(self):
        """Test result.passed property."""
        passed = VerifyResult(status=VerificationStatus.PASSED, score=1.0)
        failed = VerifyResult(status=VerificationStatus.FAILED, score=0.0)
        assert passed.passed is True
        assert failed.passed is False


class TestVerificationGate:
    def test_gate_creation(self):
        """Test gate creation."""
        async def impl(task):
            return "implemented"

        async def verifier(result):
            return VerifyResult(status=VerificationStatus.PASSED, score=1.0)

        gate = VerificationGate(implementer=impl, verifier=verifier)
        assert gate is not None

    def test_gate_success(self):
        """Test gate with successful implementation and verification."""
        async def impl(task):
            return f"Code for: {task}"

        async def verifier(result):
            if "Code for:" in result:
                return VerifyResult(status=VerificationStatus.PASSED, score=1.0)
            return VerifyResult(status=VerificationStatus.FAILED, score=0.0)

        gate = VerificationGate(implementer=impl, verifier=verifier)

        async def run_test():
            result = await gate.run("Fix bug")
            assert result.passed is True
            assert result.score == 1.0

        asyncio.run(run_test())

    def test_gate_verifier_rejects(self):
        """Test gate when verifier rejects implementation."""
        async def impl(task):
            return "bad code"

        async def verifier(result):
            return VerifyResult(status=VerificationStatus.FAILED, score=0.2, feedback="Poor quality")

        gate = VerificationGate(implementer=impl, verifier=verifier)

        async def run_test():
            result = await gate.run("Fix bug")
            assert result.passed is False
            assert result.score == 0.2
            assert result.feedback == "Poor quality"

        asyncio.run(run_test())

    def test_gate_with_test_fn(self):
        """Test gate with test function."""
        async def impl(task):
            return "implemented"

        async def verifier(result):
            return VerifyResult(status=VerificationStatus.PASSED, score=1.0)

        async def test_fn(result):
            return "implemented" in result

        gate = VerificationGate(implementer=impl, verifier=verifier, test_fn=test_fn)

        async def run_test():
            result = await gate.run("Fix bug")
            assert result.passed is True

        asyncio.run(run_test())

    def test_gate_test_fn_fails(self):
        """Test gate when test function fails."""
        async def impl(task):
            return "broken"

        async def verifier(result):
            return VerifyResult(status=VerificationStatus.PASSED, score=1.0)

        async def test_fn(result):
            return False  # Tests fail

        gate = VerificationGate(implementer=impl, verifier=verifier, test_fn=test_fn)

        async def run_test():
            result = await gate.run("Fix bug")
            assert result.passed is False
            assert "tests_failed" in result.feedback.lower() or result.status == VerificationStatus.FAILED

        asyncio.run(run_test())

    def test_gate_implementer_error(self):
        """Test gate when implementer raises error."""
        async def impl(task):
            raise ValueError("Implementation failed")

        async def verifier(result):
            return VerifyResult(status=VerificationStatus.PASSED, score=1.0)

        gate = VerificationGate(implementer=impl, verifier=verifier)

        async def run_test():
            result = await gate.run("Fix bug")
            assert result.passed is False
            assert result.status == VerificationStatus.ERROR

        asyncio.run(run_test())

    def test_gate_with_threshold(self):
        """Test gate with score threshold."""
        async def impl(task):
            return "implemented"

        async def verifier(result):
            return VerifyResult(status=VerificationStatus.PASSED, score=0.6)

        gate = VerificationGate(
            implementer=impl,
            verifier=verifier,
            threshold=0.8,  # Requires 0.8 but only gets 0.6
        )

        async def run_test():
            result = await gate.run("Fix bug")
            assert result.passed is False  # Score below threshold

        asyncio.run(run_test())
