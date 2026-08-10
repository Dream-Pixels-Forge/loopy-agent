"""
Example 5: Middleware Pipeline

Demonstrates composable middleware with retry, circuit breaker, and fallback.
"""

import asyncio

from loopy import (
    CircuitBreakerMiddleware,
    FallbackMiddleware,
    LoggingMiddleware,
    MiddlewareContext,
    MiddlewarePipeline,
    RetryMiddleware,
    TimingMiddleware,
)

# Simulate a flaky service
call_count = 0

async def flaky_handler(data: dict, **kwargs) -> str:
    """Handler that fails sometimes."""
    global call_count
    call_count += 1
    
    # Fail first 2 times, succeed on 3rd
    if call_count < 3:
        raise Exception(f"Service error (attempt {call_count})")
    
    return f"Success after {call_count} attempts!"


async def fallback_handler(ctx: MiddlewareContext, error: Exception) -> str:
    """Fallback function when main handler fails."""
    return f"Fallback response (original error: {error})"


async def main():
    global call_count
    
    # Create pipeline with middleware
    pipeline = MiddlewarePipeline()
    
    # Add middleware in order
    pipeline.add(LoggingMiddleware())  # Logs all operations
    pipeline.add(TimingMiddleware())   # Tracks timing
    pipeline.add(RetryMiddleware(      # Auto-retry with backoff
        max_retries=3,
        base_delay=0.1,
        max_delay=1.0,
    ))
    pipeline.add(CircuitBreakerMiddleware(  # Prevent cascade failures
        failure_threshold=5,
        recovery_timeout=30.0,
    ))
    pipeline.add(FallbackMiddleware(   # Provider failover
        fallback_fn=fallback_handler,
    ))
    
    print("=== Example 1: Successful Retry ===")
    call_count = 0
    
    result = await pipeline.execute(
        operation="llm.chat",
        handler=flaky_handler,
        data={"message": "Hello"},
    )
    print(f"Result: {result}")
    print(f"Total attempts: {call_count}")
    print()
    
    # Example 2: Circuit breaker
    print("=== Example 2: Circuit Breaker ===")
    
    fail_count = 0
    
    async def always_failing(data: dict, **kwargs) -> str:
        nonlocal fail_count
        fail_count += 1
        raise Exception(f"Failure #{fail_count}")
    
    breaker_pipeline = MiddlewarePipeline()
    breaker_pipeline.add(CircuitBreakerMiddleware(
        failure_threshold=3,
        recovery_timeout=1.0,
    ))
    
    # Try 5 times - first 3 should fail, 4th should be blocked
    for i in range(5):
        try:
            result = await breaker_pipeline.execute(
                operation="test",
                handler=always_failing,
                data={},
            )
            print(f"Attempt {i+1}: {result}")
        except Exception as e:
            print(f"Attempt {i+1}: Failed - {e}")
    
    print()
    
    # Example 3: Retry with failure
    print("=== Example 3: Retry Exhaustion ===")
    
    async def always_failing_handler(data: dict, **kwargs) -> str:
        raise Exception("Permanent failure")
    
    retry_pipeline = MiddlewarePipeline()
    retry_pipeline.add(RetryMiddleware(
        max_retries=2,
        base_delay=0.01,
    ))
    
    try:
        result = await retry_pipeline.execute(
            operation="llm.chat",
            handler=always_failing_handler,
            data={"message": "Hello"},
        )
    except Exception as e:
        print(f"Final error after retries: {e}")
    print()
    
    # Example 4: Custom middleware
    print("=== Example 4: Custom Middleware ===")
    
    from loopy import Middleware
    
    class AuthMiddleware(Middleware):
        """Custom middleware for authentication."""
        
        async def before(self, ctx: MiddlewareContext) -> MiddlewareContext:
            # Check for API key
            if not ctx.data.get("api_key"):
                ctx.cancel("Missing API key")
            else:
                print(f"Authenticated with key: {ctx.data['api_key'][:10]}...")
            return ctx
    
    auth_pipeline = MiddlewarePipeline()
    auth_pipeline.add(AuthMiddleware())
    
    # Without API key
    result = await auth_pipeline.execute(
        operation="llm.chat",
        handler=lambda data, **kwargs: "Success!",
        data={"message": "Hello"},
    )
    print(f"Without key: {result}")
    
    # With API key
    async def success_handler(data: dict, **kwargs) -> str:
        return "Success!"
    
    result = await auth_pipeline.execute(
        operation="llm.chat",
        handler=success_handler,
        data={"message": "Hello", "api_key": "sk-1234567890"},
    )
    print(f"With key: {result}")


if __name__ == "__main__":
    asyncio.run(main())
