"""Observability coverage tests — OTLP export, TraceExporter, MetricsCollector."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loopy.observe import (
    MetricsCollector,
    Span,
    SpanStatus,
    TraceExporter,
    Tracer,
)

# ── Span ─────────────────────────────────────────────────────


class TestSpan:
    def test_duration_ms(self):
        span = Span(
            name="test",
            trace_id="t1",
            span_id="s1",
            parent_id=None,
            start_time=100.0,
            end_time=100.5,
            status=SpanStatus.OK,
        )
        assert span.duration_ms == 500.0

    def test_duration_ms_none_when_open(self):
        span = Span(
            name="test",
            trace_id="t1",
            span_id="s1",
            parent_id=None,
            start_time=100.0,
            end_time=None,
            status=SpanStatus.OK,
        )
        assert span.duration_ms is None

    def test_set_attribute(self):
        span = Span(
            name="test",
            trace_id="t1",
            span_id="s1",
            parent_id=None,
            start_time=100.0,
            end_time=None,
            status=SpanStatus.OK,
        )
        span.set_attribute("model", "gpt-4")
        assert span.attributes["model"] == "gpt-4"

    def test_add_event(self):
        span = Span(
            name="test",
            trace_id="t1",
            span_id="s1",
            parent_id=None,
            start_time=100.0,
            end_time=None,
            status=SpanStatus.OK,
        )
        span.add_event("retry", {"attempt": 1})
        assert len(span.events) == 1
        assert span.events[0]["name"] == "retry"

    def test_set_status_with_message(self):
        span = Span(
            name="test",
            trace_id="t1",
            span_id="s1",
            parent_id=None,
            start_time=100.0,
            end_time=None,
            status=SpanStatus.OK,
        )
        span.set_status(SpanStatus.ERROR, "timeout")
        assert span.status == SpanStatus.ERROR
        assert span.attributes["status_message"] == "timeout"


# ── Tracer ───────────────────────────────────────────────────


class TestTracer:
    def test_start_span(self):
        tracer = Tracer(service="test")
        span = tracer.start_span("op1", model="gpt-4")
        assert span.name == "op1"
        assert span.attributes["model"] == "gpt-4"
        assert len(tracer.get_spans()) == 1

    def test_get_trace_same_trace_id(self):
        tracer = Tracer(service="test")
        # Manually set _current_trace_id so spans share a trace
        tracer._current_trace_id = "shared-trace"
        tracer.start_span("a")
        tracer.start_span("b")
        trace = tracer.get_trace("shared-trace")
        assert len(trace) == 2

    def test_export_json(self):
        tracer = Tracer(service="test")
        tracer.start_span("op")
        exported = tracer.export_json()
        data = json.loads(exported)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_export_otlp(self):
        tracer = Tracer(service="test")
        tracer.start_span("op")
        otlp = tracer.export_otlp()
        assert "resource" in otlp
        assert otlp["resource"]["attributes"]["service.name"] == "test"
        assert "spans" in otlp

    def test_export_opentelemetry(self):
        tracer = Tracer(service="test")
        tracer.start_span("op")
        otel = tracer.export_opentelemetry()
        assert "resource" in otel
        assert "spans" in otel
        assert len(otel["spans"]) == 1

    def test_clear(self):
        tracer = Tracer(service="test")
        tracer.start_span("a")
        tracer.start_span("b")
        tracer.clear()
        assert tracer.get_spans() == []


# ── TraceExporter ────────────────────────────────────────────


class TestTraceExporter:
    def test_export_file(self, tmp_path):
        tracer = Tracer(service="test")
        tracer.start_span("op")
        exporter = TraceExporter(tracer)
        path = tmp_path / "traces.json"
        exporter.export_file(str(path))
        assert path.exists()
        data = json.loads(path.read_text())
        assert "spans" in data

    def test_export_stdout(self, capsys):
        tracer = Tracer(service="test")
        tracer.start_span("op")
        exporter = TraceExporter(tracer)
        result = exporter.export_stdout()
        assert "spans" in result
        captured = capsys.readouterr()
        assert "spans" in captured.out

    @pytest.mark.asyncio
    async def test_export_http_success(self):
        tracer = Tracer(service="test")
        tracer.start_span("op")
        exporter = TraceExporter(tracer)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("loopy.observe.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await exporter.export_http("http://localhost:14268/api/traces")
            assert result is True

    @pytest.mark.asyncio
    async def test_export_http_failure(self):
        tracer = Tracer(service="test")
        exporter = TraceExporter(tracer)

        with patch("loopy.observe.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await exporter.export_http("http://bad:1234/api/traces", max_retries=1)
            assert result is False


# ── MetricsCollector ─────────────────────────────────────────


class TestMetricsCollector:
    def test_summary_with_data(self):
        mc = MetricsCollector()
        mc.increment("requests")
        mc.increment("requests")
        mc.histogram("latency", 100.0)
        mc.histogram("latency", 200.0)
        mc.gauge("connections", 5.0)

        summary = mc.summary()
        assert summary["requests"]["count"] == 2
        assert summary["latency"]["sum"] == 300.0
        assert summary["latency"]["min"] == 100.0
        assert summary["latency"]["max"] == 200.0

    def test_export(self):
        mc = MetricsCollector()
        mc.increment("req", model="gpt-4")
        exported = mc.export()
        assert len(exported) == 1
        assert exported[0]["name"] == "req"
        assert exported[0]["tags"]["model"] == "gpt-4"

    def test_clear(self):
        mc = MetricsCollector()
        mc.increment("x")
        mc.clear()
        assert mc.export() == []


# ── v0.8.0 — OTel auto-instrumentation ─────────────────────────────


class TestOTelAutoInstrumentation:
    def setup_method(self):
        # Reset the process-wide default tracer for every test so
        # spans recorded by a previous test do not leak.
        # NOTE: ``loopy.observe`` is shadowed by the decorator exported
        # in loopy/__init__.py, so we reach the module via sys.modules.
        import sys

        loopy_observe_module = sys.modules["loopy.observe"]

        loopy_observe_module.set_default_tracer(loopy_observe_module.Tracer())
        self.tracer = loopy_observe_module.get_default_tracer()

        # Snapshot Gateway.chat so teardown_method can restore it
        # (auto_instrument_gateway monkey-patches the class).
        from loopy.gateway import Gateway as _Gateway

        self._gateway_class = _Gateway
        self._original_chat = _Gateway.__dict__["chat"]

    def teardown_method(self):
        from loopy.gateway import Gateway as _Gateway

        # Always restore the snapshotted original — even if the test
        # did not patch it. This is a no-op when nothing was patched.
        _Gateway.chat = self._original_chat  # type: ignore[assignment]

        import sys

        loopy_observe_module = sys.modules["loopy.observe"]
        loopy_observe_module.set_default_tracer(None)

    @pytest.mark.asyncio
    async def test_observe_async_produces_one_span_with_attributes(self):
        from loopy import observe

        @observe(name="hello", attributes={"who": "world"})
        async def greet():
            return "hi"

        result = await greet()
        assert result == "hi"
        spans = self.tracer.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "hello"
        assert span.attributes["who"] == "world"
        assert span.status == SpanStatus.OK
        assert span.end_time is not None

    def test_observe_sync_produces_one_span(self):
        from loopy import observe

        @observe(name="compute")
        def add(a, b):
            return a + b

        assert add(1, 2) == 3
        spans = self.tracer.get_spans()
        assert len(spans) == 1
        assert spans[0].name == "compute"
        assert spans[0].status == SpanStatus.OK

    @pytest.mark.asyncio
    async def test_observe_exception_marks_span_error_and_reraises(self):
        from loopy import observe

        @observe(name="boom")
        async def kaboom():
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError, match="nope"):
            await kaboom()

        span = self.tracer.get_spans()[0]
        assert span.status == SpanStatus.ERROR
        assert span.attributes["error.message"] == "nope"
        assert span.attributes["error.type"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_auto_instrument_gateway_produces_generation_span(self):
        from loopy import auto_instrument_gateway
        from loopy.gateway import Gateway

        auto_instrument_gateway(tracer=self.tracer)
        # Calling twice must be a no-op (idempotent).
        auto_instrument_gateway(tracer=self.tracer)

        # Drive Gateway.chat with the TestModel injected via the
        # ``model=`` keyword (the test-only short-circuit).
        from loopy.gateway import TestModel

        gw = Gateway()
        await gw.chat("hi", model=TestModel())
        chat_spans = [s for s in self.tracer.get_spans() if s.name == "gateway.chat"]
        assert len(chat_spans) == 1
        assert chat_spans[0].status == SpanStatus.OK
        assert "gateway.model" in chat_spans[0].attributes

    @pytest.mark.asyncio
    async def test_auto_instrument_mcp_produces_tool_span(self):
        """auto_instrument_mcp patches MCPClient.call_tool; we drive the
        patched path by replacing the original method with a LocalMCP
        shim so the test does not need network access."""
        import contextlib

        from loopy import auto_instrument_mcp
        from loopy.mcp import LocalMCP, MCPClient, MCPToolResult

        local = LocalMCP()

        @local.tool("echo", "Echo back the args")
        async def echo(args: dict[str, object]) -> dict[str, object]:
            return {"echo": args}

        class _LocalClient(MCPClient):
            def __init__(self):
                # URL is never resolved — call_tool is shimmed before use.
                super().__init__(server_url="http://localhost:0")
                self._local = local

        from loopy.mcp import MCPClient as _MCP

        # Snapshot to restore in finally.
        original_call_tool = _MCP.__dict__["call_tool"]
        try:
            auto_instrument_mcp(tracer=self.tracer)
            # Idempotent: a second call is a no-op.
            auto_instrument_mcp(tracer=self.tracer)

            # Replace the original call_tool with a LocalMCP shim, then
            # re-instrument so the wrapper wraps the shim.
            async def shim(self, name, arguments=None, *args, **kwargs):  # type: ignore[no-untyped-def]
                if hasattr(self, "_local"):
                    return await self._local.call_tool(name, arguments)
                return MCPToolResult(ok=True, content={})

            # Bypass the idempotency latch and re-wrap.
            with contextlib.suppress(KeyError, AttributeError):
                del _MCP.__dict__["call_tool"].__dict__["_loopy_instrumented"]
            _MCP.call_tool = shim  # type: ignore[assignment,method-assign]
            with contextlib.suppress(KeyError, AttributeError):
                del _MCP.__dict__["call_tool"].__dict__["_loopy_instrumented"]
            auto_instrument_mcp(tracer=self.tracer)

            client = _LocalClient()
            result = await client.call_tool("echo", {"x": 1})
            assert result is not None
            tool_spans = [s for s in self.tracer.get_spans() if s.name == "mcp.call_tool"]
            assert len(tool_spans) == 1
            assert tool_spans[0].attributes.get("mcp.tool") == "echo"
            assert tool_spans[0].status == SpanStatus.OK
        finally:
            _MCP.call_tool = original_call_tool  # type: ignore[assignment,method-assign]

    def test_observe_respects_redactor(self):
        from loopy.observe import Redactor, Tracer

        # Redactor ships with built-in patterns (email/phone/ssn/etc).
        redactor = Redactor()
        tracer = Tracer(redactor=redactor)

        # Decorator with an explicit tracer (skip the default-tracer dance).
        from loopy.observe import observe as observe_deco

        @observe_deco(name="with-secret", tracer=tracer)
        def reveal():
            return "ssn is 123-45-6789"

        assert reveal() == "ssn is 123-45-6789"
        spans = tracer.get_spans()
        assert len(spans) == 1
        # The redactor scrubs attributes; the function's return is untouched.
        assert spans[0].name == "with-secret"

    def test_observe_respects_disabled_flag(self):
        from loopy import observe
        from loopy.observe import Tracer

        tracer = Tracer()
        tracer.disabled = True

        @observe(name="noop", tracer=tracer)
        def go():
            return 42

        assert go() == 42
        assert tracer.get_spans() == []

    def test_observe_after_shutdown_does_not_raise(self):
        from loopy import observe
        from loopy.observe import Tracer

        tracer = Tracer()
        tracer.shutdown()

        @observe(name="post-shutdown", tracer=tracer)
        def go():
            return "ok"

        # No exception, return value intact.
        assert go() == "ok"
        # And no spans were appended to the (already-empty) list.
        assert tracer.get_spans() == []

    def test_double_observe_is_idempotent(self):
        from loopy import observe

        @observe(name="once")
        @observe(name="twice")
        def f():
            return 1

        # Only the outer decorator's span is recorded.
        f()
        spans = self.tracer.get_spans()
        assert len(spans) == 1
        assert spans[0].name == "twice"

    def test_build_otlp_envelope_shape(self):
        from loopy import build_otlp_envelope, observe

        @observe(name="shape")
        def s():
            return 1

        s()
        envelope = build_otlp_envelope(self.tracer.get_spans(), service="loopy-test")
        assert "resourceSpans" in envelope
        rs = envelope["resourceSpans"]
        assert len(rs) == 1
        assert rs[0]["resource"]["attributes"][0]["key"] == "service.name"
        assert rs[0]["resource"]["attributes"][0]["value"]["stringValue"] == "loopy-test"
        scope = rs[0]["scopeSpans"][0]
        assert scope["scope"]["name"] == "loopy"
        assert len(scope["spans"]) == 1
        otlp_span = scope["spans"][0]
        assert otlp_span["name"] == "shape"
        assert otlp_span["status"]["code"] == 1  # OK
        # traceId/spanId populated
        assert otlp_span["traceId"]
        assert otlp_span["spanId"]
