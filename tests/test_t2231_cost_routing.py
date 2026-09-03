"""T2.3.1 — Cost-Aware Adaptive Routing (v0.9.0).

Covers:
  * ``Gateway.chat(..., max_cost_usd=X)`` raises ``BudgetExceeded``
    *before* the HTTP request fires when the estimated cost is
    above the cap
  * ``max_cost_usd=None`` disables the cost guard (regression
    against the v0.7.x behaviour)
  * When the requested provider would exceed the cap, the
    gateway falls back to the cheapest configured provider
  * ``CostTracker`` records the estimated cost, the actual cost,
    and the savings from the fallback
  * New ``ProviderConfig.cost_per_1k_tokens`` field (USD) so the
    gateway can pick the cheapest
"""

from __future__ import annotations

import pytest

from loopy.cost import BudgetExceeded, CostTracker
from loopy.gateway import (
    Gateway,
    ModelProvider,
    ProviderConfig,
)
from loopy.gateway import TestModel as _TestModel

# ── max_cost_usd pre-check ───────────────────────────────────


class TestMaxCostUsdPreCheck:
    @pytest.mark.asyncio
    async def test_max_cost_usd_disabled_by_default(self):
        """Regression: omitting max_cost_usd never raises on cost."""
        gw = Gateway()
        try:
            response = await gw.chat("hi", model=_TestModel())
            assert response is not None
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_max_cost_usd_none_disables_guard(self):
        gw = Gateway()
        try:
            response = await gw.chat("hi", model=_TestModel(), max_cost_usd=None)
            assert response is not None
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_max_cost_usd_below_estimate_raises_before_http(self):
        # With cost_per_1k_tokens=0.01 and max_tokens=1000 the
        # estimated cost is $0.01. Setting max_cost_usd=0.005 must
        # raise before any network call.
        gw = Gateway()
        gw.add_provider(
            "openai",
            ProviderConfig(
                provider=ModelProvider.OPENAI,
                api_key="sk-test",
                model="gpt-4",
                cost_per_1k_tokens=0.01,
            ),
        )
        try:
            with pytest.raises(BudgetExceeded):
                await gw.chat(
                    "hi",
                    provider="openai",
                    model=_TestModel(),  # short-circuit
                    max_tokens=1000,
                    max_cost_usd=0.005,
                )
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_max_cost_usd_above_estimate_passes(self):
        gw = Gateway()
        gw.add_provider(
            "openai",
            ProviderConfig(
                provider=ModelProvider.OPENAI,
                api_key="sk-test",
                model="gpt-4",
                cost_per_1k_tokens=0.001,
            ),
        )
        try:
            response = await gw.chat(
                "hi",
                provider="openai",
                model=_TestModel(),
                max_tokens=100,
                max_cost_usd=1.00,
            )
            assert response is not None
        finally:
            await gw.close()


# ── Provider fallback ───────────────────────────────────────


class TestProviderFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_cheapest_provider_when_over_budget(self):
        """When the requested provider is over the cost cap, the
        gateway falls back to the cheapest configured provider."""
        gw = Gateway()
        # Expensive provider (over the cap with the default test
        # max_tokens=1000).
        gw.add_provider(
            "openai",
            ProviderConfig(
                provider=ModelProvider.OPENAI,
                api_key="sk-test",
                model="gpt-4",
                cost_per_1k_tokens=0.06,  # 0.06 USD per 1k tokens
            ),
        )
        # Cheap fallback (within the cap).
        gw.add_provider(
            "ollama",
            ProviderConfig(
                provider=ModelProvider.OLLAMA,
                base_url="http://localhost:11434",
                model="llama3",
                cost_per_1k_tokens=0.0,  # local, free
            ),
        )
        try:
            response = await gw.chat(
                "hi",
                provider="openai",  # would cost $0.06 > $0.01
                model=_TestModel(),
                max_tokens=1000,
                max_cost_usd=0.01,
            )
            assert response is not None
            # The fallback should be recorded in logs.
            logs = gw.get_logs()
            fallback_logs = [log for log in logs if "fallback" in str(log).lower()]
            assert len(fallback_logs) >= 1
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_no_fallback_when_requested_provider_fits_budget(self):
        gw = Gateway()
        gw.add_provider(
            "openai",
            ProviderConfig(
                provider=ModelProvider.OPENAI,
                api_key="sk-test",
                model="gpt-4",
                cost_per_1k_tokens=0.001,
            ),
        )
        gw.add_provider(
            "ollama",
            ProviderConfig(
                provider=ModelProvider.OLLAMA,
                base_url="http://localhost:11434",
                model="llama3",
                cost_per_1k_tokens=0.0,
            ),
        )
        try:
            await gw.chat(
                "hi",
                provider="openai",
                model=_TestModel(),
                max_tokens=100,
                max_cost_usd=1.00,
            )
            logs = gw.get_logs()
            fallback_logs = [log for log in logs if "fallback" in str(log).lower()]
            assert fallback_logs == []
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_no_provider_within_budget_raises_budget_exceeded(self):
        gw = Gateway()
        gw.add_provider(
            "openai",
            ProviderConfig(
                provider=ModelProvider.OPENAI,
                api_key="sk-test",
                model="gpt-4",
                cost_per_1k_tokens=0.06,
            ),
        )
        gw.add_provider(
            "anthropic",
            ProviderConfig(
                provider=ModelProvider.ANTHROPIC,
                api_key="sk-test",
                model="claude-3",
                cost_per_1k_tokens=0.05,
            ),
        )
        try:
            with pytest.raises(BudgetExceeded):
                await gw.chat(
                    "hi",
                    provider="openai",
                    model=_TestModel(),
                    max_tokens=1000,
                    max_cost_usd=0.001,  # too low for any configured provider
                )
        finally:
            await gw.close()


# ── CostTracker integration ─────────────────────────────────


class TestCostTrackerIntegration:
    def test_tracker_records_estimated_and_actual_cost(self):
        tracker = CostTracker()
        tracker.record_estimated(0.05)
        tracker.record_actual(0.04, savings_from_fallback=0.02)
        report = tracker.report()
        # The tracker should expose estimated, actual, and savings.
        d = report.summary()
        assert d["estimated_usd"] == 0.05
        assert d["actual_usd"] == 0.04
        assert d["savings_usd"] == 0.02

    def test_tracker_no_fallback_has_zero_savings(self):
        tracker = CostTracker()
        tracker.record_estimated(0.01)
        tracker.record_actual(0.01, savings_from_fallback=0.0)
        d = tracker.report().summary()
        assert d["savings_usd"] == 0.0


# ── ProviderConfig.cost_per_1k_tokens ────────────────────────


class TestProviderConfigCostField:
    def test_cost_per_1k_tokens_defaults_to_zero(self):
        cfg = ProviderConfig(
            provider=ModelProvider.OLLAMA,
            base_url="http://localhost:11434",
        )
        assert cfg.cost_per_1k_tokens == 0.0

    def test_estimate_cost_uses_max_tokens_and_per_1k_rate(self):
        cfg = ProviderConfig(
            provider=ModelProvider.OPENAI,
            model="gpt-4",
            cost_per_1k_tokens=0.03,
        )
        # 1000 tokens at 0.03/1k = 0.03 USD.
        assert cfg.estimate_cost_usd(max_tokens=1000) == pytest.approx(0.03)
        # 250 tokens at 0.03/1k = 0.0075 USD.
        assert cfg.estimate_cost_usd(max_tokens=250) == pytest.approx(0.0075)

    def test_estimate_cost_uses_requested_token_count(self):
        cfg = ProviderConfig(
            provider=ModelProvider.OPENAI,
            model="gpt-4",
            cost_per_1k_tokens=0.01,
        )
        # Caller can override the assumed token count.
        assert cfg.estimate_cost_usd(max_tokens=500, expected_tokens=200) == pytest.approx(0.002)
