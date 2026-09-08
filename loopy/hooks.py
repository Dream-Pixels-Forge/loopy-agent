"""
Hooks — Lifecycle hooks for deterministic agent control.

Provides a typed hook system with lifecycle stages, priority-ordered
execution, and abort semantics so callers can inject behaviour at
every step of the agent loop without modifying the core engine.

Design inspired by claude-agent-sdk's PreToolUse / PostToolUse hooks.
Docs: https://loopy.dev/docs/hooks
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger("loopy.hooks")

T = TypeVar("T")


class HookType(str, Enum):
    """Lifecycle stage at which a hook fires."""

    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    PRE_LLM_CALL = "pre_llm_call"
    POST_LLM_CALL = "post_llm_call"
    PRE_AGENT_STEP = "pre_agent_step"
    POST_AGENT_STEP = "post_agent_step"
    ON_ERROR = "on_error"
    PRE_INPUT_VALIDATE = "pre_input_validate"
    POST_OUTPUT_PROCESS = "post_output_process"


@dataclass
class HookContext:
    """Mutable context passed through the hook pipeline.

    Fields are intentionally mutable so hooks can inspect and
    transform shared state (e.g. rewrite tool arguments before
    execution, capture output after execution).
    """

    hook_type: HookType
    operation: str
    input_data: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    aborted: bool = False
    abort_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def abort(self, reason: str) -> None:
        """Signal that the pipeline should stop."""
        self.aborted = True
        self.abort_reason = reason

    def copy(self) -> HookContext:
        """Return a shallow copy (same input_data/output refs)."""
        return HookContext(
            hook_type=self.hook_type,
            operation=self.operation,
            input_data=dict(self.input_data),
            output=self.output,
            aborted=self.aborted,
            abort_reason=self.abort_reason,
            metadata=dict(self.metadata),
        )

    def update_input(self, **kwargs: Any) -> None:
        """Mutate input_data in-place."""
        self.input_data.update(kwargs)

    def set_output(self, value: Any) -> None:
        """Mutate output in-place."""
        self.output = value


@dataclass
class HookResult:
    """Return value from a single hook invocation."""

    aborted: bool = False
    abort_reason: str = ""
    modified: bool = False
    warning: str | None = None


@dataclass
class Hook:
    """A single hook registration.

    Args:
        hook_type: Which lifecycle stage this hook fires at.
        callback: Sync or async callable ``(ctx: HookContext) -> HookResult | None``.
        priority: Lower values fire first (default 0).
        name: Human-readable name for diagnostics.
    """

    hook_type: HookType
    callback: Callable[[HookContext], Any]
    priority: int = 0
    name: str = ""

    @property
    def display_name(self) -> str:
        return self.name or self.callback.__qualname__


class HookRegistry:
    """Registry and executor for lifecycle hooks.

    Hooks are ordered by priority (ascending) within each type.
    Execution is short-circuit: if any hook aborts, subsequent
    hooks of the same type are skipped.

    Example:
        >>> reg = HookRegistry()
        >>> reg.add(Hook(HookType.PRE_TOOL_USE, my_pre_hook, priority=10))
        >>> result = await reg.fire(
        ...     HookType.PRE_TOOL_USE, operation="edit", input_data={"path": "x"}
        ... )
    """

    def __init__(self) -> None:
        self._hooks: dict[HookType, list[Hook]] = {ht: [] for ht in HookType}

    def add(self, hook: Hook) -> None:
        """Register a hook. Ordered by priority within its type."""
        bucket = self._hooks[hook.hook_type]
        bucket.append(hook)
        bucket.sort(key=lambda h: h.priority)
        logger.debug(
            "Registered hook %r (%s) priority=%s",
            hook.display_name,
            hook.hook_type.value,
            hook.priority,
        )

    def remove(self, hook_type: HookType, name: str) -> bool:
        """Remove a hook by (type, name). Returns True if found."""
        bucket = self._hooks[hook_type]
        for i, h in enumerate(bucket):
            if h.display_name == name:
                del bucket[i]
                return True
        return False

    def clear(self, hook_type: HookType | None = None) -> None:
        """Clear hooks. If *hook_type* is given, clear only that type."""
        if hook_type is not None:
            self._hooks[hook_type].clear()
        else:
            for bucket in self._hooks.values():
                bucket.clear()

    def list_hooks(self, hook_type: HookType | None = None) -> list[Hook]:
        """Return registered hooks, optionally filtered by type."""
        if hook_type is not None:
            return list(self._hooks[hook_type])
        result: list[Hook] = []
        for bucket in self._hooks.values():
            result.extend(bucket)
        return result

    async def fire(
        self,
        hook_type: HookType,
        *,
        operation: str,
        input_data: dict[str, Any] | None = None,
    ) -> HookResult:
        """Execute all hooks of the given type in priority order.

        Returns a combined :class:`HookResult`. Aborts on first
        hook that signals abort; subsequent hooks are skipped.
        """
        ctx = HookContext(
            hook_type=hook_type,
            operation=operation,
            input_data=input_data or {},
        )
        results: list[HookResult] = []
        for hook in self._hooks[hook_type]:
            try:
                raw = hook.callback(ctx)
                if asyncio.iscoroutine(raw):
                    raw = await raw
                if raw is not None and isinstance(raw, HookResult):
                    results.append(raw)
                    if raw.aborted:
                        ctx.abort(raw.abort_reason)
                        logger.info(
                            "Hook %r aborted %s (%s): %s",
                            hook.display_name,
                            hook_type.value,
                            operation,
                            raw.abort_reason,
                        )
                        break
            except Exception as e:
                logger.error("Hook %r raised %s: %s", hook.display_name, type(e).__name__, e)
                results.append(HookResult(aborted=True, abort_reason=f"hook_error:{e}"))
                ctx.abort(f"hook_error:{e}")
                break

        return HookResult(
            aborted=ctx.aborted,
            abort_reason=ctx.abort_reason,
            modified=any(r.modified for r in results),
            warning=next((r.warning for r in results if r.warning), None),
        )

    def fire_sync(
        self,
        hook_type: HookType,
        *,
        operation: str,
        input_data: dict[str, Any] | None = None,
    ) -> HookResult:
        """Synchronous variant of :meth:`fire`."""
        ctx = HookContext(
            hook_type=hook_type,
            operation=operation,
            input_data=input_data or {},
        )
        results: list[HookResult] = []
        for hook in self._hooks[hook_type]:
            try:
                raw = hook.callback(ctx)
                if raw is not None and isinstance(raw, HookResult):
                    results.append(raw)
                    if raw.aborted:
                        ctx.abort(raw.abort_reason)
                        break
            except Exception as e:
                logger.error("Hook %r raised %s: %s", hook.display_name, type(e).__name__, e)
                results.append(HookResult(aborted=True, abort_reason=f"hook_error:{e}"))
                ctx.abort(f"hook_error:{e}")
                break

        return HookResult(
            aborted=ctx.aborted,
            abort_reason=ctx.abort_reason,
            modified=any(r.modified for r in results),
            warning=next((r.warning for r in results if r.warning), None),
        )
