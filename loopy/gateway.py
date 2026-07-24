"""
AI Gateway — One control plane, many models.

Unified interface to route requests across OpenAI, Anthropic, and open-source providers.
Includes auth management, rate limiting, logging, and connection pooling.
"""

from __future__ import annotations

import asyncio
import logging
import time
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
    """Configuration for a single LLM provider."""
    
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
    
    Example:
        pool = ConnectionPool(max_size=10)
        async with pool.get_connection("openai") as client:
            response = await client.post(...)
    """
    
    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self._connections: dict[str, httpx.AsyncClient] = {}
        self._lock = asyncio.Lock()
    
    async def get_connection(self, provider: str) -> httpx.AsyncClient:
        """Get or create a connection for a provider."""
        async with self._lock:
            if provider not in self._connections:
                if len(self._connections) >= self.max_size:
                    # Evict oldest connection
                    oldest = next(iter(self._connections))
                    await self._connections[oldest].aclose()
                    del self._connections[oldest]
                
                self._connections[provider] = httpx.AsyncClient(
                    timeout=60.0,
                    limits=httpx.Limits(
                        max_connections=5,
                        max_keepalive_connections=2,
                    ),
                )
            
            return self._connections[provider]
    
    async def close(self) -> None:
        """Close all connections in the pool."""
        for client in self._connections.values():
            await client.aclose()
        self._connections.clear()
    
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
        self._pool = ConnectionPool()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False

    def __init__(self):
        self.providers: dict[str, ProviderConfig] = {}
        self._client = httpx.AsyncClient(timeout=60.0)
        self._pool: ConnectionPool | None = None
        self._logs: list[dict[str, Any]] = []

    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """Register a provider."""
        self.providers[name] = config
        logger.info(f"Added provider: {name} ({config.provider.value})")

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
        
        Routes to specified provider, or first available if not specified.
        """
        # Select provider
        if provider and provider in self.providers:
            config = self.providers[provider]
        elif self.providers:
            name, config = next(iter(self.providers.items()))
            provider = name
        else:
            raise ValueError("No providers configured. Call add_provider() first.")

        # Check rate limits
        self._check_rate_limit(config)
        
        # Route to provider
        start_time = time.time()
        
        try:
            if config.provider == ModelProvider.OPENAI:
                response = await self._call_openai(config, message, system, temperature, max_tokens)
            elif config.provider == ModelProvider.ANTHROPIC:
                response = await self._call_anthropic(config, message, system, temperature, max_tokens)
            elif config.provider == ModelProvider.OLLAMA:
                response = await self._call_ollama(config, message, system, temperature, max_tokens)
            else:
                raise ValueError(f"Unsupported provider: {config.provider}")
        except Exception as e:
            logger.error(f"Gateway error ({provider}): {e}")
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
        config._request_count += 1

        response.latency_ms = latency_ms
        return response

    async def _call_openai(
        self, config: ProviderConfig, message: str, system: str | None,
        temperature: float, max_tokens: int
    ) -> GatewayResponse:
        """Route to OpenAI API."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})

        response = await self._client.post(
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
        """Route to Anthropic API."""
        body: dict[str, Any] = {
            "model": config.model,
            "messages": [{"role": "user", "content": message}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            body["system"] = system

        response = await self._client.post(
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
        """Route to local Ollama instance."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})

        response = await self._client.post(
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

    def _check_rate_limit(self, config: ProviderConfig) -> None:
        """Check and enforce rate limits."""
        now = time.time()
        if now - config._window_start > 60:
            config._request_count = 0
            config._window_start = now
        
        if config._request_count >= config.rpm:
            raise RuntimeError(f"Rate limit exceeded for {config.provider.value}")

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
            messages: List of messages to send
            provider: Provider name (or first available)
            system: Optional system prompt for all requests
            temperature: Temperature for all requests
            max_tokens: Max tokens for all requests
            max_concurrent: Max concurrent requests
        
        Returns:
            List of GatewayResponse objects
        """
        import asyncio
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
    ) -> Any:
        """
        Send a streaming chat request (returns async generator).
        
        Yields chunks of the response as they arrive.
        """
        if provider and provider in self.providers:
            config = self.providers[provider]
        elif self.providers:
            name, config = next(iter(self.providers.items()))
            provider = name
        else:
            raise ValueError("No providers configured")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})

        if config.provider == ModelProvider.OPENAI:
            async with self._client.stream(
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
                        import json
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
        """Close the HTTP client and connection pool."""
        await self._client.aclose()
        if self._pool:
            await self._pool.close()
