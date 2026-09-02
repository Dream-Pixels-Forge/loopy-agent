"""Tests for loopy.drift — Config/State Drift Detection."""

import asyncio

from loopy.drift import (
    DriftDetector,
    DriftIssue,
    DriftReport,
)


class TestDriftIssue:
    def test_issue_creation(self):
        """Test drift issue creation."""
        issue = DriftIssue(
            component="planner",
            expected="configured",
            actual="missing",
            severity="warning",
        )
        assert issue.component == "planner"
        assert issue.severity == "warning"


class TestDriftReport:
    def test_report_creation(self):
        """Test drift report creation."""
        report = DriftReport(drifted=False, issues=[], suggestions=[])
        assert report.drifted is False

    def test_report_with_issues(self):
        """Test report with issues."""
        issues = [
            DriftIssue(component="a", expected="x", actual="y", severity="error"),
        ]
        report = DriftReport(drifted=True, issues=issues, suggestions=["Fix a"])
        assert report.drifted is True
        assert len(report.issues) == 1

    def test_report_summary(self):
        """Test report summary."""
        report = DriftReport(
            drifted=True,
            issues=[
                DriftIssue(component="a", expected="x", actual="y", severity="error"),
                DriftIssue(component="b", expected="x", actual="y", severity="warning"),
            ],
            suggestions=["Fix a"],
        )
        summary = report.summary()
        assert summary["drifted"] is True
        assert summary["error_count"] == 1
        assert summary["warning_count"] == 1


class TestDriftDetector:
    def test_detector_creation(self):
        """Test detector creation."""
        detector = DriftDetector()
        assert detector is not None

    def test_no_drift_when_matching(self):
        """Test no drift when config and state match."""
        detector = DriftDetector()

        config = {
            "planner": True,
            "actor": True,
            "observer": True,
            "reflector": True,
            "max_steps": 10,
        }
        state = {
            "current_task": "test",
            "attempts": 3,
            "max_steps": 10,
            "history": [],
        }

        async def run_test():
            report = await detector.check(config, state)
            # Should not have critical drift
            assert (
                report.drifted is False
                or len([i for i in report.issues if i.severity == "error"]) == 0
            )

        asyncio.run(run_test())

    def test_drift_when_max_steps_mismatch(self):
        """Test drift detection when max_steps differs."""
        detector = DriftDetector()

        config = {"max_steps": 10}
        state = {"max_steps": 5}

        async def run_test():
            report = await detector.check(config, state)
            assert report.drifted is True
            assert any("max_steps" in i.component for i in report.issues)

        asyncio.run(run_test())

    def test_drift_when_state_missing(self):
        """Test drift when state is missing expected fields."""
        detector = DriftDetector()

        config = {"planner": True, "actor": True}
        state = {}  # Missing everything

        async def run_test():
            report = await detector.check(config, state)
            assert report.drifted is True

        asyncio.run(run_test())

    def test_suggestions_provided(self):
        """Test that suggestions are provided for drift."""
        detector = DriftDetector()

        config = {"max_steps": 10}
        state = {"max_steps": 5}

        async def run_test():
            report = await detector.check(config, state)
            assert len(report.suggestions) > 0

        asyncio.run(run_test())
