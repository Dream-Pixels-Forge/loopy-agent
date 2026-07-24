"""
Middleware — Composable request/response interceptors.

Add pre/post processing hooks to any loopy operation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Generic, TypeVar

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


class Middleware(ABC):
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
        logger.debug(f"Added middleware: {middleware.name}")

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
                    logger.info(f"Operation cancelled by {m.name}: {ctx.cancel_reason}")
                    return None
            except Exception as e:
                logger.error(f"Middleware {m.name} before hook failed: {e}")
                raise

        # Execute handler with retry support
        result = None
        error = None
        max_attempts = 4  # 1 initial + 3 retries
        
        for attempt in range(max_attempts):
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
                        logger.error(f"Middleware {m.name} error hook failed: {me}")
                
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
                logger.error(f"Middleware {m.name} after hook failed: {e}")
                raise

        return result


# ============================================================
# Built-in Middleware
# ============================================================

class LoggingMiddleware(Middleware):
    """Logs all operations."""
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        logger.info(f"[{ctx.operation}] Starting with {len(ctx.data)} data fields")
        return ctx
    
    async def after(self, ctx: MiddlewareContext, result: Any) -> Any:
        logger.info(f"[{ctx.operation}] Completed")
        return result
    
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        logger.error(f"[{ctx.operation}] Failed: {error}")
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
            logger.debug(f"[{ctx.operation}] Took {elapsed_ms:.1f}ms")
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
    """Cache middleware for identical requests."""
    
    def __init__(self, ttl: int = 60):
        self.ttl = ttl
        self._cache: dict[str, tuple[float, Any]] = {}
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        import hashlib
        import json
        
        # Create cache key
        key_data = json.dumps(ctx.data, sort_keys=True, default=str)
        cache_key = hashlib.md5(key_data.encode()).hexdigest()
        
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
        # Store in cache
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
            if field_name in ctx.data:
                if not validator(ctx.data[field_name]):
                    ctx.cancel(f"Validation failed for field: {field_name}")
                    return ctx
        
        return ctx


class RetryMiddleware(Middleware):
    """Auto-retry with exponential backoff."""
    
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
        self._retry_count = 0
    
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        if isinstance(error, self.retryable_exceptions) and self._retry_count < self.max_retries:
            delay = min(self.base_delay * (2 ** self._retry_count), self.max_delay)
            self._retry_count += 1
            logger.warning(f"Retry {self._retry_count}/{self.max_retries} after {delay:.1f}s: {error}")
            await asyncio.sleep(delay)
            ctx.metadata["retry_count"] = self._retry_count
            ctx.metadata["should_retry"] = True
            return error
        else:
            self._retry_count = 0
            raise


class CircuitBreakerMiddleware(Middleware):
    """Circuit breaker to prevent cascade failures."""
    
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
    
    async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        if self._state == "open":
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = "half-open"
                logger.info("Circuit breaker: half-open state")
            else:
                ctx.cancel(f"Circuit breaker is open (failures: {self._failure_count})")
        return ctx
    
    async def after(self, ctx: MiddlewareContext, result: Any) -> Any:
        # Success - reset failure count
        if self._state == "half-open":
            self._state = "closed"
            logger.info("Circuit breaker: closed (recovered)")
        self._failure_count = 0
        return result
    
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(f"Circuit breaker: open (failures: {self._failure_count})")
        
        return error


class FallbackMiddleware(Middleware):
    """Provider failover middleware."""
    
    def __init__(
        self,
        fallback_fn: Callable[[MiddlewareContext, Any], Awaitable[Any]] | None = None,
        fallback_data: dict[str, Any] | None = None,
    ):
        self.fallback_fn = fallback_fn
        self.fallback_data = fallback_data
    
    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> Exception:
        if self.fallback_fn:
            try:
                result = await self.fallback_fn(ctx, error)
                ctx.metadata["fallback_result"] = result
                ctx.metadata["fallback_used"] = True
                logger.info(f"Fallback used for {ctx.operation}")
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                return error
        elif self.fallback_data:
            ctx.metadata["fallback_result"] = self.fallback_data
            ctx.metadata["fallback_used"] = True
        
        return error
