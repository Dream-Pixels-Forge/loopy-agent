"""Extended compliance tests — AuditLogger summary, EU AI Act paths."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from loopy.compliance import (
    AuditEntry,
    AuditLogger,
    ComplianceChecker,
    ComplianceFramework,
    ComplianceReport,
    DataClassification,
)


class TestAuditLoggerSummary:
    def test_summary_empty_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.jsonl")
            logger = AuditLogger(path)
            s = logger.summary(days=30)
            assert s["total_actions"] == 0
            assert s["total_tokens"] == 0
            assert s["by_agent"] == {}
            assert s["by_classification"] == {}

    def test_summary_with_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "summary.jsonl")
            logger = AuditLogger(path)

            logger.log(
                AuditEntry(
                    timestamp="2026-01-01T00:00:00",
                    action="summarize",
                    agent_id="agent-a",
                    input_summary="doc1",
                    output_summary="sum1",
                    classification=DataClassification.INTERNAL,
                    tokens_used=100,
                )
            )
            logger.log(
                AuditEntry(
                    timestamp="2026-01-01T01:00:00",
                    action="classify",
                    agent_id="agent-b",
                    input_summary="doc2",
                    output_summary="class2",
                    classification=DataClassification.PUBLIC,
                    tokens_used=50,
                )
            )

            s = logger.summary(days=30)
            assert s["total_actions"] == 2
            assert s["total_tokens"] == 150
            assert s["by_agent"] == {"agent-a": 1, "agent-b": 1}
            assert s["by_classification"] == {"internal": 1, "public": 1}

    def test_summary_queries_skips_corrupt_lines(self):
        """Corrupt lines in the JSONL file cause JSONDecodeError;
        the logger does not currently swallow them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "partial.jsonl")
            logger = AuditLogger(path)

            logger.log(
                AuditEntry(
                    timestamp="2026-01-01T00:00:00",
                    action="test",
                    agent_id="a1",
                    input_summary="s",
                    output_summary="o",
                    classification=DataClassification.PUBLIC,
                )
            )
            with open(path, "a") as f:
                f.write("this is not json\n")

            with pytest.raises(json.JSONDecodeError):
                logger.query()


class TestAuditLoggerQueryFilters:
    def test_query_by_agent_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "filtered.jsonl")
            logger = AuditLogger(path)

            logger.log(
                AuditEntry(
                    timestamp="2026-01-01T00:00:00",
                    action="a",
                    agent_id="alpha",
                    input_summary="x",
                    output_summary="y",
                    classification=DataClassification.PUBLIC,
                )
            )
            logger.log(
                AuditEntry(
                    timestamp="2026-01-01T01:00:00",
                    action="b",
                    agent_id="beta",
                    input_summary="x",
                    output_summary="y",
                    classification=DataClassification.PUBLIC,
                )
            )

            results = logger.query(agent_id="alpha")
            assert len(results) == 1
            assert results[0].agent_id == "alpha"

    def test_query_by_time_range(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "timed.jsonl")
            logger = AuditLogger(path)

            logger.log(
                AuditEntry(
                    timestamp="2025-06-01T00:00:00",
                    action="old",
                    agent_id="a",
                    input_summary="x",
                    output_summary="y",
                    classification=DataClassification.PUBLIC,
                )
            )
            logger.log(
                AuditEntry(
                    timestamp="2026-06-01T00:00:00",
                    action="new",
                    agent_id="a",
                    input_summary="x",
                    output_summary="y",
                    classification=DataClassification.PUBLIC,
                )
            )

            results = logger.query(start_time="2026-01-01T00:00:00")
            assert len(results) == 1
            assert results[0].action == "new"

            results = logger.query(end_time="2025-12-31T23:59:59")
            assert len(results) == 1
            assert results[0].action == "old"


class TestComplianceCheckerEUAIAct:
    def test_eu_ai_act_all_checks_pass(self):
        checker = ComplianceChecker()
        config = {
            "risk_classification": "high",
            "human_oversight": True,
            "transparency": True,
            "explainability": True,
        }
        report = checker.check_eu_ai_act(config)
        assert report.passed is True
        assert len(report.violations) == 0
        assert len(report.recommendations) == 0

    def test_eu_ai_act_missing_risk_classification(self):
        checker = ComplianceChecker()
        report = checker.check_eu_ai_act({})
        assert report.passed is False
        violations = [v for v in report.violations if "risk" in v.lower()]
        assert len(violations) > 0

    def test_eu_ai_act_missing_oversight(self):
        checker = ComplianceChecker()
        report = checker.check_eu_ai_act({"risk_classification": "low"})
        assert report.passed is False
        oversight_violations = [v for v in report.violations if "oversight" in v.lower()]
        assert len(oversight_violations) > 0

    def test_eu_ai_act_all_violations(self):
        checker = ComplianceChecker()
        report = checker.check_eu_ai_act({})
        assert report.passed is False
        assert len(report.checks) == 4
        passed = sum(1 for c in report.checks if c["passed"])
        assert passed == 0

    def test_eu_ai_act_partial_pass(self):
        checker = ComplianceChecker()
        report = checker.check_eu_ai_act(
            {
                "risk_classification": "high",
                "human_oversight": True,
            }
        )
        assert report.passed is False
        passed = sum(1 for c in report.checks if c["passed"])
        assert passed == 2
        assert len(report.recommendations) == 2


class TestComplianceReport:
    def test_summary_dict_shape(self):
        report = ComplianceReport(
            framework=ComplianceFramework.EU_AI_ACT,
            passed=False,
            checks=[
                {"name": "a", "passed": True},
                {"name": "b", "passed": False},
            ],
            violations=["violation 1"],
            recommendations=["rec 1"],
        )
        s = report.summary()
        assert s["framework"] == "eu_ai_act"
        assert s["passed"] is False
        assert s["checks_passed"] == 1
        assert s["checks_failed"] == 1
        assert s["violations"] == ["violation 1"]
        assert s["recommendations"] == ["rec 1"]


class TestComplianceCheckerSOC2Extended:
    def test_soc2_with_all_config(self):
        checker = ComplianceChecker()
        config = {
            "authentication": {"type": "oauth"},
            "audit_logging": True,
            "encryption": {"at_rest": True},
            "rate_limit": {"per_minute": 100},
        }
        report = checker.check_soc2(config)
        assert report.passed is True

    def test_soc2_missing_everything(self):
        checker = ComplianceChecker()
        report = checker.check_soc2({})
        assert report.passed is False
        # authentication → violation, audit_logging → violation;
        # encryption and rate_limit only produce recommendations
        assert len(report.violations) >= 2


class TestComplianceCheckerGDPRExtended:
    def test_gdpr_with_full_config(self):
        checker = ComplianceChecker()
        config = {
            "data_minimization": True,
            "deletion_support": True,
            "consent_tracking": True,
            "pii_protection": "masking",
        }
        report = checker.check_gdpr(config)
        assert report.passed is True

    def test_gdpr_partial_config(self):
        checker = ComplianceChecker()
        report = checker.check_gdpr({"data_processing_lawfulness": True})
        assert report.passed is False
        assert len(report.violations) > 0
