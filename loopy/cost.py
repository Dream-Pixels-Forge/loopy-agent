"""
Cost — Token Cost Tracking.

Track and limit token spending with daily budgets.
Inspired by loop-engineering's loop-cost tool.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.cost")


class BudgetExceeded(Exception):
    """Raised when token budget is exceeded."""

    def __init__(self, limit: int, used: int):
        self.limit = limit
        self.used = used
        super().__init__(f"Budget exceeded: {used}/{limit} tokens")


@dataclass
class CostReport:
    """Report of token usage and (v0.9.0) USD cost."""

    used: int
    limit: int
    remaining: int
    usage_percent: float
    # v0.9.0 — Cost-Aware Routing. All four USD fields are 0.0 by
    # default for the v0.7.x token-only callers; callers that
    # opt in to USD tracking see them populated.
    estimated_usd: float = 0.0
    actual_usd: float = 0.0
    savings_usd: float = 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "used": self.used,
            "limit": self.limit,
            "remaining": self.remaining,
            "usage_percent": self.usage_percent,
            "estimated_usd": self.estimated_usd,
            "actual_usd": self.actual_usd,
            "savings_usd": self.savings_usd,
        }


class CostTracker:
    """
    Track and limit token spending.

    Example:
        tracker = CostTracker(daily_limit=10000)
        tracker.record(500)
        report = tracker.report()
        print(f"Used: {report.used}/{report.limit}")
    """

    def __init__(
        self,
        daily_limit: int = 10000,
        persist_path: str | None = None,
        per_tenant: bool = False,
    ):
        self.daily_limit = daily_limit
        self.persist_path = Path(persist_path) if persist_path else None
        self.per_tenant = per_tenant
        self._usage: dict[str, int] = {}
        # v1.2.0 — per-tenant tracking. When ``per_tenant=True``,
        # ``_tenants`` holds a dict keyed by tenant_id -> {date: tokens}.
        self._tenants: dict[str, dict[str, int]] = {}
        # Optional per-tenant cost rates (USD per 1k tokens).
        self._tenant_rates: dict[str, float] = {}
        # v0.9.0 — USD totals across the run (not persisted; resets
        # on process restart). The token ``_usage`` dict is keyed by
        # day; the USD totals are session-scoped.
        self._estimated_usd: float = 0.0
        self._actual_usd: float = 0.0
        self._savings_usd: float = 0.0

        if self.persist_path and self.persist_path.exists():
            self._load()

    @property
    def used_today(self) -> int:
        """Tokens used today."""
        today = date.today().isoformat()
        return self._usage.get(today, 0)

    @property
    def remaining(self) -> int:
        """Tokens remaining today."""
        return max(0, self.daily_limit - self.used_today)

    @property
    def should_stop(self) -> bool:
        """Whether budget is exceeded."""
        return self.remaining <= 0

    def record(self, tokens: int) -> None:
        """Record token usage."""
        today = date.today().isoformat()
        self._usage[today] = self._usage.get(today, 0) + tokens

        if self.persist_path:
            self._save()

        if self.should_stop:
            logger.warning("Budget exceeded: %s/%s", self.used_today, self.daily_limit)

    # ── v1.2.0 — Per-tenant tracking ───────────────────────────

    def record_tenant(self, tenant_id: str, tokens: int) -> None:
        """Record token usage for a specific tenant.

        No-op when ``per_tenant`` is disabled.
        """
        if not self.per_tenant:
            return
        today = date.today().isoformat()
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = {}
        self._tenants[tenant_id][today] = self._tenants[tenant_id].get(today, 0) + tokens

    def tenant_totals(self, tenant_id: str) -> dict[str, int]:
        """Return {used, limit, remaining} for a specific tenant."""
        if not self.per_tenant:
            return {"used": 0, "limit": self.daily_limit, "remaining": self.daily_limit}
        today = date.today().isoformat()
        used = self._tenants.get(tenant_id, {}).get(today, 0)
        return {
            "used": used,
            "limit": self.daily_limit,
            "remaining": max(0, self.daily_limit - used),
        }

    def tenant_cost_usd(self, tenant_id: str) -> float:
        """Return estimated USD for a specific tenant."""
        totals = self.tenant_totals(tenant_id)
        rate = self._tenant_rates.get(tenant_id, 0.0)
        return (totals["used"] / 1000.0) * rate

    def reset(self) -> None:
        """Reset daily usage."""
        self._usage.clear()
        self._tenants.clear()
        self._estimated_usd = 0.0
        self._actual_usd = 0.0
        self._savings_usd = 0.0
        if self.persist_path:
            self._save()

    # ── v0.9.0 — Cost-Aware Routing ───────────────────────────

    def record_estimated(self, usd: float) -> None:
        """Record the estimated USD cost of a planned call."""
        self._estimated_usd += float(usd)

    def record_actual(
        self,
        usd: float,
        *,
        savings_from_fallback: float = 0.0,
    ) -> None:
        """Record the actual USD cost of a completed call.

        ``savings_from_fallback`` is the dollar amount the routing
        decision saved vs. the originally-requested provider (when
        the gateway fell back to a cheaper option).
        """
        self._actual_usd += float(usd)
        self._savings_usd += float(savings_from_fallback)

    def report(self) -> CostReport:
        """Generate cost report."""
        used = self.used_today
        return CostReport(
            used=used,
            limit=self.daily_limit,
            remaining=max(0, self.daily_limit - used),
            usage_percent=(used / self.daily_limit * 100) if self.daily_limit > 0 else 0,
            estimated_usd=self._estimated_usd,
            actual_usd=self._actual_usd,
            savings_usd=self._savings_usd,
        )

    def _save(self) -> None:
        """Save usage to disk."""
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist_path.write_text(json.dumps(self._usage, indent=2))

    def _load(self) -> None:
        """Load usage from disk."""
        if not self.persist_path or not self.persist_path.exists():
            return
        try:
            self._usage = json.loads(self.persist_path.read_text())
        except Exception as e:
            logger.warning("Failed to load cost data: %s", e)
            self._usage = {}
