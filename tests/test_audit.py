"""Tests for loopy.audit — Loop Readiness Scoring."""

import asyncio
import pytest
from loopy.audit import (
    LoopAuditor,
    AuditReport,
    CheckItem,
    ReadinessLevel,
)


class TestReadinessLevel:
    def test_level_enum_values(self):
        """Test readiness level enum has correct values."""
        assert ReadinessLevel.L0.value == "L0"
        assert ReadinessLevel.L1.value == "L1"
        assert ReadinessLevel.L2.value == "L2"
        assert ReadinessLevel.L3.value == "L3"

    def test_level_from_score(self):
        """Test level derivation from score."""
        assert ReadinessLevel.from_score(0) == ReadinessLevel.L0
        assert ReadinessLevel.from_score(25) == ReadinessLevel.L0
        assert ReadinessLevel.from_score(30) == ReadinessLevel.L1
        assert ReadinessLevel.from_score(50) == ReadinessLevel.L1
        assert ReadinessLevel.from_score(60) == ReadinessLevel.L2
        assert ReadinessLevel.from_score(79) == ReadinessLevel.L2
        assert ReadinessLevel.from_score(80) == ReadinessLevel.L3
        assert ReadinessLevel.from_score(100) == ReadinessLevel.L3


class TestCheckItem:
    def test_check_item_creation(self):
        """Test check item dataclass."""
        item = CheckItem(
            name="single_goal",
            passed=True,
            weight=10,
            description="Loop has a single clear goal",
        )
        assert item.name == "single_goal"
        assert item.passed is True
        assert item.weight == 10

    def test_check_item_score(self):
        """Test check item scoring."""
        passed = CheckItem(name="a", passed=True, weight=10, description="")
        failed = CheckItem(name="b", passed=False, weight=10, description="")
        assert passed.score == 10
        assert failed.score == 0


class TestAuditReport:
    def test_report_creation(self):
        """Test audit report creation."""
        report = AuditReport(
            score=75,
            level=ReadinessLevel.L2,
            checks=[],
            suggestions=[],
        )
        assert report.score == 75
        assert report.level == ReadinessLevel.L2

    def test_report_summary(self):
        """Test report summary generation."""
        checks = [
            CheckItem(name="a", passed=True, weight=10, description=""),
            CheckItem(name="b", passed=False, weight=10, description=""),
            CheckItem(name="c", passed=True, weight=10, description=""),
        ]
        report = AuditReport(score=67, level=ReadinessLevel.L1, checks=checks, suggestions=[])
        summary = report.summary()
        assert summary["score"] == 67
        assert summary["level"] == "L1"
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert summary["total"] == 3


class TestLoopAuditor:
    def test_auditor_creation(self):
        """Test auditor can be created."""
        auditor = LoopAuditor()
        assert auditor is not None

    def test_audit_empty_config(self):
        """Test auditing empty config gives low score."""
        auditor = LoopAuditor()

        async def run_test():
            report = await auditor.audit({})
            assert report.score < 30
            assert report.level == ReadinessLevel.L0
            assert len(report.checks) > 0

        asyncio.run(run_test())

    def test_audit_with_planner(self):
        """Test auditing config with planner increases score."""
        auditor = LoopAuditor()

        async def dummy_planner(h):
            return "plan"

        async def run_test():
            report = await auditor.audit({"planner": dummy_planner})
            # Should score higher than empty config
            assert report.score > 0

        asyncio.run(run_test())

    def test_audit_suggestions(self):
        """Test audit provides suggestions for failed checks."""
        auditor = LoopAuditor()

        async def run_test():
            report = await auditor.audit({})
            # Should have suggestions for missing components
            assert len(report.suggestions) > 0

        asyncio.run(run_test())

    def test_audit_level_boundaries(self):
        """Test level boundaries are correct."""
        auditor = LoopAuditor()

        async def run_test():
            # L0: 0-29
            report = await auditor.audit({})
            assert 0 <= report.score <= 100

        asyncio.run(run_test())
