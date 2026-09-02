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
