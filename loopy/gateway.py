"""
AI Gateway — One control plane, many models.

Unified interface to route requests across OpenAI, Anthropic, and open-source providers.
Includes auth management, rate limiting, logging, and connection pooling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger("loopy.gateway")


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    CUSTOM = "custom"


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider.

    Includes rate-limit tracking via :meth:`check_rate_limit` and
    :meth:`record_request`.

    Args:
        provider: The LLM provider enum.
        api_key: Optional API key for authentication.
        base_url: Base URL for the provider API.
        model: Model identifier (e.g. "gpt-4").
        rpm: Max requests per minute.
        tpm: Max tokens per minute.
    """

    provider: ModelProvider
    api_key: str | None = None
    base_url: str = ""
    model: str = "gpt-4"

    # Rate limiting
    rpm: int = 60  # requests per minute
    tpm: int = 100_000  # tokens per minute

    # Internal tracking
    _request_count: int = field(default=0, repr=False)
    _window_start: float = field(default_factory=time.time, repr=False)

    def check_rate_limit(self) -> None:
        """Check whether the rate limit has been reached.

        Raises:
            RuntimeError: If the number of requests in the current
                rolling 60-second window exceeds *rpm*.
        """
        now = time.time()
        if now - self._window_start > 60:
            self._request_count = 0
            self._window_start = now

        if self._request_count >= self.rpm:
            raise RuntimeError(f"Rate limit exceeded for {self.provider.value}")

    def record_request(self) -> None:
        """Increment the request counter for rate tracking."""
        self._request_count += 1


@dataclass
class GatewayResponse:
    """Unified response from the gateway."""
    
    content: str
    model: str
    provider: ModelProvider
    tokens_used: int = 0
    latency_ms: float = 0
    cached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ConnectionPool:
    """
    HTTP connection pool for reusing connections to providers.
    
    Reduces latency by reusing TCP connections and SSL handshakes.
    Evicts the least-recently-used connection when at capacity.
    
    Example:
        pool = ConnectionPool(max_size=10)
        async with pool.get_connection("openai") as client:
            response = await client.post(...)
    """
    
    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self._connections: dict[str, httpx.AsyncClient] = {}
        self._last_used: dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    async def get_connection(self, provider: str) -> httpx.AsyncClient:
        """Get or create a connection for a provider."""
        async with self._lock:
            if provider in self._connections:
                self._last_used[provider] = time.time()
                return self._connections[provider]

            if len(self._connections) >= self.max_size:
                # Evict least recently used connection
                lru_key = min(self._last_used, key=self._last_used.get)
                await self._connections[lru_key].aclose()
                del self._connections[lru_key]
                del self._last_used[lru_key]

            self._connections[provider] = httpx.AsyncClient(
                timeout=60.0,
                limits=httpx.Limits(
                    max_connections=5,
                    max_keepalive_connections=2,
                ),
            )
            self._last_used[provider] = time.time()
            return self._connections[provider]
    
    async def close(self) -> None:
        """Close all connections in the pool."""
        for client in self._connections.values():
            await client.aclose()
        self._connections.clear()
        self._last_used.clear()
    
    def stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        return {
            "active_connections": len(self._connections),
            "max_size": self.max_size,
            "providers": list(self._connections.keys()),
        }


class Gateway:
    """
    AI Gateway for routing LLM requests across providers.
    
    Supports both standalone and async context manager usage.
    
    Example (async context manager):
        async with Gateway() as gateway:
            gateway.add_provider("openai", ProviderConfig(...))
            response = await gateway.chat("What is 2+2?")
    
    Example (standalone):
        gateway = Gateway()
        gateway.add_provider("openai", ProviderConfig(...))
        response = await gateway.chat("What is 2+2?", provider="openai")
        await gateway.close()
    """
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False

    def __init__(self):
        self.providers: dict[str, ProviderConfig] = {}
        self._pool: ConnectionPool = ConnectionPool()
        self._logs: list[dict[str, Any]] = []

    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """Register a provider."""
        self.providers[name] = config
        logger.info("Added provider: %s (%s)", name, config.provider.value)

    def _resolve_provider(
        self, provider: str | None = None
    ) -> tuple[str, ProviderConfig]:
        """Resolve a provider name to a (name, config) pair.

        Args:
            provider: Preferred provider name, or *None* for the first
                      available provider.

        Returns:
            A tuple of (provider_name, ProviderConfig).

        Raises:
            ValueError: If no providers are configured.
        """
        if provider and provider in self.providers:
            return provider, self.providers[provider]
        if self.providers:
            name, config = next(iter(self.providers.items()))
            return name, config
        raise ValueError("No providers configured. Call add_provider() first.")

    # Dispatch table for provider-specific API calls
    _PROVIDER_HANDLERS: dict[ModelProvider, str] = {
        ModelProvider.OPENAI: "_call_openai",
        ModelProvider.ANTHROPIC: "_call_anthropic",
        ModelProvider.OLLAMA: "_call_ollama",
    }

    async def chat(
        self,
        message: str,
        provider: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> GatewayResponse:
        """
        Send a chat completion request through the gateway.

        Routes to the specified provider, or the first available if
        *provider* is *None*.

        Args:
            message: The user message.
            provider: Provider name to route to.
            system: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.
            **kwargs: Additional arguments (ignored).

        Returns:
            A GatewayResponse with the model reply.

        Raises:
            ValueError: If no providers are configured.
            RuntimeError: If the provider's rate limit is exceeded.
        """
        provider, config = self._resolve_provider(provider)

        # Check rate limits
        config.check_rate_limit()

        # Route to provider
        start_time = time.time()

        try:
            handler_name = self._PROVIDER_HANDLERS.get(config.provider)
            if handler_name is None:
                raise ValueError(f"Unsupported provider: {config.provider}")
            handler = getattr(self, handler_name)
            response = await handler(config, message, system, temperature, max_tokens)
        except Exception as e:
            logger.error("Gateway error (%s): %s", provider, e)
            raise

        latency_ms = (time.time() - start_time) * 1000

        # Log request
        log_entry = {
            "provider": provider,
            "model": config.model,
            "latency_ms": latency_ms,
            "tokens": response.tokens_used,
            "timestamp": time.time(),
        }
        self._logs.append(log_entry)
        config.record_request()

        response.latency_ms = latency_ms
        return response

    async def _call_openai(
        self, config: ProviderConfig, message: str, system: str | None,
        temperature: float, max_tokens: int
    ) -> GatewayResponse:
        """Route a chat request to the OpenAI API.

        Args:
            config: Provider configuration.
            message: The user message.
            system: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.

        Returns:
            A GatewayResponse with the model reply.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})

        client = await self._pool.get_connection("openai")
        response = await client.post(
            f"{config.base_url or 'https://api.openai.com/v1'}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}"},
            json={
                "model": config.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()

        return GatewayResponse(
            content=data["choices"][0]["message"]["content"],
            model=config.model,
            provider=ModelProvider.OPENAI,
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
        )

    async def _call_anthropic(
        self, config: ProviderConfig, message: str, system: str | None,
        temperature: float, max_tokens: int
    ) -> GatewayResponse:
        """Route a chat request to the Anthropic API.

        Args:
            config: Provider configuration.
            message: The user message.
            system: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.

        Returns:
            A GatewayResponse with the model reply.
        """
        body: dict[str, Any] = {
            "model": config.model,
            "messages": [{"role": "user", "content": message}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            body["system"] = system

        client = await self._pool.get_connection("anthropic")
        response = await client.post(
            f"{config.base_url or 'https://api.anthropic.com/v1'}/messages",
            headers={
                "x-api-key": config.api_key or "",
                "anthropic-version": "2023-06-01",
            },
            json=body,
        )
        response.raise_for_status()
        data = response.json()

        return GatewayResponse(
            content=data["content"][0]["text"],
            model=config.model,
            provider=ModelProvider.ANTHROPIC,
            tokens_used=data.get("usage", {}).get("input_tokens", 0)
                      + data.get("usage", {}).get("output_tokens", 0),
        )

    async def _call_ollama(
        self, config: ProviderConfig, message: str, system: str | None,
        temperature: float, max_tokens: int
    ) -> GatewayResponse:
        """Route a chat request to a local Ollama instance.

        Args:
            config: Provider configuration.
            message: The user message.
            system: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.

        Returns:
            A GatewayResponse with the model reply.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})

        client = await self._pool.get_connection("ollama")
        response = await client.post(
            f"{config.base_url or 'http://localhost:11434'}/api/chat",
            json={
                "model": config.model,
                "messages": messages,
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()

        return GatewayResponse(
            content=data["message"]["content"],
            model=config.model,
            provider=ModelProvider.OLLAMA,
            tokens_used=data.get("eval_count", 0),
        )



    async def chat_batch(
        self,
        messages: list[str],
        provider: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        max_concurrent: int = 5,
    ) -> list[GatewayResponse]:
        """
        Send multiple chat requests concurrently.

        Args:
            messages: List of messages to send.
            provider: Provider name (or first available).
            system: Optional system prompt for all requests.
            temperature: Temperature for all requests.
            max_tokens: Max tokens for all requests.
            max_concurrent: Max concurrent requests.

        Returns:
            List of GatewayResponse objects.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _single_chat(msg: str) -> GatewayResponse:
            async with semaphore:
                return await self.chat(
                    message=msg,
                    provider=provider,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

        tasks = [_single_chat(msg) for msg in messages]
        return await asyncio.gather(*tasks)

    async def chat_streaming(
        self,
        message: str,
        provider: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> AsyncGenerator[str, None]:
        """
        Send a streaming chat request.

        Yields content chunks as they arrive from the provider.
        Falls back to a single non-streaming call for providers
        other than OpenAI.

        Args:
            message: The user message.
            provider: Provider name (or first available).
            system: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.

        Yields:
            Content strings as they are received.
        """
        provider, config = self._resolve_provider(provider)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})

        if config.provider == ModelProvider.OPENAI:
            client = await self._pool.get_connection("openai")
            async with client.stream(
                "POST",
                f"{config.base_url or 'https://api.openai.com/v1'}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        data = json.loads(line[6:])
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
        else:
            # Fallback to non-streaming for other providers
            result = await self.chat(message, provider, system, temperature, max_tokens)
            yield result.content

    def get_logs(self) -> list[dict[str, Any]]:
        """Return request logs."""
        return self._logs.copy()

    async def close(self) -> None:
        """Close the connection pool."""
        await self._pool.close()
