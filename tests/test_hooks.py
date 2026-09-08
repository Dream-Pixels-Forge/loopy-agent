"""Tests for loopy.hooks — lifecycle hook system."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from loopy.hooks import (
    Hook,
    HookContext,
    HookRegistry,
    HookResult,
    HookType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sync_hook(
    result: HookResult | None = None,
    abort: bool = False,
    reason: str = "",
    fn_body: callable | None = None,
):
    """Factory: returns a sync callback suitable for Hook(callback=...)."""

    def fn(ctx: HookContext) -> HookResult:
        if abort:
            return HookResult(aborted=True, abort_reason=reason)
        if fn_body is not None:
            return fn_body(ctx)
        return result or HookResult()

    return fn


# ---------------------------------------------------------------------------
# HookContext
# ---------------------------------------------------------------------------


class TestHookContext:
    def test_defaults(self):
        ctx = HookContext(hook_type=HookType.PRE_TOOL_USE, operation="edit")
        assert ctx.input_data == {}
        assert ctx.output is None
        assert not ctx.aborted
        assert ctx.abort_reason == ""
        assert ctx.metadata == {}

    def test_abort_sets_flags(self):
        ctx = HookContext(hook_type=HookType.POST_LLM_CALL, operation="chat")
        ctx.abort("user rejected")
        assert ctx.aborted
        assert ctx.abort_reason == "user rejected"

    def test_update_input_merges(self):
        ctx = HookContext(hook_type=HookType.PRE_TOOL_USE, operation="x", input_data={"a": 1})
        ctx.update_input(b=2, a=99)
        assert ctx.input_data == {"a": 99, "b": 2}

    def test_set_output(self):
        ctx = HookContext(hook_type=HookType.POST_OUTPUT_PROCESS, operation="y")
        ctx.set_output("new value")
        assert ctx.output == "new value"

    def test_copy_shallow(self):
        ctx = HookContext(
            hook_type=HookType.PRE_AGENT_STEP,
            operation="z",
            input_data={"k": "v"},
            metadata={"seq": 1},
        )
        copy = ctx.copy()
        assert copy.hook_type == ctx.hook_type
        assert copy.operation == ctx.operation
        assert copy.input_data == ctx.input_data
        assert copy.metadata == ctx.metadata
        assert copy is not ctx
        # Mutating copy doesn't affect original
        copy.input_data["k"] = "changed"
        assert ctx.input_data["k"] == "v"


# ---------------------------------------------------------------------------
# HookRegistry — registration
# ---------------------------------------------------------------------------


class TestHookRegistryRegistration:
    def test_add_and_list(self):
        reg = HookRegistry()
        h = Hook(HookType.PRE_TOOL_USE, _sync_hook(), priority=5, name="first")
        reg.add(h)
        assert len(reg.list_hooks(HookType.PRE_TOOL_USE)) == 1
        assert reg.list_hooks(HookType.PRE_TOOL_USE)[0] is h

    def test_empty_registry_lists_nothing(self):
        reg = HookRegistry()
        assert reg.list_hooks() == []
        assert reg.list_hooks(HookType.POST_LLM_CALL) == []

    def test_multiple_types_independent(self):
        reg = HookRegistry()
        reg.add(Hook(HookType.PRE_TOOL_USE, _sync_hook(), name="tool"))
        reg.add(Hook(HookType.POST_LLM_CALL, _sync_hook(), name="llm"))
        assert len(reg.list_hooks(HookType.PRE_TOOL_USE)) == 1
        assert len(reg.list_hooks(HookType.POST_LLM_CALL)) == 1
        assert len(reg.list_hooks(HookType.PRE_INPUT_VALIDATE)) == 0

    def test_remove_returns_true_when_found(self):
        reg = HookRegistry()
        h = Hook(HookType.ON_ERROR, _sync_hook(), name="err")
        reg.add(h)
        assert reg.remove(HookType.ON_ERROR, "err") is True
        assert reg.list_hooks(HookType.ON_ERROR) == []

    def test_remove_returns_false_when_missing(self):
        reg = HookRegistry()
        assert reg.remove(HookType.ON_ERROR, "nope") is False

    def test_clear_by_type(self):
        reg = HookRegistry()
        reg.add(Hook(HookType.PRE_TOOL_USE, _sync_hook(), name="t1"))
        reg.add(Hook(HookType.PRE_TOOL_USE, _sync_hook(), name="t2"))
        reg.add(Hook(HookType.POST_LLM_CALL, _sync_hook(), name="l1"))
        reg.clear(HookType.PRE_TOOL_USE)
        assert reg.list_hooks(HookType.PRE_TOOL_USE) == []
        assert len(reg.list_hooks(HookType.POST_LLM_CALL)) == 1

    def test_clear_all(self):
        reg = HookRegistry()
        for ht in HookType:
            reg.add(Hook(ht, _sync_hook(), name=ht.value))
        reg.clear()
        assert reg.list_hooks() == []


# ---------------------------------------------------------------------------
# HookRegistry — priority ordering
# ---------------------------------------------------------------------------


class TestHookRegistryPriority:
    def test_lower_priority_fires_first(self):
        order: list[str] = []
        reg = HookRegistry()
        entries = [("low", 10), ("high", 1), ("mid", 5)]
        for label, prio in entries:

            def make_fn(label: str) -> callable:
                def fn(_ctx: HookContext) -> HookResult:
                    order.append(label)
                    return HookResult()

                return fn

            reg.add(Hook(HookType.PRE_TOOL_USE, make_fn(label), priority=prio, name=label))
        asyncio.run(reg.fire(HookType.PRE_TOOL_USE, operation="x"))
        assert order == ["high", "mid", "low"]


# ---------------------------------------------------------------------------
# HookRegistry — fire() async semantics
# ---------------------------------------------------------------------------


class TestHookRegistryFire:
    def test_fire_runs_all_hooks_in_order(self):
        reg = HookRegistry()
        for name in ("a", "b", "c"):
            reg.add(Hook(HookType.POST_AGENT_STEP, _sync_hook(), name=name, priority=0))
        result = asyncio.run(reg.fire(HookType.POST_AGENT_STEP, operation="step1"))
        assert not result.aborted
        hooks = reg.list_hooks(HookType.POST_AGENT_STEP)
        assert len(hooks) == 3

    def test_fire_empty_registry_returns_non_aborted(self):
        reg = HookRegistry()
        result = asyncio.run(reg.fire(HookType.PRE_INPUT_VALIDATE, operation="v"))
        assert not result.aborted
        assert result.abort_reason == ""
        assert not result.modified

    def test_fire_single_hook_modifies_result(self):
        reg = HookRegistry()
        reg.add(
            Hook(
                HookType.PRE_LLM_CALL,
                _sync_hook(result=HookResult(modified=True, warning="slow model")),
                name="warn",
            )
        )
        result = asyncio.run(
            reg.fire(HookType.PRE_LLM_CALL, operation="chat", input_data={"model": "old"})
        )
        assert result.modified
        assert result.warning == "slow model"
        assert not result.aborted

    def test_fire_context_injected_correctly(self):
        captured: list[HookContext] = []

        def fn(ctx: HookContext) -> HookResult:
            captured.append(ctx)
            return HookResult()

        reg = HookRegistry()
        reg.add(Hook(HookType.PRE_AGENT_STEP, fn, name="capture"))
        asyncio.run(reg.fire(HookType.PRE_AGENT_STEP, operation="plan", input_data={"q": "hi"}))
        assert len(captured) == 1
        assert captured[0].hook_type == HookType.PRE_AGENT_STEP
        assert captured[0].operation == "plan"
        assert captured[0].input_data == {"q": "hi"}

    def test_fire_passes_input_data_through(self):
        reg = HookRegistry()
        reg.add(
            Hook(
                HookType.PRE_TOOL_USE,
                lambda ctx: (
                    HookResult(modified=True) if ctx.input_data.get("rewrite") else HookResult()
                ),
                name="rw",
            )
        )
        result = asyncio.run(
            reg.fire(HookType.PRE_TOOL_USE, operation="edit", input_data={"rewrite": True})
        )
        assert result.modified


# ---------------------------------------------------------------------------
# HookRegistry — abort semantics
# ---------------------------------------------------------------------------


class TestHookRegistryAbort:
    def test_abort_stops_subsequent_hooks(self):
        fired: list[str] = []

        def make_fn(label: str, do_abort: bool, abort_r: str) -> callable:
            def fn(_ctx: HookContext) -> HookResult:
                fired.append(label)
                if do_abort:
                    return HookResult(aborted=True, abort_reason=abort_r)
                return HookResult()

            return fn

        reg = HookRegistry()
        reg.add(
            Hook(
                HookType.POST_OUTPUT_PROCESS, make_fn("first", False, ""), name="first", priority=0
            )
        )
        reg.add(
            Hook(
                HookType.POST_OUTPUT_PROCESS,
                make_fn("second", True, "denied"),
                name="second",
                priority=0,
            )
        )
        result = asyncio.run(reg.fire(HookType.POST_OUTPUT_PROCESS, operation="out"))
        assert result.aborted
        assert result.abort_reason == "denied"
        assert "first" in fired
        assert "second" in fired

    def test_abort_reason_propagates(self):
        reg = HookRegistry()
        reg.add(
            Hook(
                HookType.PRE_INPUT_VALIDATE,
                _sync_hook(abort=True, reason="pii detected"),
                name="guard",
            )
        )
        result = asyncio.run(reg.fire(HookType.PRE_INPUT_VALIDATE, operation="in"))
        assert result.aborted
        assert result.abort_reason == "pii detected"

    def test_abort_prevents_later_hooks_from_running(self):
        ran_after_abort: list[str] = []
        reg = HookRegistry()
        reg.add(
            Hook(HookType.PRE_AGENT_STEP, _sync_hook(abort=True, reason="stop"), name="stopper")
        )

        def late_fn(_ctx: HookContext) -> HookResult:
            ran_after_abort.append("late")
            return HookResult()

        reg.add(Hook(HookType.PRE_AGENT_STEP, late_fn, name="late"))
        asyncio.run(reg.fire(HookType.PRE_AGENT_STEP, operation="step"))
        assert ran_after_abort == [], "hook after abort should not run"


# ---------------------------------------------------------------------------
# HookRegistry — exception handling
# ---------------------------------------------------------------------------


class TestHookRegistryExceptions:
    def test_raising_hook_aborts_and_logs(self, caplog):
        reg = HookRegistry()
        reg.add(
            Hook(
                HookType.ON_ERROR,
                _sync_hook(fn_body=lambda _ctx: (_ for _ in ()).throw(RuntimeError("boom"))),
                name="bad",
            )
        )
        with caplog.at_level(logging.ERROR):
            result = asyncio.run(reg.fire(HookType.ON_ERROR, operation="err"))
        assert result.aborted
        assert "boom" in result.abort_reason or "hook_error" in result.abort_reason

    def test_exception_after_successful_hook(self):
        ran: list[str] = []
        reg = HookRegistry()
        reg.add(
            Hook(HookType.PRE_TOOL_USE, lambda _c: (ran.append("ok"), HookResult())[1], name="ok")
        )
        reg.add(
            Hook(
                HookType.PRE_TOOL_USE,
                _sync_hook(fn_body=lambda _ctx: (_ for _ in ()).throw(ValueError("bad"))),
                name="bad",
            )
        )
        result = asyncio.run(reg.fire(HookType.PRE_TOOL_USE, operation="edit"))
        assert "ok" in ran
        assert result.aborted


# ---------------------------------------------------------------------------
# HookRegistry — fire_sync
# ---------------------------------------------------------------------------


class TestHookRegistryFireSync:
    def test_sync_fire_runs_hooks(self):
        reg = HookRegistry()
        reg.add(Hook(HookType.PRE_LLM_CALL, _sync_hook(), name="s"))
        result = reg.fire_sync(HookType.PRE_LLM_CALL, operation="chat")
        assert not result.aborted

    def test_sync_fire_with_abort(self):
        reg = HookRegistry()
        reg.add(
            Hook(
                HookType.POST_AGENT_STEP,
                _sync_hook(abort=True, reason="nope"),
                name="x",
            )
        )
        result = reg.fire_sync(HookType.POST_AGENT_STEP, operation="s")
        assert result.aborted
        assert result.abort_reason == "nope"

    def test_sync_fire_empty_registry(self):
        reg = HookRegistry()
        result = reg.fire_sync(HookType.ON_ERROR, operation="err")
        assert not result.aborted
        assert not result.modified

    def test_sync_fire_preserves_input_data(self):
        captured: list[dict] = []
        reg = HookRegistry()

        def reader(ctx: HookContext) -> HookResult:
            captured.append(dict(ctx.input_data))
            return HookResult()

        reg.add(Hook(HookType.PRE_INPUT_VALIDATE, reader, name="read"))
        reg.fire_sync(HookType.PRE_INPUT_VALIDATE, operation="v", input_data={"key": "val"})
        assert captured == [{"key": "val"}]

    def test_sync_fire_handles_raising_hook(self, caplog):
        reg = HookRegistry()
        reg.add(
            Hook(
                HookType.ON_ERROR,
                _sync_hook(fn_body=lambda _ctx: (_ for _ in ()).throw(RuntimeError("boom"))),
                name="bad",
            )
        )
        with caplog.at_level(logging.ERROR):
            result = reg.fire_sync(HookType.ON_ERROR, operation="err")
        assert result.aborted
        assert "boom" in result.abort_reason or "hook_error" in result.abort_reason


# ---------------------------------------------------------------------------
# HookRegistry — async hooks
# ---------------------------------------------------------------------------


class TestHookRegistryAsyncHooks:
    @pytest.mark.asyncio
    async def test_async_hook_runs(self):
        called = False

        async def fn(_ctx: HookContext) -> HookResult:
            nonlocal called
            called = True
            return HookResult(modified=True)

        reg = HookRegistry()
        reg.add(Hook(HookType.PRE_LLM_CALL, fn, name="async_fn"))
        result = await reg.fire(HookType.PRE_LLM_CALL, operation="chat")
        assert called
        assert result.modified

    @pytest.mark.asyncio
    async def test_async_hook_abort(self):
        async def fn(_ctx: HookContext) -> HookResult:
            return HookResult(aborted=True, abort_reason="async deny")

        reg = HookRegistry()
        reg.add(Hook(HookType.PRE_INPUT_VALIDATE, fn, name="deny"))
        result = await reg.fire(HookType.PRE_INPUT_VALIDATE, operation="in")
        assert result.aborted
        assert result.abort_reason == "async deny"


# ---------------------------------------------------------------------------
# HookRegistry — mixed sync/async
# ---------------------------------------------------------------------------


class TestHookRegistryMixed:
    @pytest.mark.asyncio
    async def test_mixed_sync_async_hooks_run_in_order(self):
        order: list[str] = []
        reg = HookRegistry()
        reg.add(
            Hook(
                HookType.PRE_AGENT_STEP, lambda c: (order.append("sync"), HookResult())[1], name="s"
            )
        )
        reg.add(
            Hook(
                HookType.PRE_AGENT_STEP,
                lambda c: (order.append("async"), HookResult())[1],
                name="a",
            )
        )

        async def async_fn(_ctx: HookContext) -> HookResult:
            order.append("async_actual")
            return HookResult()

        reg.add(Hook(HookType.PRE_AGENT_STEP, async_fn, name="a2"))
        await reg.fire(HookType.PRE_AGENT_STEP, operation="x")
        assert order == ["sync", "async", "async_actual"]


# ---------------------------------------------------------------------------
# HookRegistry — context mutation propagation
# ---------------------------------------------------------------------------


class TestHookContextMutation:
    @pytest.mark.asyncio
    async def test_input_mutations_visible_to_subsequent_hooks(self):
        values: list[dict] = []
        reg = HookRegistry()

        def mutator(ctx: HookContext) -> HookResult:
            ctx.update_input(expanded=True)
            return HookResult(modified=True)

        def reader(ctx: HookContext) -> HookResult:
            values.append(dict(ctx.input_data))
            return HookResult()

        reg.add(Hook(HookType.PRE_INPUT_VALIDATE, mutator, name="mut"))
        reg.add(Hook(HookType.PRE_INPUT_VALIDATE, reader, name="read"))
        await reg.fire(HookType.PRE_INPUT_VALIDATE, operation="v", input_data={"q": "hello"})
        assert values[-1]["q"] == "hello"
        assert values[-1]["expanded"] is True

    @pytest.mark.asyncio
    async def test_output_propagates(self):
        captured: list[Any] = []

        def writer(ctx: HookContext) -> HookResult:
            ctx.set_output("processed")
            return HookResult()

        def reader(ctx: HookContext) -> HookResult:
            captured.append(ctx.output)
            return HookResult()

        reg = HookRegistry()
        reg.add(Hook(HookType.POST_OUTPUT_PROCESS, writer, name="w"))
        reg.add(Hook(HookType.POST_OUTPUT_PROCESS, reader, name="r"))
        await reg.fire(HookType.POST_OUTPUT_PROCESS, operation="o")
        assert captured == ["processed"]


# ---------------------------------------------------------------------------
# HookRegistry — name uniqueness + re-add
# ---------------------------------------------------------------------------


class TestHookRegistryReAdd:
    def test_re_add_same_name_different_hook(self):
        """Adding two hooks with the same name is allowed; remove removes the first match."""
        reg = HookRegistry()
        h1 = Hook(HookType.PRE_TOOL_USE, _sync_hook(), name="dup")
        h2 = Hook(HookType.PRE_TOOL_USE, _sync_hook(), name="dup")
        reg.add(h1)
        reg.add(h2)
        assert len(reg.list_hooks(HookType.PRE_TOOL_USE)) == 2
        reg.remove(HookType.PRE_TOOL_USE, "dup")
        # Should remove first match only
        assert len(reg.list_hooks(HookType.PRE_TOOL_USE)) == 1


# ---------------------------------------------------------------------------
# HookRegistry — all HookTypes accounted for
# ---------------------------------------------------------------------------


class TestHookTypes:
    def test_all_types_exist(self):
        assert hasattr(HookType, "PRE_TOOL_USE")
        assert hasattr(HookType, "POST_TOOL_USE")
        assert hasattr(HookType, "PRE_LLM_CALL")
        assert hasattr(HookType, "POST_LLM_CALL")
        assert hasattr(HookType, "PRE_AGENT_STEP")
        assert hasattr(HookType, "POST_AGENT_STEP")
        assert hasattr(HookType, "ON_ERROR")
        assert hasattr(HookType, "PRE_INPUT_VALIDATE")
        assert hasattr(HookType, "POST_OUTPUT_PROCESS")

    def test_all_types_can_be_registered(self):
        reg = HookRegistry()
        for ht in HookType:
            reg.add(Hook(ht, _sync_hook(), name=ht.value))
        result = asyncio.run(reg.fire(ht, operation="x"))
        assert not result.aborted
