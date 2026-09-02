"""MCP coverage tests — MCPClient HTTP paths, LocalMCP error paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loopy.mcp import LocalMCP, MCPClient, MCPToolResult, Tool

# ── MCPClient ────────────────────────────────────────────────


class TestMCPClientHTTP:
    @pytest.mark.asyncio
    async def test_list_tools(self):
        client = MCPClient("http://localhost:3000")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Weather",
                    "input_schema": {},
                    "annotations": {},
                },
            ]
        }

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            tools = await client.list_tools()

        assert len(tools) == 1
        assert tools[0].name == "get_weather"
        assert isinstance(tools[0], Tool)

    @pytest.mark.asyncio
    async def test_call_tool(self):
        client = MCPClient("http://localhost:3000")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "content": "Sunny, 72°F",
            "is_error": False,
            "metadata": {},
        }

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.call_tool("get_weather", {"city": "Portland"})

        assert isinstance(result, MCPToolResult)
        assert result.content == "Sunny, 72°F"
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        client = MCPClient("http://localhost:3000")
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            ok = await client.health_check()
        assert ok is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        client = MCPClient("http://localhost:3000")
        with patch.object(
            client._client, "get", new_callable=AsyncMock, side_effect=ConnectionError("refused")
        ):
            ok = await client.health_check()
        assert ok is False

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with MCPClient("http://localhost:3000") as client:
            assert isinstance(client, MCPClient)


# ── LocalMCP ─────────────────────────────────────────────────


class TestLocalMCP:
    @pytest.mark.asyncio
    async def test_decorator_registers_tool(self):
        mcp = LocalMCP()

        @mcp.tool("greet", "Say hello")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        tools = await mcp.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "greet"

    @pytest.mark.asyncio
    async def test_call_registered_tool(self):
        mcp = LocalMCP()

        @mcp.tool("add", "Add two numbers")
        async def add(a: int, b: int) -> int:
            return a + b

        result = await mcp.call_tool("add", {"a": 3, "b": 4})
        assert result.content == "7"
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self):
        mcp = LocalMCP()
        result = await mcp.call_tool("nonexistent")
        assert result.is_error is True
        assert "not found" in result.content.lower()

    @pytest.mark.asyncio
    async def test_call_tool_raises(self):
        mcp = LocalMCP()

        @mcp.tool("fail", "Always fails")
        async def fail() -> str:
            raise ValueError("bad input")

        result = await mcp.call_tool("fail")
        assert result.is_error is True
        assert "bad input" in result.content
