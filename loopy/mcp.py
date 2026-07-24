"""
MCP — One interface, every tool.

Model Context Protocol client for connecting to MCP servers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

import httpx

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
class ToolResult:
    """Result of a tool call."""
    
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

    def __init__(self, server_url: str, api_key: str | None = None):
        """
        Args:
            server_url: URL of the MCP server
            api_key: Optional API key for authentication
        """
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

        logger.info(f"Listed {len(self._tools)} tools from {self.server_url}")
        return self._tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolResult:
        """
        Call a tool on the MCP server.
        
        Args:
            name: Tool name
            arguments: Tool arguments
        
        Returns:
            ToolResult with the response
        """
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

        return ToolResult(
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
    ) -> ToolResult:
        """Call a registered tool."""
        if name not in self._handlers:
            return ToolResult(
                content=f"Tool not found: {name}",
                is_error=True,
            )

        try:
            result = await self._handlers[name](**(arguments or {}))
            return ToolResult(content=str(result))
        except Exception as e:
            return ToolResult(
                content=str(e),
                is_error=True,
            )
