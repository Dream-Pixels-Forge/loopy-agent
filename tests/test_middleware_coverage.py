"""Middleware coverage tests — retry, circuit breaker, fallback, cache, validation."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest

from loopy.middleware import (
    CacheMiddleware,
    CircuitBreakerMiddleware,
    FallbackMiddleware,
    FunctionMiddleware,
    LoggingMiddleware,
    MiddlewarePipeline,
    RateLimitMiddleware,
    RetryMiddleware,
    TimingMiddleware,
    ValidationMiddleware,
)

# ── Helpers ──────────────────────────────────────────────────

async def _ok_handler(data: dict[str, Any], **kwargs: Any) -> str:
    return f"ok:{data.get('msg', '')}"


async def _fail_handler(data: dict[str, Any], **kwargs: Any) -> str:
    raise RuntimeError("handler failed")


_call_count = 0


async def _fail_then_ok_handler(data: dict[str, Any], **kwargs: Any) -> str:
    global _call_count
    _call_count += 1
    if _call_count < 3:
        raise RuntimeError(f"fail #{_call_count}")
    return "recovered"


# ── Pipeline basics ──────────────────────────────────────────

class TestPipelineBasics:
    @pytest.mark.asyncio
    async def test_remove_middleware(self):
        pipe = MiddlewarePipeline()
        m = LoggingMiddleware()
        pipe.add(m)
        assert pipe.remove("LoggingMiddleware") is True
        assert pipe.remove("nonexistent") is False

    @pytest.mark.asyncio
    async def test_clear_middleware(self):
        pipe = MiddlewarePipeline()
        pipe.add(LoggingMiddleware())
        pipe.add(TimingMiddleware())
        pipe.clear()
        assert len(pipe._middleware) == 0

    @pytest.mark.asyncio
    async def test_execute_no_middleware(self):
        pipe = MiddlewarePipeline()
        result = await pipe.execute("test", _ok_handler, {"msg": "hi"})
        assert result == "ok:hi"

    @pytest.mark.asyncio
    async def test_execute_cancelled(self):
        async def cancel_fn(ctx):
            ctx.cancel("blocked")
            return ctx

        pipe = MiddlewarePipeline()
        pipe.add(FunctionMiddleware(name="blocker", before_fn=cancel_fn))
        result = await pipe.execute("test", _ok_handler, {"msg": "hi"})
        assert result is None


# ── RetryMiddleware ──────────────────────────────────────────

class TestRetryMiddleware:
    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        global _call_count
        _call_count = 0

        pipe = MiddlewarePipeline()
        pipe.add(RetryMiddleware(max_retries=5, base_delay=0.01))

        result = await pipe.execute("test", _fail_then_ok_handler, {})
        assert result == "recovered"
        assert _call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        async def always_fail(data, **kwargs):
            raise ValueError("always")

        pipe = MiddlewarePipeline()
        pipe.add(RetryMiddleware(max_retries=2, base_delay=0.01))

        with pytest.raises(ValueError, match="always"):
            await pipe.execute("test", always_fail, {})

    @pytest.mark.asyncio
    async def test_retry_non_retryable_exception(self):
        class CustomError(Exception):
            pass

        async def custom_fail(data, **kwargs):
            raise CustomError("custom")

        pipe = MiddlewarePipeline()
        pipe.add(RetryMiddleware(
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),  # CustomError not included
        ))

        with pytest.raises(CustomError):
            await pipe.execute("test", custom_fail, {})


# ── CircuitBreakerMiddleware ─────────────────────────────────

class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        cb = CircuitBreakerMiddleware(failure_threshold=3, recovery_timeout=10)
        pipe = MiddlewarePipeline()
        pipe.add(cb)

        for _ in range(3):
            with contextlib.suppress(RuntimeError):
                await pipe.execute("test", _fail_handler, {})

        # Circuit should be open now
        assert cb._state == "open"
        result = await pipe.execute("test", _ok_handler, {})
        assert result is None  # cancelled by circuit breaker

    @pytest.mark.asyncio
    async def test_circuit_half_open_after_timeout(self):
        cb = CircuitBreakerMiddleware(failure_threshold=2, recovery_timeout=0.1)
        pipe = MiddlewarePipeline()
        pipe.add(cb)

        # Open the circuit
        for _ in range(2):
            with contextlib.suppress(RuntimeError):
                await pipe.execute("test", _fail_handler, {})
        assert cb._state == "open"

        # Wait for recovery
        await asyncio.sleep(0.15)

        # Should be half-open now, and success closes it
        result = await pipe.execute("test", _ok_handler, {})
        assert result == "ok:"
        assert cb._state == "closed"

    @pytest.mark.asyncio
    async def test_circuit_reset_on_success(self):
        cb = CircuitBreakerMiddleware(failure_threshold=5)
        pipe = MiddlewarePipeline()
        pipe.add(cb)

        # One failure
        with contextlib.suppress(RuntimeError):
            await pipe.execute("test", _fail_handler, {})
        assert cb._failure_count == 1

        # Success resets
        await pipe.execute("test", _ok_handler, {})
        assert cb._failure_count == 0


# ── FallbackMiddleware ───────────────────────────────────────

class TestFallbackMiddleware:
    @pytest.mark.asyncio
    async def test_fallback_static_data(self):
        pipe = MiddlewarePipeline()
        pipe.add(FallbackMiddleware(fallback_data={"fallback": True}))

        # Handler fails, fallback data stored
        with contextlib.suppress(RuntimeError):
            await pipe.execute("test", _fail_handler, {})

    @pytest.mark.asyncio
    async def test_fallback_callable(self):
        async def my_fallback(ctx, error):
            return "fallback_result"

        pipe = MiddlewarePipeline()
        pipe.add(FallbackMiddleware(fallback_fn=my_fallback))

        with contextlib.suppress(RuntimeError):
            await pipe.execute("test", _fail_handler, {})

    @pytest.mark.asyncio
    async def test_fallback_also_fails(self):
        async def bad_fallback(ctx, error):
            raise RuntimeError("fallback also broken")

        pipe = MiddlewarePipeline()
        pipe.add(FallbackMiddleware(fallback_fn=bad_fallback))

        with pytest.raises(RuntimeError, match="handler failed"):
            await pipe.execute("test", _fail_handler, {})


# ── CacheMiddleware ──────────────────────────────────────────

class TestCacheMiddleware:
    @pytest.mark.asyncio
    async def test_cache_hit_short_circuits(self):
        cache = CacheMiddleware(ttl=60)
        pipe = MiddlewarePipeline()
        pipe.add(cache)

        # First call: cache miss, stores result
        r1 = await pipe.execute("test", _ok_handler, {"msg": "first"})
        assert r1 == "ok:first"

        # Second call: cache hit → pipeline returns None (cancelled)
        r2 = await pipe.execute("test", _ok_handler, {"msg": "first"})
        assert r2 is None  # cancelled by cache hit

    @pytest.mark.asyncio
    async def test_cache_expired(self):
        cache = CacheMiddleware(ttl=0)  # instant expiry
        pipe = MiddlewarePipeline()
        pipe.add(cache)

        await pipe.execute("test", _ok_handler, {"msg": "x"})
        await asyncio.sleep(0.01)
        r = await pipe.execute("test", _ok_handler, {"msg": "x"})
        assert r == "ok:x"


# ── ValidationMiddleware ─────────────────────────────────────

class TestValidationMiddleware:
    @pytest.mark.asyncio
    async def test_missing_required_field(self):
        pipe = MiddlewarePipeline()
        pipe.add(ValidationMiddleware(required_fields=["name"]))
        result = await pipe.execute("test", _ok_handler, {})
        assert result is None  # cancelled

    @pytest.mark.asyncio
    async def test_validator_failure(self):
        pipe = MiddlewarePipeline()
        pipe.add(ValidationMiddleware(validators={"age": lambda x: x > 0}))
        result = await pipe.execute("test", _ok_handler, {"age": -5})
        assert result is None  # cancelled

    @pytest.mark.asyncio
    async def test_all_valid(self):
        pipe = MiddlewarePipeline()
        pipe.add(ValidationMiddleware(
            required_fields=["name"],
            validators={"age": lambda x: x > 0},
        ))
        result = await pipe.execute("test", _ok_handler, {"name": "Alice", "age": 30})
        assert result == "ok:"


# ── RateLimitMiddleware ──────────────────────────────────────

class TestRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_rate_limit_cancel(self):
        pipe = MiddlewarePipeline()
        pipe.add(RateLimitMiddleware(max_per_second=1))

        # First call: ok
        r1 = await pipe.execute("test", _ok_handler, {})
        assert r1 == "ok:"

        # Immediate second call: rate limited
        r2 = await pipe.execute("test", _ok_handler, {})
        assert r2 is None  # cancelled
