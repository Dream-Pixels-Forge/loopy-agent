"""Tests for loopy.cost — Token Cost Tracking."""

import os
import tempfile

from loopy.cost import (
    BudgetExceeded,
    CostReport,
    CostTracker,
)


class TestCostTracker:
    def test_tracker_creation(self):
        """Test tracker creation with default budget."""
        tracker = CostTracker()
        assert tracker.daily_limit == 10000

    def test_tracker_custom_budget(self):
        """Test tracker with custom budget."""
        tracker = CostTracker(daily_limit=5000)
        assert tracker.daily_limit == 5000

    def test_record_tokens(self):
        """Test recording token usage."""
        tracker = CostTracker()
        tracker.record(100)
        tracker.record(200)
        assert tracker.used_today == 300

    def test_remaining_tokens(self):
        """Test remaining token calculation."""
        tracker = CostTracker(daily_limit=1000)
        tracker.record(400)
        assert tracker.remaining == 600

    def test_should_stop(self):
        """Test should_stop when budget exceeded."""
        tracker = CostTracker(daily_limit=100)
        tracker.record(50)
        assert tracker.should_stop is False
        tracker.record(60)
        assert tracker.should_stop is True

    def test_report_generation(self):
        """Test cost report generation."""
        tracker = CostTracker(daily_limit=1000)
        tracker.record(250)
        tracker.record(350)

        report = tracker.report()
        assert report.used == 600
        assert report.limit == 1000
        assert report.remaining == 400
        assert report.usage_percent == 60.0

    def test_reset_daily(self):
        """Test daily reset."""
        tracker = CostTracker()
        tracker.record(500)
        tracker.reset()
        assert tracker.used_today == 0

    def test_persistence(self):
        """Test cost persistence to file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            tracker1 = CostTracker(persist_path=path)
            tracker1.record(100)

            tracker2 = CostTracker(persist_path=path)
            assert tracker2.used_today == 100
        finally:
            os.unlink(path)


class TestCostReport:
    def test_report_creation(self):
        """Test report creation."""
        report = CostReport(used=500, limit=1000, remaining=500, usage_percent=50.0)
        assert report.used == 500
        assert report.limit == 1000

    def test_report_summary(self):
        """Test report summary dict."""
        report = CostReport(used=500, limit=1000, remaining=500, usage_percent=50.0)
        summary = report.summary()
        assert summary["used"] == 500
        assert summary["limit"] == 1000
        assert summary["remaining"] == 500
        assert summary["usage_percent"] == 50.0


class TestBudgetExceeded:
    def test_budget_exception(self):
        """Test budget exceeded exception."""
        exc = BudgetExceeded(1000, 1200)
        assert exc.limit == 1000
        assert exc.used == 1200
        assert "1200" in str(exc)
