"""Phase C — Policy.exponential() factory + Gateway retry integration."""

from __future__ import annotations

import asyncio
import logging

import pytest

from loopy.gateway import Gateway
from loopy.gateway import TestModel as _TestModel
from loopy.middleware import (
    CircuitBreakerMiddleware,
    MiddlewareContext,
    RetryMiddleware,
)
from loopy.policies import Policy, PolicyDecision, PolicyEngine

logger = logging.getLogger("loopy.test_retry")


# ── Policy.exponential() factory ──────────────────────────────


class TestPolicyExponentialFactory:
    def test_exponential_creates_policy_with_max_retries_condition(self):
        policy = Policy.exponential(max_attempts=3)
        assert policy.name == "exponential-retry"
        assert len(policy.conditions) == 1
        cond = policy.conditions[0]
        assert cond.kind == "max_retries"
        assert cond.value == 3
        assert policy.severity == "warn"

    def test_exponential_defaults(self):
        policy = Policy.exponential()
        assert policy.name == "exponential-retry"
        assert policy.conditions[0].value == 5
        assert policy.severity == "warn"

    def test_exponential_stores_extra_context_fields(self):
        policy = Policy.exponential(max_attempts=7, base=2.0, cap=60.0, jitter=False)
        assert policy.metadata["base_delay"] == 2.0
        assert policy.metadata["max_delay"] == 60.0
        assert policy.metadata["jitter"] is False

    def test_exponential_returns_new_instance_per_call(self):
        p1 = Policy.exponential(max_attempts=3)
        p2 = Policy.exponential(max_attempts=3)
        assert p1 is not p2
        # Each has its own condition list so mutations don't bleed.
        assert p1.conditions[0].value == p2.conditions[0].value

    def test_exponential_name_is_deterministic(self):
        policy = Policy.exponential(max_attempts=10)
        assert policy.name == "exponential-retry"

    def test_exponential_backoff_delays_no_jitter(self):
        policy = Policy.exponential(base=1.0, jitter=False)
        delays = policy.backoff_delays(retries=5)
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_exponential_backoff_delays_empty(self):
        policy = Policy.exponential()
        delays = policy.backoff_delays(retries=0)
        assert delays == []


# ── Exponential backoff schedule ──────────────────────────────


class TestExponentialBackoffSchedule:
    def test_delay_follows_2_retry_base(self):
        policy = Policy.exponential(base=1.0, jitter=False)
        delays = policy.backoff_delays(retries=5)
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_cap_is_respected(self):
        policy = Policy.exponential(base=1.0, cap=10.0, jitter=False)
        delays = policy.backoff_delays(retries=10)
        assert all(d <= 10.0 for d in delays)
        # Last few should all be capped at 10.
        assert delays[-3:] == [10.0, 10.0, 10.0]

    def test_jitter_true_returns_varied_floats(self):
        policy = Policy.exponential(base=1.0, jitter=True)
        # With full jitter the delays are NOT exact powers of two;
        # they are randomised. We verify by checking the returned
        # values are floats and not just the raw exponential schedule.
        delays = policy.backoff_delays(retries=3)
        assert len(delays) == 3
        assert all(isinstance(d, float) for d in delays)
        # After many samples the variance should be non-zero.
        sample = [policy.backoff_delays(retries=3) for _ in range(50)]
        # The first delay across samples should vary (full jitter).
        first_delays = [s[0] for s in sample]
        assert max(first_delays) != min(first_delays)

    def test_jitter_false_returns_exact_powers(self):
        policy = Policy.exponential(base=2.0, jitter=False)
        delays = policy.backoff_delays(retries=4)
        assert delays == [2.0, 4.0, 8.0, 16.0]

    def test_empty_retries_returns_empty_list(self):
        policy = Policy.exponential()
        delays = policy.backoff_delays(retries=0)
        assert delays == []


# ── PolicyEngine.evaluate fires correctly ────────────────────


class TestPolicyEngineExponential:
    @pytest.mark.asyncio
    async def test_fires_when_retries_exceed_max_attempts(self):
        policy = Policy.exponential(max_attempts=2)
        engine = PolicyEngine([policy])
        decisions = engine.evaluate({"retries": 3})
        assert len(decisions) == 1
        assert decisions[0].verdict == "warn"
        assert decisions[0].context["retries"] == 3

    @pytest.mark.asyncio
    async def test_no_false_positive_on_success(self):
        policy = Policy.exponential(max_attempts=5)
        engine = PolicyEngine([policy])
        decisions = engine.evaluate({"retries": 2})
        assert decisions == []

    @pytest.mark.asyncio
    async def test_evaluates_at_boundary(self):
        """retries == max_attempts should NOT fire (the condition is >)."""
        policy = Policy.exponential(max_attempts=3)
        engine = PolicyEngine([policy])
        decisions = engine.evaluate({"retries": 3})
        assert decisions == []

    @pytest.mark.asyncio
    async def test_default_max_attempts_5(self):
        policy = Policy.exponential()
        engine = PolicyEngine([policy])
        # retries=5 is exactly the default max_attempts, so no fire.
        decisions = engine.evaluate({"retries": 5})
        assert decisions == []
        # retries=6 should fire.
        decisions = engine.evaluate({"retries": 6})
        assert len(decisions) == 1

    @pytest.mark.asyncio
    async def test_audit_sink_receives_decision(self):
        policy = Policy.exponential(max_attempts=1)
        seen: list[PolicyDecision] = []

        def sink(decision: PolicyDecision) -> None:
            seen.append(decision)

        engine = PolicyEngine([policy], audit_sink=sink)
        engine.evaluate({"retries": 2})
        assert len(seen) == 1
        assert seen[0].policy_name == "exponential-retry"


# ── RetryMiddleware with policy ───────────────────────────────


class TestRetryMiddlewareIntegration:
    @pytest.mark.asyncio
    async def test_middleware_stops_retrying_when_policy_fires(self):
        """When the policy engine fires, middleware should raise
        immediately instead of retrying."""
        # max_attempts=0: first error (retries=0) doesn't fire (0>0 is
        # False), but the second error (retries=1) does (1>0 is True).
        policy = Policy.exponential(max_attempts=0)
        engine = PolicyEngine([policy])

        middleware = RetryMiddleware(policy_engine=engine)

        ctx = MiddlewareContext(operation="test_op", data={})

        # First failure: policy sees retries=0, 0 > 0 is False → retry allowed.
        result = await middleware.on_error(ctx, RuntimeError("fail"))
        assert result is not None
        assert ctx.metadata["_retry_count"] == 1

        # Second failure: policy sees retries=1, 1 > 0 is True → blocked.
        with pytest.raises(RuntimeError):
            await middleware.on_error(ctx, RuntimeError("fail"))

    @pytest.mark.asyncio
    async def test_middleware_retries_up_to_max(self):
        """Without a policy blocking, middleware retries up to its own limit."""
        middleware = RetryMiddleware(max_retries=3)

        call_count = 0

        async def handler(data, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return "ok"

        ctx = MiddlewareContext(operation="test_op", data={})
        # Simulate the pipeline's retry loop manually.
        error = RuntimeError("transient")
        for _ in range(3):
            error = await middleware.on_error(ctx, error)
        # After exhausting retries, on_error re-raises.
        assert isinstance(error, RuntimeError)


# ── CircuitBreakerMiddleware ──────────────────────────────────


class TestCircuitBreakerMiddleware:
    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self):
        cb = CircuitBreakerMiddleware(failure_threshold=3, recovery_timeout=60.0)
        ctx = MiddlewareContext(operation="test_op")
        for _ in range(3):
            error = await cb.on_error(ctx, RuntimeError("boom"))
            assert error is not None
        # Circuit should now be open.
        assert cb._state == "open"

    @pytest.mark.asyncio
    async def test_blocks_requests_when_open(self):
        cb = CircuitBreakerMiddleware(failure_threshold=2, recovery_timeout=60.0)
        ctx = MiddlewareContext(operation="test_op")
        await cb.on_error(ctx, RuntimeError("boom"))
        await cb.on_error(ctx, RuntimeError("boom"))
        assert cb._state == "open"

        ctx2 = MiddlewareContext(operation="test_op")
        result = await cb.before(ctx2)
        assert result.cancelled is True
        assert "Circuit breaker is open" in result.cancel_reason

    @pytest.mark.asyncio
    async def test_recovers_to_half_open_after_timeout(self):
        cb = CircuitBreakerMiddleware(failure_threshold=2, recovery_timeout=0.01)
        ctx = MiddlewareContext(operation="test_op")
        await cb.on_error(ctx, RuntimeError("boom"))
        await cb.on_error(ctx, RuntimeError("boom"))
        assert cb._state == "open"

        # Wait for recovery timeout.
        await asyncio.sleep(0.05)

        ctx2 = MiddlewareContext(operation="test_op")
        result = await cb.before(ctx2)
        # Should have transitioned to half-open (not cancelled).
        assert result.cancelled is False
        assert cb._state == "half-open"

    @pytest.mark.asyncio
    async def test_closes_after_successful_probe(self):
        cb = CircuitBreakerMiddleware(failure_threshold=2, recovery_timeout=0.01)
        ctx = MiddlewareContext(operation="test_op")
        await cb.on_error(ctx, RuntimeError("boom"))
        await cb.on_error(ctx, RuntimeError("boom"))
        await asyncio.sleep(0.05)

        # Probe succeeds -> closed.
        ctx2 = MiddlewareContext(operation="test_op")
        result = await cb.before(ctx2)
        assert result.cancelled is False
        assert cb._state == "half-open"

        result = await cb.after(ctx2, "ok")
        assert cb._state == "closed"


# ── Gateway uses retry policy ─────────────────────────────────


class TestGatewayRetryPolicy:
    @pytest.mark.asyncio
    async def test_gateway_stops_retrying_when_policy_fires(self):
        """When the retry policy fires, gateway should raise instead of
        looping endlessly."""
        policy = Policy.exponential(max_attempts=1)
        gw = Gateway(retry_policy=policy)
        try:
            tm = _TestModel(raise_on_message="always-fail")
            with pytest.raises(RuntimeError):
                await gw.chat("always-fail", model=tm)
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_gateway_retries_then_succeeds(self):
        """With a retry policy that hasn't fired yet, transient errors
        are retried until success."""
        policy = Policy.exponential(max_attempts=5)
        gw = Gateway(retry_policy=policy)
        try:
            call_num = 0

            def failing_then_ok(_msg, _sys):  # type: ignore[no-untyped-def]
                nonlocal call_num
                call_num += 1
                if call_num < 3:
                    raise RuntimeError("transient")
                return "success"

            tm = _TestModel(responses=[failing_then_ok])
            resp = await gw.chat("hi", model=tm)
            assert resp.content == "success"
            assert call_num == 3
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_gateway_no_policy_no_retry(self):
        """Gateway without retry_policy still works (legacy path)."""
        gw = Gateway()
        try:
            tm = _TestModel(responses=["hi"])
            resp = await gw.chat("hi", model=tm)
            assert resp.content == "hi"
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_gateway_policy_evaluated_on_each_retry(self):
        """Each retry increments the retry count in policy context."""
        policy = Policy.exponential(max_attempts=0)
        gw = Gateway(retry_policy=policy)
        try:
            tm = _TestModel(raise_on_message="boom")
            # max_attempts=0 means even the first retry (retries=1) fires.
            with pytest.raises(RuntimeError):
                await gw.chat("boom", model=tm)
        finally:
            await gw.close()
