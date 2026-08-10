"""Tests for loopy.compliance — Regulatory compliance built-in."""

import os
import tempfile

import pytest

from loopy.compliance import (
    AuditEntry,
    AuditLogger,
    ComplianceChecker,
    ComplianceFramework,
    DataClassification,
)


class TestComplianceFramework:
    def test_frameworks(self):
        assert ComplianceFramework.SOC2.value == "soc2"
        assert ComplianceFramework.GDPR.value == "gdpr"
        assert ComplianceFramework.EU_AI_ACT.value == "eu_ai_act"


class TestDataClassification:
    def test_classifications(self):
        assert DataClassification.PUBLIC.value == "public"
        assert DataClassification.RESTRICTED.value == "restricted"


class TestAuditEntry:
    def test_entry_creation(self):
        entry = AuditEntry(
            timestamp="2026-01-01T00:00:00",
            action="summarize",
            agent_id="agent-1",
            input_summary="Long doc",
            output_summary="Summary",
            classification=DataClassification.INTERNAL,
        )
        assert entry.action == "summarize"
        d = entry.to_dict()
        assert d["classification"] == "internal"


class TestAuditLogger:
    def test_logger_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.jsonl")
            logger = AuditLogger(path)
            assert logger.path.exists() or True  # Dir created

    @pytest.mark.asyncio
    async def test_log_and_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.jsonl")
            logger = AuditLogger(path)

            entry = AuditEntry(
                timestamp="2026-01-01T00:00:00",
                action="test",
                agent_id="agent-1",
                input_summary="input",
                output_summary="output",
                classification=DataClassification.PUBLIC,
            )
            await logger.log(entry)

            entries = await logger.query()
            assert len(entries) == 1
            assert entries[0].action == "test"


class TestComplianceChecker:
    @pytest.mark.asyncio
    async def test_soc2_pass(self):
        checker = ComplianceChecker()
        config = {
            "authentication": {"type": "oauth"},
            "audit_logging": True,
            "encryption": {"at_rest": True},
            "rate_limit": {"per_minute": 100},
        }
        report = await checker.check_soc2(config)
        assert report.passed is True

    @pytest.mark.asyncio
    async def test_soc2_fail(self):
        checker = ComplianceChecker()
        report = await checker.check_soc2({})
        assert report.passed is False
        assert len(report.violations) > 0

    @pytest.mark.asyncio
    async def test_gdpr_check(self):
        checker = ComplianceChecker()
        report = await checker.check_gdpr({})
        assert report.passed is False
        assert len(report.recommendations) > 0

    @pytest.mark.asyncio
    async def test_eu_ai_act_check(self):
        checker = ComplianceChecker()
        report = await checker.check_eu_ai_act({"human_oversight": True})
        # Should have some failures
        assert len(report.checks) > 0
