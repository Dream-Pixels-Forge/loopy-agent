"""Tests for loopy.tools — in-process tool execution engine."""

from __future__ import annotations

import asyncio
import logging

import pytest

from loopy.tools import (
    ToolContext,
    ToolDef,
    ToolExecutor,
    ToolParamSchema,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sync_handler(ctx: ToolContext, x: int = 0) -> str:
    return f"sync:{x}"


async def _async_handler(ctx: ToolContext, x: int = 0) -> str:
    return f"async:{x}"


def _handler_raises(ctx: ToolContext, **kwargs) -> str:  # type: ignore[return]
    raise RuntimeError("boom")


def _positional_handler(x: int) -> str:  # no ctx param
    return f"pos:{x}"


# ---------------------------------------------------------------------------
# ToolDef
# ---------------------------------------------------------------------------


class TestToolDef:
    def test_read_only_property(self):
        t = ToolDef("r", "read", lambda c: "ok", scope="read_only")
        assert t.is_read_only is True
        t2 = ToolDef("s", "side", lambda c: "ok", scope="side_effecting")
        assert t2.is_read_only is False

    def test_to_schema_minimal(self):
        t = ToolDef("t", "desc", lambda c: "ok")
        schema = t.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "t"
        assert schema["function"]["description"] == "desc"
        assert schema["function"]["parameters"]["type"] == "object"

    def test_to_schema_with_parameters(self):
        t = ToolDef(
            "calc",
            "compute",
            _async_handler,
            parameters=[
                ToolParamSchema(name="a", type="number", required=True),
                ToolParamSchema(name="b", type="number", required=False, default=0),
            ],
        )
        schema = t.to_schema()["function"]["parameters"]
        assert "a" in schema["properties"]
        assert "b" in schema["properties"]
        assert "a" in schema["required"]
        assert "b" not in schema["required"]


# ---------------------------------------------------------------------------
# ToolExecutor — registration
# ---------------------------------------------------------------------------


class TestToolExecutorRegistration:
    def test_register_and_get(self):
        exec_ = ToolExecutor()
        tool = ToolDef("hello", "greet", _async_handler)
        exec_.register(tool)
        assert exec_.get("hello") is tool
        assert len(exec_.list_tools()) == 1

    def test_unregister(self):
        exec_ = ToolExecutor()
        tool = ToolDef("x", "x", _async_handler)
        exec_.register(tool)
        assert exec_.unregister("x") is True
        assert exec_.get("x") is None
        assert exec_.unregister("missing") is False

    def test_list_schemas(self):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("a", "a", _async_handler))
        exec_.register(ToolDef("b", "b", _async_handler))
        schemas = exec_.list_schemas()
        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert names == {"a", "b"}

    def test_re_register_overwrites(self):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("t", "v1", _async_handler))
        exec_.register(ToolDef("t", "v2", _async_handler))
        assert exec_.get("t").description == "v2"


# ---------------------------------------------------------------------------
# ToolExecutor — call() success paths
# ---------------------------------------------------------------------------


class TestToolExecutorCall:
    @pytest.mark.asyncio
    async def test_async_handler(self):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("fn", "f", _async_handler))
        call = await exec_.call("fn", {"x": 42})
        assert call.success is True
        assert call.output == "async:42"
        assert call.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_sync_handler(self):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("fn", "f", _sync_handler))
        call = await exec_.call("fn", {"x": 7})
        assert call.success is True
        assert call.output == "sync:7"

    @pytest.mark.asyncio
    async def test_handler_without_ctx_param(self):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("fn", "f", _positional_handler))
        call = await exec_.call("fn", {"x": 3})
        assert call.success is True
        assert call.output == "pos:3"

    @pytest.mark.asyncio
    async def test_session_id_propagated(self):
        received: list[str] = []

        async def capture(ctx: ToolContext, **kw) -> str:
            received.append(ctx.session_id)
            return "ok"

        exec_ = ToolExecutor()
        exec_.register(ToolDef("fn", "f", capture))
        await exec_.call("fn", {}, session_id="s1")
        assert received == ["s1"]

    def test_default_max_calls_bound(self):
        exec_ = ToolExecutor()
        assert exec_._max_calls == 10_000


# ---------------------------------------------------------------------------
# ToolExecutor — error / denial paths
# ---------------------------------------------------------------------------


class TestToolExecutorErrors:
    @pytest.mark.asyncio
    async def test_tool_not_found(self):
        exec_ = ToolExecutor()
        call = await exec_.call("missing")
        assert call.success is False
        assert "not found" in call.error or "Tool not found" in call.error

    @pytest.mark.asyncio
    async def test_disabled_tool(self):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("t", "t", _async_handler, enabled=False))
        call = await exec_.call("t")
        assert call.success is False
        assert "disabled" in call.error.lower()

    @pytest.mark.asyncio
    async def test_raising_handler(self, caplog):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("t", "t", _handler_raises))
        with caplog.at_level(logging.WARNING):
            call = await exec_.call("t")
        assert call.success is False
        assert "boom" in call.error

    @pytest.mark.asyncio
    async def test_call_many_order_preserved(self):
        exec_ = ToolExecutor()

        async def make_fn(i: int):
            async def fn(ctx: ToolContext, x: int = 0, _i: int = i) -> str:
                return f"res{_i}:{x}"
            return fn

        for i in range(3):
            exec_.register(ToolDef(f"fn{i}", f"f{i}", await make_fn(i)))

        calls = [("fn0", {"x": 1}), ("fn1", {"x": 2}), ("fn2", {"x": 3})]
        out = await exec_.call_many(calls)
        assert len(out) == 3
        assert [c.output for c in out] == ["res0:1", "res1:2", "res2:3"]


# ---------------------------------------------------------------------------
# ToolExecutor — audit
# ---------------------------------------------------------------------------


class TestToolExecutorAudit:
    @pytest.mark.asyncio
    async def test_recent_calls(self):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("t", "t", _async_handler))
        await exec_.call("t", {"x": 1})
        await exec_.call("t", {"x": 2})
        recent = exec_.recent_calls(1)
        assert len(recent) == 1
        assert recent[0].output == "async:2"

    @pytest.mark.asyncio
    async def test_reset_audit(self):
        exec_ = ToolExecutor()
        exec_.register(ToolDef("t", "t", _async_handler))
        await exec_.call("t")
        exec_.reset_audit()
        assert exec_.recent_calls() == []


# ---------------------------------------------------------------------------
# ToolExecutor — concurrency limit
# ---------------------------------------------------------------------------


class TestToolExecutorConcurrency:
    @pytest.mark.asyncio
    async def test_max_concurrent_bounded(self):
        """Only N handlers run simultaneously when max_concurrent=N."""
        running = 0
        peak = 0
        lock = asyncio.Lock()

        async def bounded(ctx: ToolContext, delay: float = 0.01) -> int:
            nonlocal running, peak
            async with lock:
                running += 1
                peak = max(peak, running)
            await asyncio.sleep(delay)
            async with lock:
                running -= 1
            return peak

        exec_ = ToolExecutor(max_concurrent=2)
        exec_.register(ToolDef("fn", "fn", bounded))
        await exec_.call_many([("fn", {})] * 5)
        assert peak <= 2
