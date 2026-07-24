"""
Tools Plugin — Tool-use with function calling.

Provides a registry for tools that agents can use during execution.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loopy.plugins import Plugin, PluginInfo, PluginRegistry

logger = logging.getLogger("loopy.plugins.tools")


@dataclass
class ToolParameter:
    """A tool parameter definition."""
    
    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str = ""
    required: bool = True
    default: Any = None
    
    def to_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format."""
        schema: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass
class Tool:
    """A tool that agents can use."""
    
    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    parameters: list[ToolParameter] = field(default_factory=list)
    
    def to_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling schema."""
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


@dataclass
class ToolResult:
    """Result of a tool execution."""
    
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """
    Registry for tools that agents can use.
    
    Example:
        registry = ToolRegistry()
        
        # Register a tool
        registry.register(Tool(
            name="get_weather",
            description="Get weather for a location",
            handler=get_weather_fn,
            parameters=[
                ToolParameter(name="location", type="string", description="City name"),
            ],
        ))
        
        # Execute a tool
        result = await registry.execute("get_weather", {"location": "Portland"})
    """
    
    def __init__(self):
        self.tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def list_all(self) -> list[Tool]:
        """List all registered tools."""
        return list(self.tools.values())
    
    def list_schemas(self) -> list[dict[str, Any]]:
        """List all tool schemas (for OpenAI function calling)."""
        return [tool.to_schema() for tool in self.tools.values()]
    
    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """
        Execute a tool by name.
        
        Args:
            name: Tool name
            arguments: Tool arguments
        
        Returns:
            ToolResult with output or error
        """
        tool = self.tools.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool not found: {name}",
            )
        
        start_time = time.time()
        
        try:
            output = await tool.handler(**arguments)
            duration_ms = (time.time() - start_time) * 1000
            
            return ToolResult(
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def get_summary(self) -> dict[str, Any]:
        """Get summary of registered tools."""
        return {
            "total_tools": len(self.tools),
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": len(tool.parameters),
                }
                for tool in self.tools.values()
            ],
        }


class ToolsPlugin(Plugin):
    """
    Tool-use plugin for function calling.
    
    Provides a registry for tools that agents can use during execution.
    
    Example:
        plugin = ToolsPlugin()
        await registry.load(plugin)
        
        tool_registry = plugin.tool_registry
        
        # Register custom tools
        tool_registry.register(Tool(
            name="calculate",
            description="Perform a calculation",
            handler=calculate_fn,
        ))
        
        # Execute
        result = await tool_registry.execute("calculate", {"expression": "2+2"})
    """
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="loopy-tools",
            version="0.3.0",
            description="Tool-use and function calling for loopy agents",
            author="Dream Pixels Forge",
            capabilities=["tool", "registry"],
            requires=[],
        )
    
    async def setup(self, registry: PluginRegistry) -> None:
        """Initialize the Tools plugin."""
        self.tool_registry = ToolRegistry()
        
        # Register built-in tools
        self._register_builtins()
        
        # Register tool registry as a tool
        registry.register_tool("execute_tool", self._execute_tool)
        registry.register_tool("list_tools", self._list_tools)
        registry.register_tool("get_tool_schema", self._get_tool_schema)
        
        logger.info("Tools plugin initialized")
    
    def _register_builtins(self) -> None:
        """Register built-in tools."""
        # Calculator tool
        self.tool_registry.register(Tool(
            name="calculator",
            description="Perform basic arithmetic calculations",
            handler=self._calculator,
            parameters=[
                ToolParameter(
                    name="expression",
                    type="string",
                    description="Math expression (e.g., '2 + 2')",
                ),
            ],
        ))
        
        # JSON parser tool
        self.tool_registry.register(Tool(
            name="parse_json",
            description="Parse a JSON string",
            handler=self._parse_json,
            parameters=[
                ToolParameter(name="text", type="string", description="JSON string to parse"),
            ],
        ))
    
    async def _calculator(self, expression: str) -> Any:
        """Calculate a math expression safely."""
        # Simple safe eval for basic math
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            raise ValueError("Invalid characters in expression")
        
        result = eval(expression)  # noqa: S307
        return {"result": result, "expression": expression}
    
    async def _parse_json(self, text: str) -> Any:
        """Parse JSON text."""
        return json.loads(text)
    
    async def _execute_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a tool."""
        result = await self.tool_registry.execute(name, arguments or {})
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }
    
    async def _list_tools(self) -> list[dict[str, Any]]:
        """List all available tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": len(tool.parameters),
            }
            for tool in self.tool_registry.list_all()
        ]
    
    async def _get_tool_schema(self, name: str) -> dict[str, Any] | None:
        """Get a tool's schema."""
        tool = self.tool_registry.get(name)
        if tool:
            return tool.to_schema()
        return None
