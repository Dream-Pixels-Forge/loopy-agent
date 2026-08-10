"""Tests for loopy.patterns — Production Loop Patterns."""

from loopy.patterns import (
    LoopPattern,
    PatternCadence,
    PatternRegistry,
    RiskLevel,
)


class TestPatternCadence:
    def test_cadence_enum(self):
        """Test cadence enum values."""
        assert PatternCadence.MINUTES_5.value == "5m"
        assert PatternCadence.MINUTES_15.value == "15m"
        assert PatternCadence.HOURS_1.value == "1h"
        assert PatternCadence.HOURS_6.value == "6h"
        assert PatternCadence.DAILY.value == "1d"


class TestRiskLevel:
    def test_risk_enum(self):
        """Test risk level enum values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"


class TestLoopPattern:
    def test_pattern_creation(self):
        """Test pattern creation."""
        pattern = LoopPattern(
            name="daily-triage",
            description="Triage issues daily",
            cadence=PatternCadence.DAILY,
            risk=RiskLevel.LOW,
            readiness_level="L1",
        )
        assert pattern.name == "daily-triage"
        assert pattern.cadence == PatternCadence.DAILY

    def test_pattern_to_dict(self):
        """Test pattern serialization."""
        pattern = LoopPattern(
            name="test",
            description="Test pattern",
            cadence=PatternCadence.DAILY,
            risk=RiskLevel.LOW,
            readiness_level="L1",
        )
        d = pattern.to_dict()
        assert d["name"] == "test"
        assert d["cadence"] == "1d"
        assert d["risk"] == "low"


class TestPatternRegistry:
    def test_registry_creation(self):
        """Test registry creation."""
        registry = PatternRegistry()
        assert registry is not None

    def test_builtin_patterns(self):
        """Test built-in patterns exist."""
        registry = PatternRegistry()
        patterns = registry.list_all()
        assert len(patterns) >= 7

    def test_get_pattern(self):
        """Test getting pattern by name."""
        registry = PatternRegistry()
        pattern = registry.get("daily-triage")
        assert pattern is not None
        assert pattern.name == "daily-triage"

    def test_get_nonexistent(self):
        """Test getting nonexistent pattern returns None."""
        registry = PatternRegistry()
        pattern = registry.get("nonexistent")
        assert pattern is None

    def test_list_by_risk(self):
        """Test listing patterns by risk level."""
        registry = PatternRegistry()
        low_risk = registry.list_by_risk(RiskLevel.LOW)
        assert len(low_risk) > 0
        assert all(p.risk == RiskLevel.LOW for p in low_risk)

    def test_list_by_cadence(self):
        """Test listing patterns by cadence."""
        registry = PatternRegistry()
        daily = registry.list_by_cadence(PatternCadence.DAILY)
        assert len(daily) > 0
        assert all(p.cadence == PatternCadence.DAILY for p in daily)

    def test_builtin_pattern_details(self):
        """Test built-in pattern have required fields."""
        registry = PatternRegistry()
        for pattern in registry.list_all():
            assert pattern.name is not None
            assert pattern.description is not None
            assert pattern.cadence is not None
            assert pattern.risk is not None
            assert pattern.readiness_level is not None

    def test_daily_triage_pattern(self):
        """Test Daily Triage pattern specifics."""
        registry = PatternRegistry()
        pattern = registry.get("daily-triage")
        assert pattern.cadence == PatternCadence.DAILY
        assert pattern.risk == RiskLevel.LOW
        assert pattern.readiness_level == "L1"

    def test_pr_babysitter_pattern(self):
        """Test PR Babysitter pattern specifics."""
        registry = PatternRegistry()
        pattern = registry.get("pr-babysitter")
        assert pattern is not None
        assert pattern.risk == RiskLevel.MEDIUM
