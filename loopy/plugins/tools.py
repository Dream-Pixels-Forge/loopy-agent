"""
Tools Plugin — Tool-use with function calling.

Provides a registry for tools that agents can use during execution.
"""

from __future__ import annotations

import ast
import json
import logging
import operator
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loopy.plugins import (
    DENIAL_LOG_MAX,
    Plugin,
    PluginInfo,
    PluginRegistry,
    redact_arguments,
)

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
    """A tool that agents can use.

    Security-relevant fields: deny-by-default, least privilege, and
    human-in-the-loop enforcement live on the tool. ``scope``, ``enabled``,
    ``requires_approval`` and ``allowed_values`` are checked by
    :meth:`ToolRegistry.execute` before a handler ever runs.
    """

    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    parameters: list[ToolParameter] = field(default_factory=list)

    # --- capability scoping (security) ---
    scope: str = "side_effecting"  # "read_only" | "side_effecting"
    enabled: bool = True  # deny-by-default — False = never executes
    requires_approval: bool = False  # HITL gate, enforced in execute()
    # Enumerate legal values per parameter (allow-list for free-text args)
    allowed_values: dict[str, set[str]] | None = None

    def is_read_only(self) -> bool:
        """Return True if the tool has no side effects."""
        return self.scope == "read_only"

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

    Enforces the defense-in-depth stack before any handler runs:
    deny-by-default (disabled tools never execute), parameter allow-lists
    (enum constraints), and a human-in-the-loop approval gate for
    consequential tools. Denied calls are recorded for auditing.

    Example:
        async def approver(tool, arguments):
            return tool.scope == "read_only"  # approve only read-only tools

        registry = ToolRegistry(approver=approver)

        # Register a tool
        registry.register(Tool(
            name="get_weather",
            description="Get weather for a location",
            handler=get_weather_fn,
            parameters=[ToolParameter(name="location", type="string")],
        ))

        # Execute a tool (enforced)
        result = await registry.execute("get_weather", {"location": "Portland"})
    """

    def __init__(
        self,
        approver: Callable[[Tool, dict[str, Any]], Awaitable[bool]] | None = None,
    ):
        """Args:
        approver: Optional async callback ``(tool, arguments) -> bool``
            that decides whether a ``requires_approval`` tool may run.
            If None, any tool with ``requires_approval=True`` is denied.
        """
        self.tools: dict[str, Tool] = {}
        self.approver = approver
        self._denials: deque = deque(maxlen=DENIAL_LOG_MAX)

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self.tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self.tools.get(name)

    def list_all(self) -> list[Tool]:
        """List all registered tools."""
        return list(self.tools.values())

    def list_schemas(self) -> list[dict[str, Any]]:
        """List all tool schemas (for OpenAI function calling)."""
        return [tool.to_schema() for tool in self.tools.values()]

    def denials(self) -> list[dict[str, Any]]:
        """Audit trail of every denied/blocked tool call.

        Bounded to ``DENIAL_LOG_MAX`` entries (oldest dropped first);
        secret-looking argument values are redacted.
        """
        return list(self._denials)

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """
        Execute a tool by name, enforcing the capability gates.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            ToolResult with output or error
        """
        tool = self.tools.get(name)
        if not tool:
            self._denials.append({"tool": name, "reason": "not_found"})
            return ToolResult(
                success=False,
                error=f"Tool not found: {name}",
            )

        # Deny-by-default: a disabled tool never executes.
        if not tool.enabled:
            self._denials.append({"tool": name, "reason": "disabled"})
            return ToolResult(
                success=False,
                error=f"Tool '{name}' is disabled",
            )

        # Parameter allow-list (enum constraints).
        if tool.allowed_values:
            for param, allowed in tool.allowed_values.items():
                value = arguments.get(param)
                if value is not None and value not in allowed:
                    self._denials.append(
                        {"tool": name, "reason": f"parameter '{param}' out of range"}
                    )
                    return ToolResult(
                        success=False,
                        error=f"Parameter '{param}' outside allowed values",
                    )

        # Human-in-the-loop gate for consequential tools.
        if tool.requires_approval:
            if self.approver is None:
                self._denials.append({"tool": name, "reason": "approval_required_no_approver"})
                return ToolResult(
                    success=False,
                    error=f"Tool '{name}' requires approval and no approver is configured",
                )
            approved = await self.approver(tool, arguments)
            if not approved:
                self._denials.append(
                    {
                        "tool": name,
                        "reason": "approval_denied",
                        "arguments": redact_arguments(arguments),
                    }
                )
                return ToolResult(
                    success=False,
                    error=f"Tool '{name}' was not approved",
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


_ALLOWED_BINOPS: dict[type[ast.AST], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}

_ALLOWED_UNARY: dict[type[ast.AST], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_math(expression: str) -> float:
    """Evaluate a numeric expression via an AST whitelist (no ``eval``).

    Only numeric constants, binary arithmetic and unary ``+``/``-`` are
    permitted. Names, calls, attribute access, comprehensions, and string
    literals raise ``ValueError`` — arbitrary code cannot run.

    Raises:
        ValueError: On unsupported syntax.
        ZeroDivisionError: On division by zero (propagates to the caller).
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"Unsupported expression: {exc}") from exc

    def _walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            return _ALLOWED_BINOPS[type(node.op)](_walk(node.left), _walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
            return _ALLOWED_UNARY[type(node.op)](_walk(node.operand))
        raise ValueError(f"Unsupported expression element: {type(node).__name__}")

    return _walk(tree)


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

        # Register read-only registry introspection tools (agent-visible).
        # NOTE: a universal 'execute_tool' meta-tool is deliberately NOT
        # registered — it would grant the model arbitrary execution over the
        # whole registry (excessive agency). Executing a tool is the caller's
        # job via ToolRegistry.execute(), which enforces capability gates.
        registry.register_tool("list_tools", self._list_tools, scope="read_only")
        registry.register_tool("get_tool_schema", self._get_tool_schema, scope="read_only")

        logger.info("Tools plugin initialized")

    def _register_builtins(self) -> None:
        """Register built-in tools (read-only, no approval needed)."""
        # Calculator tool
        self.tool_registry.register(
            Tool(
                name="calculator",
                description="Perform basic arithmetic calculations",
                handler=self._calculator,
                scope="read_only",
                parameters=[
                    ToolParameter(
                        name="expression",
                        type="string",
                        description="Math expression (e.g., '2 + 2')",
                    ),
                ],
            )
        )

        # JSON parser tool
        self.tool_registry.register(
            Tool(
                name="parse_json",
                description="Parse a JSON string",
                handler=self._parse_json,
                scope="read_only",
                parameters=[
                    ToolParameter(name="text", type="string", description="JSON string to parse"),
                ],
            )
        )

    async def _calculator(self, expression: str) -> Any:
        """Calculate a math expression using an AST whitelist (no ``eval``).

        Only numeric literals, ``+ - * / % ** //`` and unary ``+/-`` are
        accepted. Attribute access, calls, names, and comprehensions are
        rejected outright, so arbitrary code cannot run.

        Raises:
            ValueError: If the expression uses unsupported syntax.
        """
        return {"result": _eval_math(expression), "expression": expression}

    async def _parse_json(self, text: str) -> Any:
        """Parse JSON text."""
        return json.loads(text)

    async def _execute_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a tool via the registry (operator use only).

        Not registered as an agent-visible tool — intended for programmatic
        / operator callers. Capability gates are enforced by
        :meth:`ToolRegistry.execute`.
        """
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
