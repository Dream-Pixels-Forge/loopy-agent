"""v1.2.0 T2.2 — Multi-tenant Gateway.

Tests the v1.2 multi-tenant contract:

* ``Gateway(tenant="acme", cost_tracker=tracker)`` routes cost
  through the tenant-scoped tracker.
* ``CostTracker(per_tenant=True).record_tenant(...)`` accumulates
  per-tenant token counts keyed by date.
* ``CostTracker.tenant_totals("acme")`` returns ``{"used",
  "limit", "remaining"}``.
* ``CostTracker.tenant_cost_usd("acme")`` returns estimated USD.
* When a tenant's used tokens reach its limit, subsequent
  ``Gateway.chat()`` calls raise ``BudgetExceeded`` before any
  provider I/O fires.
* Tenant isolation: acme costs ≠ globex costs.
* Single-tenant default path is unchanged (backward compat).
* Audit/log entries include ``tenant_id`` when a tenant is set.
"""

from __future__ import annotations

import pytest

from loopy.cost import BudgetExceeded, CostTracker
from loopy.gateway import Gateway, ModelProvider, ProviderConfig
from loopy.gateway import TestModel as _TM

# ── Helpers ───────────────────────────────────────────────────


def _openai_config(**overrides) -> ProviderConfig:
    return ProviderConfig(
        provider=ModelProvider.OPENAI,
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="gpt-4",
        **overrides,
    )


# ── CostTracker tenant methods ────────────────────────────────


class TestCostTrackerTenantMethods:
    def test_tenant_totals_returns_correct_shape(self):
        """tenant_totals returns {used, limit, remaining}."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        tracker.record_tenant("acme", 300)
        totals = tracker.tenant_totals("acme")
        assert totals == {"used": 300, "limit": 1000, "remaining": 700}

    def test_tenant_totals_unknown_tenant(self):
        """Unknown tenant returns zeroed totals."""
        tracker = CostTracker(daily_limit=500, per_tenant=True)
        totals = tracker.tenant_totals("nobody")
        assert totals == {"used": 0, "limit": 500, "remaining": 500}

    def test_tenant_cost_usd_basic(self):
        """tenant_cost_usd returns 0.0 when no cost rate is set."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        tracker.record_tenant("acme", 500)
        # Without a cost_per_1k_tokens rate, cost is 0.
        assert tracker.tenant_cost_usd("acme") == 0.0

    def test_tenant_cost_usd_with_rate(self):
        """tenant_cost_usd scales with a provided rate."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        tracker._tenant_rates["acme"] = 0.03  # $0.03 / 1k tokens
        tracker.record_tenant("acme", 1000)
        assert tracker.tenant_cost_usd("acme") == pytest.approx(0.03)

    def test_record_tenant_accumulates_per_tenant(self):
        """Multiple record_tenant calls sum for the same tenant."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        tracker.record_tenant("acme", 200)
        tracker.record_tenant("acme", 150)
        totals = tracker.tenant_totals("acme")
        assert totals["used"] == 350

    def test_tenant_mode_does_not_affect_global_usage(self):
        """record() and record_tenant() track independently."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        tracker.record(100)
        tracker.record_tenant("acme", 200)
        assert tracker.used_today == 100
        assert tracker.tenant_totals("acme")["used"] == 200

    def test_global_mode_ignores_tenant_methods(self):
        """When per_tenant=False, record_tenant has no effect."""
        tracker = CostTracker(daily_limit=1000, per_tenant=False)
        tracker.record_tenant("acme", 500)
        # Global used_today should not change.
        assert tracker.used_today == 0


# ── Tenant isolation ──────────────────────────────────────────


class TestTenantIsolation:
    def test_acme_and_globex_costs_are_independent(self):
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        tracker.record_tenant("acme", 400)
        tracker.record_tenant("globex", 600)
        assert tracker.tenant_totals("acme") == {
            "used": 400,
            "limit": 1000,
            "remaining": 600,
        }
        assert tracker.tenant_totals("globex") == {
            "used": 600,
            "limit": 1000,
            "remaining": 400,
        }

    def test_reset_clears_all_tenants(self):
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        tracker.record_tenant("acme", 300)
        tracker.record_tenant("globex", 200)
        tracker.reset()
        assert tracker.tenant_totals("acme")["used"] == 0
        assert tracker.tenant_totals("globex")["used"] == 0
        # Global usage also resets.
        assert tracker.used_today == 0


# ── Gateway with tenant ──────────────────────────────────────


class TestGatewayTenant:
    @pytest.mark.asyncio
    async def test_gateway_accepts_tenant_kwarg(self):
        """Gateway(tenant=...) stores the tenant without error."""
        tracker = CostTracker(daily_limit=10000, per_tenant=True)
        gw = Gateway(tenant="acme", cost_tracker=tracker)
        assert gw.tenant == "acme"
        await gw.close()

    @pytest.mark.asyncio
    async def test_gateway_without_tenant_defaults_to_none(self):
        """Gateway() without tenant still works."""
        gw = Gateway()
        assert gw.tenant is None
        await gw.close()

    @pytest.mark.asyncio
    async def test_chat_with_tenant_records_to_tracker(self):
        """A chat call with tenant= records tokens to the tracker."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        gw = Gateway(tenant="acme", cost_tracker=tracker)
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["hello world"])
        try:
            await gw.chat("hi", model=test_model)
        finally:
            await gw.close()
        # __TM counts words; "hello world" = 2 tokens.
        assert tracker.tenant_totals("acme")["used"] == 2

    @pytest.mark.asyncio
    async def test_chat_without_tenant_skips_tenant_recording(self):
        """Gateway without tenant does not touch the tracker."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        gw = Gateway(cost_tracker=tracker)
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["hi"])
        try:
            await gw.chat("hi", model=test_model)
        finally:
            await gw.close()
        # No tenant was set, so nothing was recorded.
        assert tracker.tenant_totals("acme")["used"] == 0

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises_before_chat(self):
        """When tenant hits limit, subsequent calls raise BudgetExceeded."""
        tracker = CostTracker(daily_limit=1, per_tenant=True)
        gw = Gateway(tenant="acme", cost_tracker=tracker)
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["short"])
        try:
            # First call: 1 token, hits the limit exactly.
            await gw.chat("hi", model=test_model)
            # Second call: tenant is at limit, should raise before I/O.
            with pytest.raises(BudgetExceeded):
                await gw.chat("hi again", model=test_model)
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_budget_exceeded_does_not_fire_provider_io(self):
        """BudgetExceeded is raised before any provider handler runs."""
        tracker = CostTracker(daily_limit=0, per_tenant=True)
        gw = Gateway(tenant="acme", cost_tracker=tracker)
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["should not run"])
        try:
            with pytest.raises(BudgetExceeded):
                await gw.chat("hi", model=test_model)
            # The test model should have recorded zero calls.
            assert test_model.calls == []
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_logs_include_tenant_id(self):
        """Log entries contain tenant_id when tenant is set."""
        tracker = CostTracker(daily_limit=10000, per_tenant=True)
        gw = Gateway(tenant="acme", cost_tracker=tracker)
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["ok"])
        try:
            await gw.chat("hi", model=test_model)
        finally:
            await gw.close()
        logs = gw.get_logs()
        assert len(logs) == 1
        assert logs[0]["tenant_id"] == "acme"

    @pytest.mark.asyncio
    async def test_logs_without_tenant_no_tenant_id(self):
        """Log entries omit tenant_id when no tenant is set."""
        gw = Gateway()
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["ok"])
        try:
            await gw.chat("hi", model=test_model)
        finally:
            await gw.close()
        logs = gw.get_logs()
        assert len(logs) == 1
        assert "tenant_id" not in logs[0]


# ── Backward compatibility ───────────────────────────────────


class TestBackwardCompat:
    @pytest.mark.asyncio
    async def test_gateway_without_new_params_works(self):
        """Gateway() with no tenant/cost_tracker still functions."""
        gw = Gateway()
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["world"])
        try:
            resp = await gw.chat("hi", model=test_model)
            assert resp.content == "world"
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_cost_tracker_without_per_tenant_unchanged(self):
        """CostTracker without per_tenant still uses record() as before."""
        tracker = CostTracker(daily_limit=1000)
        tracker.record(300)
        assert tracker.used_today == 300
        assert tracker.remaining == 700

    @pytest.mark.asyncio
    async def test_gateway_with_policy_engine_still_works(self):
        """PolicyEngine on Gateway is unaffected by new params."""
        from loopy.policies import Condition, Policy, PolicyEngine

        policy = Policy(
            name="cheap",
            conditions=[Condition(kind="max_cost_usd", value=999.0)],
            severity="info",
        )
        engine = PolicyEngine([policy])
        gw = Gateway(policy_engine=engine)
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["ok"])
        try:
            resp = await gw.chat("hi", model=test_model)
            assert resp.content == "ok"
        finally:
            await gw.close()


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_tenant_string_is_falsy(self):
        """tenant='' is treated as no tenant."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        gw = Gateway(tenant="", cost_tracker=tracker)
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["hi"])
        try:
            await gw.chat("hi", model=test_model)
        finally:
            await gw.close()
        # Empty string tenant should not record to tracker.
        assert tracker.tenant_totals("acme")["used"] == 0

    @pytest.mark.asyncio
    async def test_tenant_none_with_tracker_provided(self):
        """tenant=None + cost_tracker=... does not crash."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        gw = Gateway(tenant=None, cost_tracker=tracker)
        gw.add_provider("openai", _openai_config())
        test_model = _TM(responses=["hi"])
        try:
            await gw.chat("hi", model=test_model)
        finally:
            await gw.close()
        assert tracker.tenant_totals("acme")["used"] == 0

    @pytest.mark.asyncio
    async def test_different_tenants_share_tracker(self):
        """Two gateways can share one CostTracker with different tenants."""
        tracker = CostTracker(daily_limit=1000, per_tenant=True)
        gw1 = Gateway(tenant="acme", cost_tracker=tracker)
        gw2 = Gateway(tenant="globex", cost_tracker=tracker)
        gw1.add_provider("openai", _openai_config())
        gw2.add_provider("openai", _openai_config())
        tm = _TM(responses=["x"])
        try:
            await gw1.chat("hi", model=tm)
            await gw2.chat("hi", model=tm)
        finally:
            await gw1.close()
            await gw2.close()
        assert tracker.tenant_totals("acme")["used"] == 1
        assert tracker.tenant_totals("globex")["used"] == 1

    @pytest.mark.asyncio
    async def test_tenant_hit_limit_blocks_only_that_tenant(self):
        """When acme is over budget, globex can still call."""
        tracker = CostTracker(daily_limit=1, per_tenant=True)
        gw_acme = Gateway(tenant="acme", cost_tracker=tracker)
        gw_globex = Gateway(tenant="globex", cost_tracker=tracker)
        gw_acme.add_provider("openai", _openai_config())
        gw_globex.add_provider("openai", _openai_config())
        tm = _TM(responses=["x"])
        try:
            await gw_acme.chat("hi", model=tm)  # 1 token, hits limit
            with pytest.raises(BudgetExceeded):
                await gw_acme.chat("hi", model=tm)  # would exceed
            # globex is independent — should succeed.
            resp = await gw_globex.chat("hi", model=tm)
            assert resp is not None
        finally:
            await gw_acme.close()
            await gw_globex.close()

    @pytest.mark.asyncio
    async def test_cost_tracker_without_per_tenant_rejects_tenant_methods(self):
        """record_tenant on non-per-tenant tracker is a no-op."""
        tracker = CostTracker(daily_limit=1000, per_tenant=False)
        tracker.record_tenant("acme", 500)
        # Global usage should be unaffected.
        assert tracker.used_today == 0

    @pytest.mark.asyncio
    async def test_gateway_tenant_with_max_cost_usd(self):
        """Both tenant check and max_cost_usd can coexist."""
        tracker = CostTracker(daily_limit=10000, per_tenant=True)
        gw = Gateway(tenant="acme", cost_tracker=tracker)
        gw.add_provider(
            "openai",
            ProviderConfig(
                provider=ModelProvider.OPENAI,
                api_key="sk-test",
                model="gpt-4",
                cost_per_1k_tokens=0.001,
            ),
        )
        test_model = _TM(responses=["ok"])
        try:
            resp = await gw.chat(
                "hi",
                model=test_model,
                max_tokens=100,
                max_cost_usd=1.0,
            )
            assert resp is not None
        finally:
            await gw.close()
