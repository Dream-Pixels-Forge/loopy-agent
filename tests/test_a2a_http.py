"""Extended A2A HTTP tests — _post_json, _get_json, _sse_events, verify_webhook."""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loopy.a2a import (
    A2AClient,
    AgentCard,
    AgentRegistry,
)

# ── _post_json ─────────────────────────────────────────────────


class TestPostJson:
    @pytest.mark.asyncio
    async def test_post_json_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "t1", "state": "submitted"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("loopy.a2a.httpx.AsyncClient", return_value=mock_client):
            client = A2AClient(AgentRegistry())
            result = await client._post_json("http://example.com/tasks", json={"skill_id": "t"})
            assert result["id"] == "t1"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_json_raises_on_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock(side_effect=Exception("bad status"))

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("loopy.a2a.httpx.AsyncClient", return_value=mock_client):
            client = A2AClient(AgentRegistry())
            with pytest.raises(Exception, match="bad status"):
                await client._post_json("http://example.com", json={})


# ── _get_json ──────────────────────────────────────────────────


class TestGetJson:
    @pytest.mark.asyncio
    async def test_get_json_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "t2", "state": "completed"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("loopy.a2a.httpx.AsyncClient", return_value=mock_client):
            client = A2AClient(AgentRegistry())
            result = await client._get_json("http://example.com/tasks/t2")
            assert result["id"] == "t2"

    @pytest.mark.asyncio
    async def test_get_json_raises_on_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock(side_effect=Exception("not found"))

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("loopy.a2a.httpx.AsyncClient", return_value=mock_client):
            client = A2AClient(AgentRegistry())
            with pytest.raises(Exception, match="not found"):
                await client._get_json("http://example.com/tasks/x")


# ── _sse_events ────────────────────────────────────────────────


class TestSSEEvents:
    @pytest.mark.asyncio
    async def test_sse_events_parses_data_lines(self):
        events = [
            {"event": "start"},
            {"event": "progress", "value": 50},
            {"event": "done"},
        ]

        async def fake_sse(url):
            for ev in events:
                yield ev

        client = A2AClient(AgentRegistry())
        client._sse_events = fake_sse  # type: ignore[assignment]
        collected = [ev async for ev in client._sse_events("http://example.com/stream")]
        assert len(collected) == 3
        assert collected[0]["event"] == "start"
        assert collected[1]["value"] == 50
        assert collected[2]["event"] == "done"

    @pytest.mark.asyncio
    async def test_sse_events_skips_empty_data_lines(self):
        events = [
            {"e": "a"},
            {"e": "b"},
        ]

        async def fake_sse(url):
            for ev in events:
                yield ev

        client = A2AClient(AgentRegistry())
        client._sse_events = fake_sse  # type: ignore[assignment]
        collected = [ev async for ev in client._sse_events("http://example.com/stream")]
        assert len(collected) == 2


# ── verify_webhook ─────────────────────────────────────────────


class TestVerifyWebhook:
    def _make_client(self):
        card = AgentCard(name="c", url="http://x", version="1.0", capabilities=[], endpoint="")
        return A2AClient.from_agent_card(card)

    def test_valid_signature(self):
        client = self._make_client()
        body = b"hello world"
        secret = b"my-secret"
        sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
        assert client.verify_webhook(body, sig, secret) is True

    def test_invalid_signature(self):
        client = self._make_client()
        body = b"hello world"
        secret = b"my-secret"
        bad_sig = "0" * 64
        assert client.verify_webhook(body, bad_sig, secret) is False

    def test_wrong_secret(self):
        client = self._make_client()
        body = b"hello world"
        secret = b"my-secret"
        other_secret = b"other-secret"
        sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
        assert client.verify_webhook(body, sig, other_secret) is False

    def test_empty_body(self):
        client = self._make_client()
        secret = b"secret"
        sig = hmac.new(secret, b"", hashlib.sha256).hexdigest()
        assert client.verify_webhook(b"", sig, secret) is True

    def test_signature_too_short_returns_false(self):
        client = self._make_client()
        body = b"hello"
        secret = b"secret"
        assert client.verify_webhook(body, "short", secret) is False

    def test_signature_not_string_returns_false(self):
        client = self._make_client()
        body = b"hello"
        secret = b"secret"
        assert client.verify_webhook(body, 12345, secret) is False


# ── fetch_agent_card ───────────────────────────────────────────


class TestFetchAgentCard:
    @pytest.mark.asyncio
    async def test_fetch_agent_card_success(self):
        payload = {
            "name": "remote-agent",
            "version": "2.0",
            "capabilities": ["text-generation"],
            "endpoint": "http://remote:8080",
        }
        client = A2AClient(AgentRegistry())
        with patch.object(client, "_fetch_json", AsyncMock(return_value=payload)):
            card = await client.fetch_agent_card("http://remote:8080/.well-known/agent-card.json")
        assert card.name == "remote-agent"
        assert card.version == "2.0"

    @pytest.mark.asyncio
    async def test_fetch_agent_card_http_error(self):
        from loopy.a2a import A2AError

        client = A2AClient(AgentRegistry())
        with (
            patch.object(
                client, "_fetch_json", AsyncMock(side_effect=Exception("connection failed"))
            ),
            pytest.raises(A2AError, match="Agent Card"),
        ):
            await client.fetch_agent_card("http://bad-host/.well-known/agent-card.json")

    @pytest.mark.asyncio
    async def test_fetch_agent_card_bad_status(self):
        from loopy.a2a import A2AError

        client = A2AClient(AgentRegistry())
        with (
            patch.object(client, "_fetch_json", AsyncMock(side_effect=Exception("not found"))),
            pytest.raises(A2AError, match="Agent Card"),
        ):
            await client.fetch_agent_card("http://example.com/.well-known/agent-card.json")


# ── A2AClient._endpoint ────────────────────────────────────────


class TestEndpoint:
    def test_endpoint_from_url(self):
        card = AgentCard(
            name="c", url="http://example.com/agent", version="1.0", capabilities=[], endpoint=""
        )
        client = A2AClient.from_agent_card(card)
        assert client._endpoint() == "http://example.com/agent"

    def test_endpoint_from_endpoint_fallback(self):
        card = AgentCard(
            name="c", url="", version="1.0", capabilities=[], endpoint="http://fallback:9000"
        )
        client = A2AClient.from_agent_card(card)
        assert client._endpoint() == "http://fallback:9000"

    def test_endpoint_strips_trailing_slash(self):
        card = AgentCard(
            name="c", url="http://example.com/agent/", version="1.0", capabilities=[], endpoint=""
        )
        client = A2AClient.from_agent_card(card)
        assert client._endpoint() == "http://example.com/agent"


# ── A2AClient.create_task ─────────────────────────────────────


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_create_task_basic(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "t-new", "state": "submitted"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("loopy.a2a.httpx.AsyncClient", return_value=mock_client):
            card = AgentCard(
                name="c",
                url="http://example.com",
                version="1.0",
                skills=[{"id": "text", "description": "process text"}],
                endpoint="",
            )
            client = A2AClient.from_agent_card(card)
            task = await client.create_task("text", {"q": "hi"})
            assert task.id == "t-new"
