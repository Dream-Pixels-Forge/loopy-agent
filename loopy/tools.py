"""
Tools — In-process tool execution engine.

Provides typed tool definitions, an in-process executor (no
subprocess IPC overhead), handler dispatch, timing, and error
handling so agents can call tools at millisecond latency instead
of spawning worker processes.

Design inspired by claude-agent-sdk's in-process tool model.
Docs: https://loopy.dev/docs/tools
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger("loopy.tools")

T = TypeVar("T")


@dataclass
class ToolParamSchema:
    """Schema for a single tool parameter."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class ToolDef:
    """Declaration of an executable tool.

    Args:
        name: Unique tool identifier.
        description: Human-readable purpose shown to the model.
        handler: Sync or async callable ``(ctx: ToolContext, **kwargs) -> Any``.
        parameters: Declared input schema (empty = accepts anything).
        scope: ``"read_only"`` or ``"side_effecting"`` (used by permission modes).
        enabled: If False the tool is invisible to execution.
        requires_approval: If True the permission gate demands approval.
    """

    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    parameters: list[ToolParamSchema] = field(default_factory=list)
    scope: str = "side_effecting"
    enabled: bool = True
    requires_approval: bool = False

    def to_schema(self) -> dict[str, Any]:
        """Return an OpenAI-compatible function-calling schema."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            prop: dict[str, Any] = {
                "type": p.type,
                "description": p.description,
            }
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
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

    @property
    def is_read_only(self) -> bool:
        return self.scope == "read_only"


@dataclass
class ToolContext:
    """Immutable context passed into every handler invocation."""

    tool_name: str
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """Record of a single tool invocation."""

    tool_name: str
    arguments: dict[str, Any]
    started_at: float
    finished_at: float = 0.0
    success: bool = False
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    def finalize(self, success: bool, output: Any | None = None, error: str | None = None) -> None:
        self.finished_at = time.monotonic()
        self.success = success
        self.output = output
        self.error = error
        self.duration_ms = round((self.finished_at - self.started_at) * 1000, 2)


class ToolExecutor:
    """In-process tool execution engine.

    Handlers run directly in the calling event loop — no subprocess,
    no IPC, no serialization overhead. Calls are tracked so callers
    can audit latency and errors.

    Example:
        >>> async def echo(ctx, text):
        ...     return text
        ...
        >>> exec = ToolExecutor()
        >>> exec.register(ToolDef("echo", "Echo text", echo))
        >>> result = await exec.call("echo", {"text": "hi"})
        >>> result.output == "hi"
    """

    def __init__(self, max_concurrent: int = 10) -> None:
        self._tools: dict[str, ToolDef] = {}
        self._calls: list[ToolCall] = []
        self._max_calls = 10_000
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: ToolDef) -> None:
        """Register a tool. Re-registration overwrites the previous entry."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool %r (scope=%s)", tool.name, tool.scope)

    def unregister(self, name: str) -> bool:
        """Remove a tool by name. Returns True if it existed."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def list_schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        session_id: str = "",
    ) -> ToolCall:
        """Execute a tool in-process and return its call record.

        Args:
            name: Tool name.
            arguments: Keyword arguments forwarded to the handler.
            session_id: Optional session identifier attached to the call.

        Returns:
            A :class:`ToolCall` recording success/failure and latency.
        """
        tool = self._tools.get(name)
        if tool is None:
            call = ToolCall(tool_name=name, arguments=arguments or {}, started_at=time.monotonic())
            call.finalize(False, error=f"Tool not found: {name}")
            self._track(call)
            return call

        if not tool.enabled:
            call = ToolCall(tool_name=name, arguments=arguments or {}, started_at=time.monotonic())
            call.finalize(False, error=f"Tool '{name}' is disabled")
            self._track(call)
            return call

        ctx = ToolContext(tool_name=name, session_id=session_id)
        call = ToolCall(tool_name=name, arguments=arguments or {}, started_at=time.monotonic())

        try:
            async with self._semaphore:
                result = await self._invoke(tool.handler, ctx, arguments or {})
            call.finalize(True, output=result)
        except Exception as exc:
            call.finalize(False, error=str(exc))
            logger.warning("Tool %r raised %s: %s", name, type(exc).__name__, exc)

        self._track(call)
        return call

    async def call_many(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        *,
        session_id: str = "",
    ) -> list[ToolCall]:
        """Execute multiple tool calls concurrently (bounded by *max_concurrent*).

        Returns results in the same order as the input list.
        """
        tasks = [self.call(name, args, session_id=session_id) for name, args in calls]
        return await asyncio.gather(*tasks, return_exceptions=False)

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def recent_calls(self, n: int = 50) -> list[ToolCall]:
        """Return the last *n* recorded calls."""
        return self._calls[-n:]

    def reset_audit(self) -> None:
        """Clear the call audit log."""
        self._calls.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _invoke(
        self, handler: Callable[..., Awaitable[Any]], ctx: ToolContext, kwargs: dict[str, Any]
    ) -> Any:
        """Call the handler, injecting *ctx* as the first positional arg if the
        signature expects it. Handles both sync and async handlers."""
        sig = inspect.signature(handler)
        params = list(sig.parameters.keys())
        bound_kwargs = {"ctx": ctx, **kwargs} if params and params[0] == "ctx" else kwargs

        result = handler(**bound_kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _track(self, call: ToolCall) -> None:
        if len(self._calls) >= self._max_calls:
            self._calls.pop(0)
        self._calls.append(call)
        logger.debug(
            "Tool %r %s in %.1fms",
            call.tool_name,
            "ok" if call.success else f"FAIL: {call.error}",
            call.duration_ms,
        )
