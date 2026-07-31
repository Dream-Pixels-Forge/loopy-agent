"""
Compliance — Regulatory frameworks built-in.

SOC2, GDPR, EU AI Act compliance for agent loops.
Critical gap: 2026 enterprises require compliance.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.compliance")


class ComplianceFramework(str, Enum):
    """Supported compliance frameworks."""
    SOC2 = "soc2"
    GDPR = "gdpr"
    EU_AI_ACT = "eu_ai_act"


class DataClassification(str, Enum):
    """Data sensitivity levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"  # PII, PHI, PCI


@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: str
    action: str
    agent_id: str
    input_summary: str
    output_summary: str
    classification: DataClassification
    tokens_used: int = 0
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "agent_id": self.agent_id,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "classification": self.classification.value,
            "tokens_used": self.tokens_used,
            "model": self.model,
            "metadata": self.metadata,
        }


@dataclass
class ComplianceReport:
    """Compliance check report."""
    framework: ComplianceFramework
    passed: bool
    checks: list[dict[str, Any]]
    violations: list[str]
    recommendations: list[str]

    def summary(self) -> dict[str, Any]:
        return {
            "framework": self.framework.value,
            "passed": self.passed,
            "checks_passed": sum(1 for c in self.checks if c.get("passed")),
            "checks_failed": sum(1 for c in self.checks if not c.get("passed")),
            "violations": self.violations,
            "recommendations": self.recommendations,
        }


class AuditLogger:
    """
    Log all agent actions for compliance.

    Example:
        logger = AuditLogger("./audit.log")
        await logger.log("summarize", agent_id="agent-1", ...)
    """

    def __init__(self, path: str = "./audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def log(self, entry: AuditEntry) -> None:
        """Append an audit entry to the JSONL log file.

        Args:
            entry: The AuditEntry to persist.
        """
        with open(self.path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    async def query(
        self,
        agent_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[AuditEntry]:
        """Query audit log entries with optional filters.

        Args:
            agent_id: Filter by agent identifier.
            start_time: ISO-format start timestamp (inclusive).
            end_time: ISO-format end timestamp (inclusive).

        Returns:
            List of matching AuditEntry objects.
        """
        entries: list[AuditEntry] = []

        if not self.path.exists():
            return entries

        with open(self.path) as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)

                if agent_id and data.get("agent_id") != agent_id:
                    continue
                if start_time and data.get("timestamp", "") < start_time:
                    continue
                if end_time and data.get("timestamp", "") > end_time:
                    continue

                entries.append(AuditEntry(
                    timestamp=data["timestamp"],
                    action=data["action"],
                    agent_id=data["agent_id"],
                    input_summary=data["input_summary"],
                    output_summary=data["output_summary"],
                    classification=DataClassification(data["classification"]),
                    tokens_used=data.get("tokens_used", 0),
                    model=data.get("model", ""),
                    metadata=data.get("metadata", {}),
                ))

        return entries

    async def summary(self, days: int = 30) -> dict[str, Any]:
        """Generate a summary of audit activity.

        Args:
            days: Number of days to look back (currently unused,
                  reserved for future filtering).

        Returns:
            Dict with total_actions, total_tokens, breakdowns
            by agent and classification.
        """
        entries = await self.query()

        total_tokens = sum(e.tokens_used for e in entries)
        by_agent: dict[str, int] = {}
        by_classification: dict[str, int] = {}

        for e in entries:
            by_agent[e.agent_id] = by_agent.get(e.agent_id, 0) + 1
            cls_key = e.classification.value
            by_classification[cls_key] = by_classification.get(cls_key, 0) + 1

        return {
            "total_actions": len(entries),
            "total_tokens": total_tokens,
            "by_agent": by_agent,
            "by_classification": by_classification,
        }


class ComplianceChecker:
    """
    Check compliance against frameworks.

    Example:
        checker = ComplianceChecker()
        report = await checker.check_soc2(config)
        if not report.passed:
            print(f"Violations: {report.violations}")
    """

    def __init__(self, audit_logger: AuditLogger | None = None):
        self.audit_logger = audit_logger

    async def check_soc2(self, config: dict[str, Any]) -> ComplianceReport:
        """Check SOC2 compliance."""
        checks = []
        violations = []
        recommendations = []

        # Check: Access controls
        has_auth = config.get("authentication") is not None
        checks.append({"name": "access_controls", "passed": has_auth})
        if not has_auth:
            violations.append("No authentication configured")
            recommendations.append("Add authentication to restrict agent access")

        # Check: Audit logging
        has_audit = config.get("audit_logging") is True
        checks.append({"name": "audit_logging", "passed": has_audit})
        if not has_audit:
            violations.append("Audit logging not enabled")
            recommendations.append("Enable audit logging for all agent actions")

        # Check: Encryption
        has_encryption = config.get("encryption") is not None
        checks.append({"name": "encryption", "passed": has_encryption})
        if not has_encryption:
            recommendations.append("Configure encryption for data at rest and in transit")

        # Check: Rate limiting
        has_rate_limit = config.get("rate_limit") is not None
        checks.append({"name": "rate_limiting", "passed": has_rate_limit})
        if not has_rate_limit:
            recommendations.append("Add rate limiting to prevent abuse")

        return ComplianceReport(
            framework=ComplianceFramework.SOC2,
            passed=all(c["passed"] for c in checks),
            checks=checks,
            violations=violations,
            recommendations=recommendations,
        )

    async def check_gdpr(self, config: dict[str, Any]) -> ComplianceReport:
        """Check GDPR compliance."""
        checks = []
        violations = []
        recommendations = []

        # Check: Data minimization
        has_minimization = config.get("data_minimization") is True
        checks.append({"name": "data_minimization", "passed": has_minimization})
        if not has_minimization:
            violations.append("Data minimization not enforced")
            recommendations.append("Only collect necessary data for agent operation")

        # Check: Right to deletion
        has_deletion = config.get("deletion_support") is True
        checks.append({"name": "right_to_deletion", "passed": has_deletion})
        if not has_deletion:
            recommendations.append("Implement data deletion on user request")

        # Check: Consent tracking
        has_consent = config.get("consent_tracking") is True
        checks.append({"name": "consent_tracking", "passed": has_consent})
        if not has_consent:
            recommendations.append("Track user consent for data processing")

        # Check: PII handling
        has_pii_protection = config.get("pii_protection") is not None
        checks.append({"name": "pii_protection", "passed": has_pii_protection})
        if not has_pii_protection:
            violations.append("No PII protection configured")
            recommendations.append("Add PII detection and masking via guardrails")

        return ComplianceReport(
            framework=ComplianceFramework.GDPR,
            passed=all(c["passed"] for c in checks),
            checks=checks,
            violations=violations,
            recommendations=recommendations,
        )

    async def check_eu_ai_act(self, config: dict[str, Any]) -> ComplianceReport:
        """Check EU AI Act compliance."""
        checks = []
        violations = []
        recommendations = []

        # Check: Risk classification
        has_risk_class = config.get("risk_classification") is not None
        checks.append({"name": "risk_classification", "passed": has_risk_class})
        if not has_risk_class:
            violations.append("No risk classification for AI system")
            recommendations.append("Classify AI system risk level per EU AI Act")

        # Check: Human oversight
        has_human_oversight = config.get("human_oversight") is True
        checks.append({"name": "human_oversight", "passed": has_human_oversight})
        if not has_human_oversight:
            violations.append("No human oversight mechanism")
            recommendations.append("Add human-in-the-loop for high-risk decisions")

        # Check: Transparency
        has_transparency = config.get("transparency") is True
        checks.append({"name": "transparency", "passed": has_transparency})
        if not has_transparency:
            recommendations.append("Document AI system capabilities and limitations")

        # Check: Explainability
        has_explainability = config.get("explainability") is True
        checks.append({"name": "explainability", "passed": has_explainability})
        if not has_explainability:
            recommendations.append("Add decision audit trail for agent actions")

        return ComplianceReport(
            framework=ComplianceFramework.EU_AI_ACT,
            passed=all(c["passed"] for c in checks),
            checks=checks,
            violations=violations,
            recommendations=recommendations,
        )
