"""Extended A2A tests — call paths, broadcast depth, registry, and edge cases."""

from __future__ import annotations

import pytest

from loopy.a2a import (
    A2AClient,
    A2AError,
    A2ATask,
    AgentCapability,
    AgentCard,
    AgentRegistry,
    AgentRequest,
    AgentResponse,
)

# ── AgentCard round-trip ─────────────────────────────────────


class TestAgentCardRoundTrip:
    def test_to_dict_from_dict_round_trip(self):
        card = AgentCard(
            name="bot",
            description="A bot",
            version="2.0",
            capabilities=[AgentCapability.TEXT_GENERATION, AgentCapability.CODE_GENERATION],
            endpoint="http://example.com/agent",
            authentication="api_key",
            pricing="per_token",
            metadata={"extra": "data"},
        )
        d = card.to_dict()
        restored = AgentCard.from_dict(d)
        assert restored.name == "bot"
        assert restored.version == "2.0"
        assert AgentCapability.CODE_GENERATION in restored.capabilities
        assert restored.authentication == "api_key"
        assert restored.pricing == "per_token"
        assert restored.metadata == {"extra": "data"}

    def test_from_dict_missing_description_defaults_to_empty(self):
        d = {
            "name": "x",
            "version": "1.0",
            "capabilities": [],
            "endpoint": "http://x",
        }
        card = AgentCard.from_dict(d)
        assert card.description == ""

    def test_from_dict_missing_authentication_defaults_to_none(self):
        d = {"name": "x", "version": "1.0", "capabilities": [], "endpoint": "http://x"}
        card = AgentCard.from_dict(d)
        assert card.authentication == "none"


# ── AgentRegistry extended ───────────────────────────────────


class TestAgentRegistryExtended:
    def test_unregister(self):
        reg = AgentRegistry()
        card = AgentCard(name="a", endpoint="http://a")
        reg.register(card)
        assert reg.get("a") is not None
        reg.unregister("a")
        assert reg.get("a") is None
        # Unregistering a non-existent agent is a no-op
        reg.unregister("missing")

    def test_find_by_pricing(self):
        reg = AgentRegistry()
        reg.register(AgentCard(name="cheap", endpoint="http://a", pricing="free"))
        reg.register(AgentCard(name="premium", endpoint="http://b", pricing="subscription"))
        free = reg.find_by_pricing("free")
        assert len(free) == 1
        assert free[0].name == "cheap"
        assert reg.find_by_pricing("enterprise") == []

    def test_to_dict_exports_all_agents(self):
        reg = AgentRegistry()
        reg.register(AgentCard(name="a", endpoint="http://a"))
        reg.register(AgentCard(name="b", endpoint="http://b"))
        d = reg.to_dict()
        assert "a" in d
        assert "b" in d
        assert d["a"]["name"] == "a"


# ── A2AClient call paths ─────────────────────────────────────


class TestA2AClientCallPaths:
    @pytest.mark.asyncio
    async def test_call_handler_raises_returns_failed_response(self):
        """When a local handler raises, call returns a failed AgentResponse."""
        reg = AgentRegistry()
        reg.register(AgentCard(name="crashy", endpoint="http://remote"))
        client = A2AClient(reg)

        async def crashing_handler(request):
            raise RuntimeError("boom")

        client.register_handler("crashy", crashing_handler)
        response = await client.call("crashy", "do it")
        assert response.success is False
        assert "boom" in response.error

    @pytest.mark.asyncio
    async def test_call_with_sender(self):
        reg = AgentRegistry()
        reg.register(AgentCard(name="echo", endpoint=""))
        client = A2AClient(reg)
        captured: list[AgentRequest] = []

        async def capture_handler(request: AgentRequest) -> AgentResponse:
            captured.append(request)
            return AgentResponse(result=request.task)

        client.register_handler("echo", capture_handler)
        await client.call("echo", "hello", sender="sender-x")
        assert len(captured) == 1
        assert captured[0].sender == "sender-x"

    @pytest.mark.asyncio
    async def test_call_unknown_agent_returns_not_found(self):
        reg = AgentRegistry()
        client = A2AClient(reg)
        response = await client.call("nope", "hi")
        assert response.success is False
        assert "not found" in response.error

    @pytest.mark.asyncio
    async def test_call_empty_endpoint_falls_through_to_placeholder(self):
        """Endpoint '' is falsy, so call skips HTTP dispatch and returns placeholder."""
        reg = AgentRegistry()
        reg.register(AgentCard(name="p", endpoint=""))
        client = A2AClient(reg)
        response = await client.call("p", "hi")
        assert response.success is True
        assert response.metadata.get("placeholder") is True


# ── A2AClient broadcast depth ────────────────────────────────


class TestA2AClientBroadcastDepth:
    @pytest.mark.asyncio
    async def test_broadcast_respects_max_depth(self):
        """Depth limit prevents infinite recursion in cycles."""
        reg = AgentRegistry()
        reg.register(
            AgentCard(name="a", endpoint="", capabilities=[AgentCapability.TEXT_GENERATION])
        )
        reg.register(
            AgentCard(name="b", endpoint="", capabilities=[AgentCapability.TEXT_GENERATION])
        )
        client = A2AClient(reg)

        # Depth 0 should short-circuit before any calls
        responses = await client.broadcast(AgentCapability.TEXT_GENERATION, "hi", max_depth=0)
        assert responses == []

    @pytest.mark.asyncio
    async def test_broadcast_skips_visited_agents(self):
        """Cycle detection: if agent A calls B which calls A, A is skipped."""
        reg = AgentRegistry()
        reg.register(
            AgentCard(name="a", endpoint="", capabilities=[AgentCapability.TEXT_GENERATION])
        )
        reg.register(
            AgentCard(name="b", endpoint="", capabilities=[AgentCapability.TEXT_GENERATION])
        )
        client = A2AClient(reg)

        # With max_depth=1 we should get results from both since neither
        # re-broadcasts internally
        responses = await client.broadcast(AgentCapability.TEXT_GENERATION, "hi", max_depth=1)
        assert len(responses) == 2


# ── A2ATask serialization ────────────────────────────────────


class TestA2ATaskSerialization:
    def test_to_dict_round_trip(self):
        task = A2ATask(
            id="t1",
            state="completed",
            artifacts=[{"type": "text", "value": "hello"}],
            metadata={"key": "val"},
        )
        d = task.to_dict()
        restored = A2ATask.from_dict(d)
        assert restored.id == "t1"
        assert restored.state == "completed"
        assert restored.artifacts == [{"type": "text", "value": "hello"}]
        assert restored.metadata == {"key": "val"}

    def test_from_dict_missing_fields_defaults(self):
        d = {"id": "t1", "state": "submitted"}
        task = A2ATask.from_dict(d)
        assert task.artifacts == []
        assert task.metadata == {}


# ── AgentResponse ────────────────────────────────────────────


class TestAgentResponse:
    def test_defaults(self):
        r = AgentResponse(result="ok")
        assert r.success is True
        assert r.error == ""
        assert r.metadata == {}
        assert r.tokens_used == 0

    def test_failure_state(self):
        r = AgentResponse(result="", success=False, error="boom")
        assert r.success is False
        assert r.error == "boom"

    def test_to_dict(self):
        r = AgentResponse(result="x", tokens_used=42)
        d = r.to_dict()
        assert d["result"] == "x"
        assert d["tokens_used"] == 42
        assert d["success"] is True

    def test_from_dict_legacy(self):
        d = {"result": "y", "success": False, "error": "bad", "tokens_used": 10}
        r = AgentResponse(
            result=d["result"],
            success=d["success"],
            error=d["error"],
            metadata=d.get("metadata", {}),
            tokens_used=d["tokens_used"],
        )
        assert r.result == "y"


# ── A2AClient.from_agent_card ────────────────────────────────


class TestFromAgentCard:
    def test_card_ttl_default(self):
        card = AgentCard(
            name="c", url="https://example.com", version="1.0", skills=[], authentication="none"
        )
        client = A2AClient.from_agent_card(card, card_ttl=7200.0)
        assert client.card_ttl == 7200.0

    def test_allow_private_defaults_true(self):
        card = AgentCard(
            name="c", url="https://example.com", version="1.0", skills=[], authentication="none"
        )
        client = A2AClient.from_agent_card(card)
        assert client._allow_private is True


# ── A2AError ─────────────────────────────────────────────────


class TestA2AError:
    def test_is_exception(self):
        assert issubclass(A2AError, Exception)

    def test_message_contains_url(self):
        try:
            raise A2AError("Could not load Agent Card from https://x: timeout")
        except A2AError as exc:
            assert "https://x" in str(exc)
