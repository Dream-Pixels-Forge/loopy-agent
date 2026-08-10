"""Tests for loopy.a2a — Agent-to-Agent protocol."""


import pytest

from loopy.a2a import (
    A2AClient,
    AgentCapability,
    AgentCard,
    AgentRegistry,
    AgentRequest,
    AgentResponse,
)


class TestAgentCapability:
    def test_capabilities(self):
        assert AgentCapability.TEXT_GENERATION.value == "text_generation"
        assert AgentCapability.CODE_GENERATION.value == "code_generation"


class TestAgentCard:
    def test_card_creation(self):
        card = AgentCard(
            name="code-bot",
            description="Writes code",
            version="1.0.0",
            capabilities=[AgentCapability.CODE_GENERATION],
            endpoint="http://localhost:8000",
        )
        assert card.name == "code-bot"

    def test_card_to_dict(self):
        card = AgentCard(
            name="test",
            description="desc",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="http://test",
        )
        d = card.to_dict()
        assert d["name"] == "test"
        assert "text_generation" in d["capabilities"]

    def test_card_from_dict(self):
        d = {
            "name": "bot",
            "description": "A bot",
            "version": "1.0",
            "capabilities": ["code_generation"],
            "endpoint": "http://bot",
        }
        card = AgentCard.from_dict(d)
        assert card.name == "bot"
        assert AgentCapability.CODE_GENERATION in card.capabilities


class TestAgentRegistry:
    def test_registry_creation(self):
        reg = AgentRegistry()
        assert len(reg.list_all()) == 0

    def test_register_agent(self):
        reg = AgentRegistry()
        card = AgentCard(
            name="agent-1",
            description="Test agent",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="http://test",
        )
        reg.register(card)
        assert len(reg.list_all()) == 1
        assert reg.get("agent-1") is not None

    def test_find_by_capability(self):
        reg = AgentRegistry()
        reg.register(AgentCard(
            name="text-bot",
            description="Text",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="http://text",
        ))
        reg.register(AgentCard(
            name="code-bot",
            description="Code",
            version="1.0",
            capabilities=[AgentCapability.CODE_GENERATION],
            endpoint="http://code",
        ))

        text_agents = reg.find_by_capability(AgentCapability.TEXT_GENERATION)
        assert len(text_agents) == 1
        assert text_agents[0].name == "text-bot"


class TestA2AClient:
    def test_client_creation(self):
        reg = AgentRegistry()
        client = A2AClient(reg)
        assert client.registry is reg

    @pytest.mark.asyncio
    async def test_call_agent(self):
        reg = AgentRegistry()
        reg.register(AgentCard(
            name="echo",
            description="Echo bot",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="",  # No remote endpoint → falls through to placeholder
        ))
        client = A2AClient(reg)
        response = await client.call("echo", "Hello")
        assert response.success is True
        # Should return placeholder since there's no handler or remote endpoint
        assert "placeholder" in str(response.metadata)

    @pytest.mark.asyncio
    async def test_call_agent_local_handler(self):
        """Test that a registered local handler is preferred over placeholder."""
        reg = AgentRegistry()
        reg.register(AgentCard(
            name="echo",
            description="Echo bot",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="http://remote",
        ))
        client = A2AClient(reg)

        async def echo_handler(request: AgentRequest) -> AgentResponse:
            return AgentResponse(result=f"Echo: {request.task}")

        client.register_handler("echo", echo_handler)
        response = await client.call("echo", "Hello")
        assert response.success is True
        assert response.result == "Echo: Hello"

    @pytest.mark.asyncio
    async def test_call_unknown_agent(self):
        reg = AgentRegistry()
        client = A2AClient(reg)
        response = await client.call("nonexistent", "Hello")
        assert response.success is False
        assert "not found" in response.error

    @pytest.mark.asyncio
    async def test_broadcast(self):
        reg = AgentRegistry()
        reg.register(AgentCard(
            name="a1",
            description="Agent 1",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="",  # No remote endpoint → placeholder
        ))
        reg.register(AgentCard(
            name="a2",
            description="Agent 2",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="",
        ))
        client = A2AClient(reg)
        responses = await client.broadcast(AgentCapability.TEXT_GENERATION, "Test")
        assert len(responses) == 2
