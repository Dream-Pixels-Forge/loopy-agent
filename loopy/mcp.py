"""
MCP — One interface, every tool.

Model Context Protocol client for connecting to MCP servers.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from loopy.netutil import validate_outbound_url

logger = logging.getLogger("loopy.mcp")


@dataclass
class Tool:
    """An MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """A request to call a tool."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPToolResult:
    """Result of a tool call via MCP server."""

    content: str | list[dict[str, Any]]
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """
    Model Context Protocol client.

    Connects to MCP servers and exposes their tools.

    Example:
        client = MCPClient("http://localhost:3000")

        # List available tools
        tools = await client.list_tools()
        for tool in tools:
            print(f"{tool.name}: {tool.description}")

        # Call a tool
        result = await client.call_tool("get_weather", {"city": "Portland"})
    """

    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        *,
        allow_private: bool = True,
    ):
        """
        Args:
            server_url: URL of the MCP server.
            api_key: Optional API key for authentication.
            allow_private: Permit loopback/private/link-local hosts. Keep
                True when *server_url* is operator-controlled (local MCP
                servers are the norm). Set False when the URL can be
                influenced by model output or other untrusted content — the
                SSRF guard then rejects internal destinations.

        Raises:
            ValueError: If the URL scheme is not http(s) or it has no host.
        """
        validate_outbound_url(server_url, allow_private=allow_private)
        self.server_url = server_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0)
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

        self._tools: list[Tool] = []

    async def list_tools(self) -> list[Tool]:
        """
        List available tools from the MCP server.

        Returns:
            List of Tool definitions
        """
        response = await self._client.post(
            f"{self.server_url}/list_tools",
            headers=self._headers,
            json={},
        )
        response.raise_for_status()
        data = response.json()

        self._tools = [
            Tool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {}),
                annotations=t.get("annotations", {}),
            )
            for t in data.get("tools", [])
        ]

        logger.info("Listed %d tools from %s", len(self._tools), self.server_url)
        return self._tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        """
        Call a tool on the MCP server.

        Validates that the tool name exists in the cached tool list
        before sending the request.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            MCPToolResult with the response

        Raises:
            ValueError: If tool name is not in the cached tool list.
        """
        # Validate tool name against cached list.
        # Skip validation if tools haven't been loaded yet (call
        # list_tools() first to enable client-side validation).
        if self._tools and not any(t.name == name for t in self._tools):
            return MCPToolResult(
                content=f"Tool not found: {name}",
                is_error=True,
            )

        payload = {
            "name": name,
            "arguments": arguments or {},
        }

        response = await self._client.post(
            f"{self.server_url}/call_tool",
            headers=self._headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        return MCPToolResult(
            content=data.get("content", ""),
            is_error=data.get("is_error", False),
            metadata=data.get("metadata", {}),
        )

    async def health_check(self) -> bool:
        """Check if the MCP server is healthy."""
        try:
            response = await self._client.get(
                f"{self.server_url}/health",
                headers=self._headers,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the client."""
        await self._client.aclose()

    async def __aenter__(self) -> MCPClient:
        return self

    async def __aexit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any
    ) -> None:
        await self.close()


class LocalMCP:
    """
    Local MCP server for testing without a running server.

    Registers tools locally and routes calls to handlers.

    Example:
        mcp = LocalMCP()

        @mcp.tool("get_weather", "Get weather for a city")
        async def get_weather(city: str) -> str:
            return f"Sunny in {city}"

        result = await mcp.call_tool("get_weather", {"city": "Portland"})
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {}

    def tool(
        self,
        name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
    ) -> Callable:
        """Decorator to register a tool handler."""

        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable:
            self._tools[name] = Tool(
                name=name,
                description=description,
                input_schema=input_schema or {},
            )
            self._handlers[name] = fn
            return fn

        return decorator

    async def list_tools(self) -> list[Tool]:
        """List registered tools."""
        return list(self._tools.values())

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        """Call a registered tool."""
        if name not in self._handlers:
            return MCPToolResult(
                content=f"Tool not found: {name}",
                is_error=True,
            )

        try:
            result = await self._handlers[name](**(arguments or {}))
            return MCPToolResult(content=str(result))
        except Exception as e:
            return MCPToolResult(
                content=str(e),
                is_error=True,
            )
