"""Gateway coverage tests — provider handlers, streaming, connection pool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from loopy.gateway import (
    ConnectionPool,
    Gateway,
    ModelProvider,
    ProviderConfig,
)

# ── Helpers ──────────────────────────────────────────────────

def _openai_config(**overrides) -> ProviderConfig:
    return ProviderConfig(
        provider=ModelProvider.OPENAI,
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="gpt-4",
        **overrides,
    )


def _anthropic_config(**overrides) -> ProviderConfig:
    return ProviderConfig(
        provider=ModelProvider.ANTHROPIC,
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com/v1",
        model="claude-3-opus",
        **overrides,
    )


def _ollama_config(**overrides) -> ProviderConfig:
    return ProviderConfig(
        provider=ModelProvider.OLLAMA,
        base_url="http://localhost:11434",
        model="llama3",
        **overrides,
    )


def _mock_openai_response(content="Hello!", tokens=10):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {"total_tokens": tokens},
    }
    return resp


def _mock_anthropic_response(content="Hello!", input_tokens=5, output_tokens=5):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "content": [{"text": content}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    return resp


def _mock_ollama_response(content="Hello!", eval_count=8):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "message": {"content": content},
        "eval_count": eval_count,
    }
    return resp


# ── ProviderConfig rate limiting ─────────────────────────────

class TestProviderConfigRateLimit:
    def test_check_rate_limit_ok(self):
        config = _openai_config(rpm=10)
        config.check_rate_limit()  # should not raise

    def test_check_rate_limit_exceeded(self):
        config = _openai_config(rpm=2)
        config.record_request()
        config.record_request()
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            config.check_rate_limit()

    def test_window_reset(self):
        import time
        config = _openai_config(rpm=1)
        config.record_request()
        # Force window reset
        config._window_start = time.time() - 61
        config.check_rate_limit()  # should reset and pass


# ── Gateway resolve_provider ─────────────────────────────────

class TestGatewayResolve:
    def test_resolve_specific_provider(self):
        gw = Gateway()
        gw.add_provider("openai", _openai_config())
        gw.add_provider("anthropic", _anthropic_config())
        name, cfg = gw._resolve_provider("anthropic")
        assert name == "anthropic"
        assert cfg.provider == ModelProvider.ANTHROPIC

    def test_resolve_first_available(self):
        gw = Gateway()
        gw.add_provider("openai", _openai_config())
        name, cfg = gw._resolve_provider(None)
        assert name == "openai"

    def test_resolve_no_providers(self):
        gw = Gateway()
        with pytest.raises(ValueError, match="No providers"):
            gw._resolve_provider()


# ── Gateway async context manager ────────────────────────────

class TestGatewayContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        async with Gateway() as gw:
            gw.add_provider("openai", _openai_config())
            assert "openai" in gw.providers
            assert gw._pool is not None
        # After exit, client should be closed


# ── ConnectionPool ───────────────────────────────────────────

class TestConnectionPool:
    @pytest.mark.asyncio
    async def test_get_connection_creates(self):
        pool = ConnectionPool(max_size=3)
        client = await pool.get_connection("openai")
        assert isinstance(client, httpx.AsyncClient)
        await pool.close()

    @pytest.mark.asyncio
    async def test_get_connection_reuses(self):
        pool = ConnectionPool()
        c1 = await pool.get_connection("openai")
        c2 = await pool.get_connection("openai")
        assert c1 is c2
        await pool.close()

    @pytest.mark.asyncio
    async def test_pool_eviction(self):
        pool = ConnectionPool(max_size=2)
        await pool.get_connection("a")
        await pool.get_connection("b")
        await pool.get_connection("c")  # should evict "a"
        assert pool.stats()["active_connections"] == 2
        await pool.close()

    def test_stats(self):
        pool = ConnectionPool(max_size=5)
        stats = pool.stats()
        assert stats["max_size"] == 5
        assert stats["active_connections"] == 0


# ── Gateway chat with mocked HTTP ────────────────────────────

class TestGatewayChat:
    @pytest.mark.asyncio
    async def test_chat_openai(self):
        gw = Gateway()
        gw.add_provider("openai", _openai_config())

        mock_resp = _mock_openai_response("Hi there!", 15)
        with patch.object(gw._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await gw.chat("Hello", provider="openai")

        assert result.content == "Hi there!"
        assert result.tokens_used == 15
        assert result.provider == ModelProvider.OPENAI
        assert len(gw.get_logs()) == 1

    @pytest.mark.asyncio
    async def test_chat_anthropic(self):
        gw = Gateway()
        gw.add_provider("anthropic", _anthropic_config())

        mock_resp = _mock_anthropic_response("Anthropic says hi", 8, 6)
        with patch.object(gw._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await gw.chat("Hello", provider="anthropic")

        assert result.content == "Anthropic says hi"
        assert result.tokens_used == 14

    @pytest.mark.asyncio
    async def test_chat_ollama(self):
        gw = Gateway()
        gw.add_provider("ollama", _ollama_config())

        mock_resp = _mock_ollama_response("Local model", 12)
        with patch.object(gw._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await gw.chat("Hello", provider="ollama")

        assert result.content == "Local model"
        assert result.tokens_used == 12

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self):
        gw = Gateway()
        gw.add_provider("openai", _openai_config())

        mock_resp = _mock_openai_response("OK")
        with patch.object(gw._client, "post",
                          new_callable=AsyncMock,
                          return_value=mock_resp) as mock_post:
            await gw.chat("Hello", provider="openai", system="Be helpful")

        call_args = mock_post.call_args
        messages = call_args[1]["json"]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_chat_no_providers(self):
        gw = Gateway()
        with pytest.raises(ValueError, match="No providers"):
            await gw.chat("Hello")

    @pytest.mark.asyncio
    async def test_chat_logs_latency(self):
        gw = Gateway()
        gw.add_provider("openai", _openai_config())
        mock_resp = _mock_openai_response("ok")
        with patch.object(gw._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await gw.chat("Hi", provider="openai")
        assert result.latency_ms >= 0
        log = gw.get_logs()[0]
        assert "latency_ms" in log


# ── Gateway chat_batch ───────────────────────────────────────

class TestGatewayBatch:
    @pytest.mark.asyncio
    async def test_chat_batch(self):
        gw = Gateway()
        gw.add_provider("openai", _openai_config())
        mock_resp = _mock_openai_response("ok")
        with patch.object(gw._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            results = await gw.chat_batch(["a", "b", "c"], provider="openai")
        assert len(results) == 3


# ── Gateway chat_streaming ───────────────────────────────────

class TestGatewayStreaming:
    @pytest.mark.asyncio
    async def test_streaming_non_openai_fallback(self):
        gw = Gateway()
        gw.add_provider("anthropic", _anthropic_config())
        mock_resp = _mock_anthropic_response("Fallback content")
        with patch.object(gw._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            chunks = []
            async for chunk in gw.chat_streaming("Hello", provider="anthropic"):
                chunks.append(chunk)
        assert "".join(chunks) == "Fallback content"

    @pytest.mark.asyncio
    async def test_streaming_openai(self):
        gw = Gateway()
        gw.add_provider("openai", _openai_config())

        # Mock streaming response with async iterator
        lines = [
            'data: {"choices":[{"delta":{"content":"Hi"}}]}',
            'data: {"choices":[{"delta":{"content":" there"}}]}',
            "data: [DONE]",
        ]

        async def async_iter(lines):
            for line in lines:
                yield line

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = lambda: async_iter(lines)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gw._client, "stream", return_value=mock_ctx):
            chunks = []
            async for chunk in gw.chat_streaming("Hello", provider="openai"):
                chunks.append(chunk)

        assert chunks == ["Hi", " there"]


# ── Gateway get_logs / close ─────────────────────────────────

class TestGatewayMisc:
    def test_get_logs_returns_copy(self):
        gw = Gateway()
        logs = gw.get_logs()
        logs.append({"fake": True})
        assert gw.get_logs() == []

    @pytest.mark.asyncio
    async def test_close(self):
        gw = Gateway()
        await gw.close()  # should not raise
