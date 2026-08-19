"""
Middleware — Composable request/response interceptors.

Add pre/post processing hooks to any loopy operation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger("loopy.middleware")

T = TypeVar("T")


@dataclass
class MiddlewareContext:
    """Context passed through the middleware chain."""
    
    operation: str
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False
    cancel_reason: str = ""
    
    def cancel(self, reason: str = "Cancelled by middleware") -> None:
        """Cancel the operation."""
        self.cancelled = True
        self.cancel_reason = reason


class Middleware:
    """
    Base middleware class.
    
    Override `before` for pre-processing and `after` for post-processing.
    """
    
    @property
    def name(self) -> str:
        return self.__class__.__name__
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        """
        Pre-processing hook.
        
        Called before the main operation. Can modify context or cancel.
        """
        return ctx
    
    async def after(
        self,
        ctx: MiddlewareContext,
        result: Any,
    ) -> Any:
        """
        Post-processing hook.
        
        Called after the main operation. Can modify the result.
        """
        return result
    
    async def on_error(
        self,
        ctx: MiddlewareContext,
        error: Exception,
    ) -> Exception:
        """
        Error handling hook.
        
        Called when the operation raises an exception.
        """
        return error


class FunctionMiddleware(Middleware):
    """Middleware created from functions."""
    
    def __init__(
        self,
        name: str = "FunctionMiddleware",
        before_fn: Callable[[MiddlewareContext], Awaitable[MiddlewareContext]] | None = None,
        after_fn: Callable[[MiddlewareContext, Any], Awaitable[Any]] | None = None,
        error_fn: Callable[[MiddlewareContext, Exception], Awaitable[Exception]] | None = None,
    ):
        self._name = name
        self._before_fn = before_fn
        self._after_fn = after_fn
        self._error_fn = error_fn
    
    @property
    def name(self) -> str:
        return self._name
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        if self._before_fn:
            return await self._before_fn(ctx)
        return ctx
    
    async def after(self, ctx: MiddlewareContext, result: Any) -> Any:
        if self._after_fn:
            return await self._after_fn(ctx, result)
        return result
    
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        if self._error_fn:
            return await self._error_fn(ctx, error)
        return error


class MiddlewarePipeline:
    """
    Composable middleware pipeline.
    
    Example:
        pipeline = MiddlewarePipeline()
        
        # Add built-in middleware
        pipeline.add(LoggingMiddleware())
        pipeline.add(TimingMiddleware())
        pipeline.add(RateLimitMiddleware(max_per_second=10))
        
        # Add custom middleware
        pipeline.add(FunctionMiddleware(
            name="auth",
            before_fn=lambda ctx: ctx.data.update({"auth": True}) or ctx,
        ))
        
        # Execute through pipeline
        result = await pipeline.execute(
            operation="llm.chat",
            handler=my_handler,
            data={"message": "Hello"},
        )
    """

    def __init__(self):
        self._middleware: list[Middleware] = []

    def add(self, middleware: Middleware) -> None:
        """Add middleware to the pipeline."""
        self._middleware.append(middleware)
        logger.debug("Added middleware: %s", middleware.name)

    def remove(self, name: str) -> bool:
        """Remove middleware by name."""
        for i, m in enumerate(self._middleware):
            if m.name == name:
                del self._middleware[i]
                return True
        return False

    def clear(self) -> None:
        """Clear all middleware."""
        self._middleware.clear()

    async def execute(
        self,
        operation: str,
        handler: Callable[..., Awaitable[Any]],
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute a handler through the middleware pipeline.
        
        Args:
            operation: Operation name (e.g., "llm.chat")
            handler: The actual handler to execute
            data: Initial data/context
            **kwargs: Additional arguments passed to handler
        
        Returns:
            The handler result after middleware processing
        """
        ctx = MiddlewareContext(
            operation=operation,
            data=data or {},
        )

        # Run before hooks
        for m in self._middleware:
            try:
                ctx = await m.before(ctx)
                if ctx.cancelled:
                    logger.info("Operation cancelled by %s: %s", m.name, ctx.cancel_reason)
                    return None
            except Exception as e:
                logger.error("Middleware %s before hook failed: %s", m.name, e)
                raise

        # Execute handler with retry support
        result = None
        error = None
        max_attempts = 4  # 1 initial + 3 retries
        
        for _attempt in range(max_attempts):
            try:
                result = await handler(ctx.data, **kwargs)
                error = None
                break
            except Exception as e:
                error = e
                ctx.metadata["last_error"] = e
                
                # Run error hooks
                for m in reversed(self._middleware):
                    try:
                        error = await m.on_error(ctx, error)
                    except Exception as me:
                        logger.error("Middleware %s error hook failed: %s", m.name, me)
                
                # Check if we should retry
                if ctx.metadata.get("should_retry"):
                    ctx.metadata["should_retry"] = False
                    continue
                
                # No retry - raise the error
                raise error from None
        
        # If we exhausted retries, raise the last error
        if error is not None:
            raise error from None

        # Run after hooks
        for m in self._middleware:
            try:
                result = await m.after(ctx, result)
            except Exception as e:
                logger.error("Middleware %s after hook failed: %s", m.name, e)
                raise

        return result


# ============================================================
# Built-in Middleware
# ============================================================

class LoggingMiddleware(Middleware):
    """Logs all operations."""
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        logger.info("[%s] Starting with %d data fields", ctx.operation, len(ctx.data))
        return ctx
    
    async def after(self, ctx: MiddlewareContext, result: Any) -> Any:
        logger.info("[%s] Completed", ctx.operation)
        return result
    
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        logger.error("[%s] Failed: %s", ctx.operation, error)
        return error


class TimingMiddleware(Middleware):
    """Tracks operation timing."""
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        ctx.metadata["start_time"] = time.time()
        return ctx
    
    async def after(self, ctx: MiddlewareContext, result: Any) -> Any:
        start = ctx.metadata.get("start_time")
        if start:
            elapsed_ms = (time.time() - start) * 1000
            ctx.metadata["elapsed_ms"] = elapsed_ms
            logger.debug("[%s] Took %.1fms", ctx.operation, elapsed_ms)
        return result


class RateLimitMiddleware(Middleware):
    """Simple rate limiter."""
    
    def __init__(self, max_per_second: int = 10):
        self.max_per_second = max_per_second
        self._timestamps: list[float] = []
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        now = time.time()
        
        # Remove old timestamps
        self._timestamps = [t for t in self._timestamps if now - t < 1.0]
        
        if len(self._timestamps) >= self.max_per_second:
            ctx.cancel(f"Rate limit exceeded: {self.max_per_second}/sec")
        else:
            self._timestamps.append(now)
        
        return ctx


class CacheMiddleware(Middleware):
    """Cache middleware for identical requests.

    Caches responses and short-circuits duplicate requests
    within the TTL window.

    Args:
        ttl: Time-to-live in seconds for cached entries.
    """

    def __init__(self, ttl: int = 60):
        self.ttl = ttl
        self._cache: dict[str, tuple[float, Any]] = {}

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        """Check cache and short-circuit on hit."""
        # Create cache key (SHA-256 instead of MD5 to avoid scanner flags)
        key_data = json.dumps(ctx.data, sort_keys=True, default=str)
        cache_key = hashlib.sha256(key_data.encode()).hexdigest()

        # Check cache
        if cache_key in self._cache:
            timestamp, cached_result = self._cache[cache_key]
            if time.time() - timestamp < self.ttl:
                ctx.metadata["cached"] = True
                ctx.metadata["cached_result"] = cached_result
                ctx.cancel("Cache hit")
            else:
                del self._cache[cache_key]

        ctx.metadata["cache_key"] = cache_key
        return ctx

    async def after(self, ctx: MiddlewareContext, result: Any) -> Any:
        """Store result in cache after successful execution."""
        if not ctx.metadata.get("cached"):
            cache_key = ctx.metadata.get("cache_key")
            if cache_key:
                self._cache[cache_key] = (time.time(), result)
        return result


class ValidationMiddleware(Middleware):
    """Validates data before processing."""
    
    def __init__(
        self,
        required_fields: list[str] | None = None,
        validators: dict[str, Callable[[Any], bool]] | None = None,
    ):
        self.required_fields = required_fields or []
        self.validators = validators or {}
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        # Check required fields
        for field_name in self.required_fields:
            if field_name not in ctx.data:
                ctx.cancel(f"Missing required field: {field_name}")
                return ctx
        
        # Run validators
        for field_name, validator in self.validators.items():
            if field_name in ctx.data and not validator(ctx.data[field_name]):
                    ctx.cancel(f"Validation failed for field: {field_name}")
                    return ctx
        
        return ctx


class RetryMiddleware(Middleware):
    """Auto-retry with exponential backoff.

    Tracks retry count per-execution via context metadata so that
    reusing the same middleware instance across multiple calls does
    not leak state between runs.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds before the first retry.
        max_delay: Maximum delay cap in seconds.
        retryable_exceptions: Tuple of exception types that trigger a retry.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retryable_exceptions = retryable_exceptions

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        """Initialize per-execution retry state."""
        ctx.metadata["_retry_count"] = 0
        return ctx

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        """
        Handle errors with exponential backoff retry.

        Checks the per-execution retry count stored in context
        metadata so state doesn't leak between pipeline calls.
        """
        retry_count = ctx.metadata.get("_retry_count", 0)
        if isinstance(error, self.retryable_exceptions) and retry_count < self.max_retries:
            delay = min(self.base_delay * (2 ** retry_count), self.max_delay)
            ctx.metadata["_retry_count"] = retry_count + 1
            logger.warning(
                "Retry %d/%d after %.1fs: %s",
                retry_count + 1,
                self.max_retries,
                delay,
                error,
            )
            await asyncio.sleep(delay)
            ctx.metadata["retry_count"] = retry_count + 1
            ctx.metadata["should_retry"] = True
            return error
        else:
            raise


class CircuitBreakerMiddleware(Middleware):
    """Circuit breaker to prevent cascade failures.

    Tracks failure count and opens the circuit after a threshold,
    blocking requests for *recovery_timeout* seconds before
    allowing a probe (half-open state).  State mutations are
    protected by an asyncio lock for safe concurrent use.

    Args:
        failure_threshold: Consecutive failures before opening.
        recovery_timeout: Seconds before transitioning to half-open.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._state = "closed"  # closed = normal, open = blocked, half-open = testing
        self._lock = asyncio.Lock()

    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        """Block request if circuit is open (unless recovery timeout elapsed)."""
        async with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    self._state = "half-open"
                    logger.info("Circuit breaker: half-open state")
                else:
                    ctx.cancel(f"Circuit breaker is open (failures: {self._failure_count})")
        return ctx

    async def after(self, ctx: MiddlewareContext, result: Any) -> Any:
        """Reset failure count on success."""
        async with self._lock:
            if self._state == "half-open":
                self._state = "closed"
                logger.info("Circuit breaker: closed (recovered)")
            self._failure_count = 0
        return result

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        """Increment failure count; open circuit if threshold reached."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._failure_count >= self.failure_threshold:
                self._state = "open"
                logger.warning("Circuit breaker: open (failures: %d)", self._failure_count)

        return error


class FallbackMiddleware(Middleware):
    """Provider failover middleware.

    Returns a fallback result (from a callable or static data)
    when the primary handler raises an exception.

    Args:
        fallback_fn: Async callable ``(ctx, error) -> result``.
        fallback_data: Static dict to return as fallback result.
    """

    def __init__(
        self,
        fallback_fn: Callable[[MiddlewareContext, Any], Awaitable[Any]] | None = None,
        fallback_data: dict[str, Any] | None = None,
    ):
        self.fallback_fn = fallback_fn
        self.fallback_data = fallback_data

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        """Attempt fallback when the primary handler fails."""
        if self.fallback_fn:
            try:
                result = await self.fallback_fn(ctx, error)
                ctx.metadata["fallback_result"] = result
                ctx.metadata["fallback_used"] = True
                logger.info("Fallback used for %s", ctx.operation)
            except Exception as fallback_error:
                logger.error("Fallback also failed: %s", fallback_error)
                return error
        elif self.fallback_data:
            ctx.metadata["fallback_result"] = self.fallback_data
            ctx.metadata["fallback_used"] = True

        return error
