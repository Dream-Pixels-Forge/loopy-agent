"""
Observability — You can't fix what you can't see.

Traces, logs, and metrics for LLM observability.
Includes OpenTelemetry export for external observability backends.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from loopy._version import __version__

logger = logging.getLogger("loopy.observe")


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass
class Span:
    """
    A single trace span representing an operation.

    Example:
        span = Tracer.start_span("llm_call", model="gpt-4")
        # ... do work ...
        span.set_attribute("tokens", 150)
        span.set_status(SpanStatus.OK)
        span.end()
    """

    name: str
    trace_id: str
    span_id: str
    parent_id: str | None = None

    start_time: float = field(default_factory=time.time)
    end_time: float | None = None

    status: SpanStatus = SpanStatus.UNSET
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    # v0.8.0 — False for sentinel spans returned by a disabled or
    # shutdown tracer. Drives cheap no-ops in the @observe() decorator
    # and keeps export methods from surfacing internal noise.
    recorded: bool = True

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span."""
        self.events.append(
            {
                "name": name,
                "timestamp": time.time(),
                "attributes": attributes or {},
            }
        )

    def set_status(self, status: SpanStatus, message: str = "") -> None:
        """Set span status."""
        self.status = status
        if message:
            self.attributes["status_message"] = message

    def end(self) -> None:
        """End the span."""
        self.end_time = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
        }


@dataclass
class RedactionMatch:
    """v0.7.9 - A single redacted substring."""

    name: str
    start: int
    end: int
    replacement: str

    def __repr__(self) -> str:
        return f"RedactionMatch(name={self.name!r}, len={self.end - self.start})"


@dataclass
class Redactor:
    """v0.7.9 - PII / secret aware redaction for traces and exports.

    Replaces sensitive substrings with stable placeholders so trace
    storage and HTTP export never leak credentials, tokens, or PII.

    Built-in patterns (all enabled by default):

    | name            | matches                                  |
    |-----------------|------------------------------------------|
    | ``email``       | RFC-ish email addresses                  |
    | ``phone``       | US/International phone-shaped numbers    |
    | ``ssn``         | US Social Security Numbers               |
    | ``credit_card`` | 13-19 digit card-shaped numbers          |
    | ``openai_key``  | ``sk-...``, ``sk-proj-...`` tokens       |
    | ``aws_key``     | ``AKIA``/``ASIA`` access keys            |
    | ``jwt``         | Three-segment dot-delimited JWTs         |
    | ``bearer``      | ``Bearer <token>`` headers               |
    | ``ipv4``        | IPv4 addresses                           |

    Patterns can be removed (``redactor.disable("phone")``) or extended
    (``redactor.add_pattern("employee_id", r"EID-d{6}")``).

    The redactor is *pure-string* and side-effect free: ``redact()``
    never mutates its input, only returns a new string.
    """

    name: str = "default"
    enabled: dict[str, re.Pattern[str]] = field(default_factory=dict)
    extra: dict[str, re.Pattern[str]] = field(default_factory=dict)
    placeholder_format: str = "[{name}_REDACTED]"

    def __post_init__(self) -> None:
        if not self.enabled:
            self.enabled = {
                "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
                "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
                "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
                "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
                "openai_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
                "aws_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
                "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
                "bearer": re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-+/=]+"),
                "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
            }

    def add_pattern(self, name: str, pattern: str) -> None:
        """Register a custom regex pattern under ``name``.

        Raises ``ValueError`` if ``name`` collides with a built-in
        (use ``disable`` first if you really want to override).
        """
        if name in self.enabled:
            raise ValueError(
                f"{name!r} is a built-in pattern; disable it first if you want to override."
            )
        self.extra[name] = re.compile(pattern)

    def disable(self, name: str) -> None:
        """Remove a pattern from the active set."""
        self.enabled.pop(name, None)
        self.extra.pop(name, None)

    @property
    def active_patterns(self) -> dict[str, re.Pattern[str]]:
        """Combined dict of built-in + custom active patterns."""
        return {**self.enabled, **self.extra}

    def redact(self, text: str) -> str:
        """Return a copy of ``text`` with every match replaced."""
        if not isinstance(text, str) or not text:
            return text
        result = text
        for name, pattern in self.active_patterns.items():
            replacement = self.placeholder_format.format(name=name.upper())
            result = pattern.sub(replacement, result)
        return result

    def find_all(self, text: str) -> list[RedactionMatch]:
        """Return every match (name, span) without modifying ``text``."""
        if not isinstance(text, str) or not text:
            return []
        matches: list[RedactionMatch] = []
        for name, pattern in self.active_patterns.items():
            replacement = self.placeholder_format.format(name=name.upper())
            for m in pattern.finditer(text):
                matches.append(
                    RedactionMatch(
                        name=name,
                        start=m.start(),
                        end=m.end(),
                        replacement=replacement,
                    )
                )
        matches.sort(key=lambda m: m.start)
        return matches

    def redact_value(self, value: Any) -> Any:
        """Recursively redact string leaves inside dicts / lists / tuples."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {k: self.redact_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact_value(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.redact_value(v) for v in value)
        return value


class Tracer:
    """
    Distributed tracer for LLM operations.

    Example:
        tracer = Tracer(service="my_app")

        with tracer.start("llm_call") as span:
            span.set_attribute("model", "gpt-4")
            response = await llm.complete(prompt)
            span.set_attribute("tokens", response.usage.total_tokens)
    """

    def __init__(self, service: str = "loopy", redactor: Redactor | None = None):
        self.service = service
        self._spans: list[Span] = []
        self._current_trace_id: str | None = None
        # v0.7.9 - optional redactor applied at span completion.
        self.redactor: Redactor | None = redactor
        # v0.8.0 - instrumentation controls. ``disabled`` is a runtime
        # flag (sets it to True to skip span recording without
        # touching call sites); ``shutdown`` is a one-way latch set
        # by :meth:`shutdown` and makes every public entry point a
        # graceful no-op (used by the @observe() decorator so it
        # never raises after a tracer is torn down).
        self.disabled: bool = False
        self._shutdown: bool = False

    def _generate_id(self) -> str:
        """Generate a unique ID using UUID4."""
        return uuid.uuid4().hex[:16]

    def start_span(
        self,
        name: str,
        parent_id: str | None = None,
        **attributes: Any,
    ) -> Span:
        """
        Start a new span.

        Args:
            name: Span name (e.g., "llm_call", "tool_use")
            parent_id: Optional parent span ID
            **attributes: Initial attributes

        Returns:
            New Span instance. When ``self.disabled`` is True or the
            tracer has been :meth:`shutdown`, a sentinel
            :class:`Span` with ``recorded=False`` is returned so the
            @observe() decorator can drive its lifecycle without
            raising.
        """
        trace_id = self._current_trace_id or self._generate_id()
        span_id = self._generate_id()

        if self.disabled or self._shutdown:
            return Span(
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                parent_id=parent_id,
                recorded=False,
            )

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_id=parent_id,
            attributes={"service": self.service, **attributes},
        )

        # v0.7.9 - scrub attributes/events before storage.
        if self.redactor is not None:
            span.attributes = self.redactor.redact_value(span.attributes)
            span.events = self.redactor.redact_value(span.events)

        self._spans.append(span)
        logger.debug("Started span: %s (%s)", name, span_id)

        return span

    def shutdown(self) -> None:
        """v0.8.0 — one-way latch: subsequent ``start_span`` calls return
        non-recording sentinel spans so instrumentation never raises.
        """
        self._shutdown = True

    def start(self, name: str, **attributes: Any) -> SpanContext:
        """
        Start a span with context manager support.

        Example:
            with tracer.start("llm_call") as span:
                span.set_attribute("model", "gpt-4")
                # ... do work ...
        """
        span = self.start_span(name, **attributes)
        return SpanContext(span)

    def get_spans(self) -> list[Span]:
        """Get all recorded spans."""
        return self._spans.copy()

    def get_trace(self, trace_id: str) -> list[Span]:
        """Get all spans for a trace."""
        return [s for s in self._spans if s.trace_id == trace_id]

    def export_json(self) -> str:
        """Export all spans as JSON."""
        return json.dumps([s.to_dict() for s in self._spans], indent=2)

    def export_otlp(self) -> dict[str, Any]:
        """
        Export spans in OTLP-compatible format.

        Delegates to :meth:`export_opentelemetry` for consistent
        output across all export methods.

        Returns:
            A dict with resource attributes and span data.
        """
        return self.export_opentelemetry()

    def clear(self) -> None:
        """Clear all spans."""
        self._spans.clear()

    def export_opentelemetry(self) -> dict[str, Any]:
        """
        Export spans in OpenTelemetry-compatible format.

        Returns a dict with resource info and spans ready for OTLP export.
        """
        return {
            "resource": {
                "attributes": {
                    "service.name": self.service,
                    "service.version": __version__,
                }
            },
            "spans": [
                {
                    "traceId": s.trace_id,
                    "spanId": s.span_id,
                    "parentSpanId": s.parent_id,
                    "operationName": s.name,
                    "startTime": int(s.start_time * 1e6),  # microseconds
                    "endTime": int((s.end_time or time.time()) * 1e6),
                    "attributes": [
                        {"key": k, "value": {"stringValue": str(v)}}
                        for k, v in s.attributes.items()
                    ],
                    "events": [
                        {
                            "name": e["name"],
                            "time": int(e["timestamp"] * 1e6),
                        }
                        for e in s.events
                    ],
                }
                for s in self._spans
            ],
        }


class TraceExporter:
    """
    Export traces to various backends.

    Example:
        exporter = TraceExporter(tracer)

        # Export to Jaeger
        exporter.export_jaeger("http://localhost:14268/api/traces")

        # Export to file
        exporter.export_file("traces.json")

        # Export to stdout
        exporter.export_stdout()
    """

    def __init__(self, tracer: Tracer):
        self.tracer = tracer

    def export_file(self, path: str) -> None:
        """Export traces to a JSON file.

        Args:
            path: Destination file path.
        """
        data = self.tracer.export_opentelemetry()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Exported %d spans to %s", len(self.tracer.get_spans()), path)

    def export_stdout(self) -> str:
        """Export traces to stdout and return the JSON string."""
        data = self.tracer.export_opentelemetry()
        output = json.dumps(data, indent=2)
        print(output)
        return output

    async def export_http(
        self,
        endpoint: str,
        timeout: float = 10.0,
        max_retries: int = 3,
    ) -> bool:
        """
        Export traces to an HTTP endpoint (e.g., Jaeger, Zipkin).

        Args:
            endpoint: The OTLP/HTTP endpoint URL.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts with
                exponential backoff (1s, 2s, 4s).

        Returns:
            True if successful after all retries.
        """
        data = self.tracer.export_opentelemetry()
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        endpoint,
                        json=data,
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()
                    logger.info("Exported traces to %s", endpoint)
                    return True
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 2**attempt  # 1s, 2s, 4s
                    logger.warning(
                        "Trace export attempt %d/%d failed, retrying in %ds: %s",
                        attempt + 1,
                        max_retries,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)

        logger.error(
            "Failed to export traces after %d attempts: %s",
            max_retries,
            last_error,
        )
        return False


class SpanContext:
    """Context manager for spans."""

    def __init__(self, span: Span):
        self.span = span

    def __enter__(self) -> Span:
        return self.span

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type:
            self.span.set_status(SpanStatus.ERROR, str(exc_val))
        else:
            self.span.set_status(SpanStatus.OK)
        self.span.end()


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    Simple metrics collector for LLM observability.

    Supports counters, histograms, and gauges with tag-based
    grouping for summary aggregation.

    Example:
        metrics = MetricsCollector()

        metrics.increment("llm.requests", tags={"model": "gpt-4"})
        metrics.histogram("llm.tokens", 150, tags={"model": "gpt-4"})
        metrics.gauge("cache.size", 42)

        summary = metrics.summary()
    """

    def __init__(self):
        self._metrics: list[MetricPoint] = []

    def increment(self, name: str, value: float = 1, **tags: str) -> None:
        """Record a counter increment.

        Args:
            name: Metric name.
            value: Amount to increment by (default 1).
            **tags: Key-value tag pairs for grouping.
        """
        self._metrics.append(MetricPoint(name=name, value=value, tags=tags))

    def histogram(self, name: str, value: float, **tags: str) -> None:
        """Record a histogram observation.

        Args:
            name: Metric name.
            value: Observed value.
            **tags: Key-value tag pairs for grouping.
        """
        self._metrics.append(MetricPoint(name=name, value=value, tags=tags))

    def gauge(self, name: str, value: float, **tags: str) -> None:
        """Set a gauge to a value.

        Args:
            name: Metric name.
            value: Current gauge value.
            **tags: Key-value tag pairs for grouping.
        """
        self._metrics.append(MetricPoint(name=name, value=value, tags=tags))

    def summary(self) -> dict[str, Any]:
        """Get summary of collected metrics."""
        by_name: dict[str, list[float]] = {}
        for m in self._metrics:
            if m.name not in by_name:
                by_name[m.name] = []
            by_name[m.name].append(m.value)

        return {
            name: {
                "count": len(values),
                "sum": sum(values),
                "avg": sum(values) / len(values) if values else 0,
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
            }
            for name, values in by_name.items()
        }

    def export(self) -> list[dict[str, Any]]:
        """Export all metrics."""
        return [
            {
                "name": m.name,
                "value": m.value,
                "timestamp": m.timestamp,
                "tags": m.tags,
            }
            for m in self._metrics
        ]

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()


# ── v0.8.0 — OTel auto-instrumentation ───────────────────────────────


_default_tracer: Tracer | None = None


def get_default_tracer() -> Tracer:
    """Return the process-wide default :class:`Tracer`, creating one on first use.

    Decorators and auto-instrumentation helpers resolve to this tracer
    unless an explicit one is passed in.
    """
    global _default_tracer
    if _default_tracer is None:
        _default_tracer = Tracer()
    return _default_tracer


def set_default_tracer(tracer: Tracer | None) -> None:
    """Replace the process-wide default tracer (pass ``None`` to clear)."""
    global _default_tracer
    _default_tracer = tracer


def _resolve_tracer(tracer: Tracer | None) -> Tracer:
    return tracer if tracer is not None else get_default_tracer()


def observe(
    name: str | None = None,
    *,
    attributes: dict[str, Any] | None = None,
    tracer: Tracer | None = None,
):
    """Decorator: wrap a sync or async function in a :class:`Span`.

    Args:
        name: Span name. Defaults to the wrapped function's qualified
            name (``module.func``) when omitted.
        attributes: Static attributes applied to every span this
            decorator produces.
        tracer: Tracer to use. Defaults to the process-wide
            :func:`get_default_tracer`.

    Notes:
        * Re-applying ``@observe()`` to a function that is already
          observed is a no-op (idempotent).
        * Exceptions inside the wrapped function mark the span as
          ``SpanStatus.ERROR`` with ``error.message`` set, then
          re-raise.
        * When the resolved tracer is :attr:`disabled` or has been
          :meth:`shutdown`, the call is a graceful no-op.
    """

    def deco(fn):  # type: ignore[no-untyped-def]
        if getattr(fn, "_loopy_observed", False):
            return fn

        span_name = name or f"{fn.__module__}.{fn.__qualname__}"
        base_attrs = dict(attributes or {})

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
                t = _resolve_tracer(tracer)
                span = t.start_span(span_name, **base_attrs)
                try:
                    result = await fn(*args, **kwargs)
                except Exception as exc:
                    if span.recorded:
                        span.set_status(SpanStatus.ERROR, str(exc))
                        span.attributes["error.message"] = str(exc)
                        span.attributes["error.type"] = type(exc).__name__
                    raise
                else:
                    if span.recorded:
                        span.set_status(SpanStatus.OK)
                finally:
                    span.end()
                return result

            async_wrapper._loopy_observed = True
            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            t = _resolve_tracer(tracer)
            span = t.start_span(span_name, **base_attrs)
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                if span.recorded:
                    span.set_status(SpanStatus.ERROR, str(exc))
                    span.attributes["error.message"] = str(exc)
                    span.attributes["error.type"] = type(exc).__name__
                raise
            else:
                if span.recorded:
                    span.set_status(SpanStatus.OK)
            finally:
                span.end()
            return result

        sync_wrapper._loopy_observed = True
        return sync_wrapper

    return deco


_INSTRUMENTED_ATTR = "_loopy_instrumented"


def auto_instrument_gateway(tracer: Tracer | None = None) -> None:
    """Monkey-patch :meth:`Gateway.chat` so every call is wrapped in a span.

    Idempotent: calling more than once is a no-op. The original
    method is preserved on the class as ``Gateway._chat_untraced``
    so tests and recovery paths can reach it.
    """
    from loopy.gateway import Gateway  # local import — avoid a cycle at module load

    if getattr(Gateway.chat, _INSTRUMENTED_ATTR, False):
        return

    t = _resolve_tracer(tracer)
    original = Gateway.chat

    @functools.wraps(original)
    async def wrapped(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        span = t.start_span("gateway.chat", **{"gateway.model": getattr(self, "model", "")})
        try:
            result = await original(self, *args, **kwargs)
        except Exception as exc:
            if span.recorded:
                span.set_status(SpanStatus.ERROR, str(exc))
                span.attributes["error.message"] = str(exc)
            raise
        else:
            if span.recorded:
                span.attributes.setdefault(
                    "gateway.tokens",
                    getattr(result, "total_tokens", 0) if result is not None else 0,
                )
                span.set_status(SpanStatus.OK)
        finally:
            span.end()
        return result

    wrapped._lopy_observed = True
    setattr(wrapped, _INSTRUMENTED_ATTR, True)
    Gateway.chat = wrapped  # type: ignore[assignment]


def auto_instrument_mcp(tracer: Tracer | None = None) -> None:
    """Monkey-patch :meth:`MCPClient.call_tool` so every call is wrapped in a span."""
    from loopy.mcp import MCPClient

    if getattr(MCPClient.call_tool, _INSTRUMENTED_ATTR, False):
        return

    t = _resolve_tracer(tracer)
    original = MCPClient.call_tool

    @functools.wraps(original)
    async def wrapped(self, name, arguments=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        span = t.start_span("mcp.call_tool", **{"mcp.tool": name})
        try:
            result = await original(self, name, arguments, *args, **kwargs)
        except Exception as exc:
            if span.recorded:
                span.set_status(SpanStatus.ERROR, str(exc))
                span.attributes["error.message"] = str(exc)
            raise
        else:
            if span.recorded:
                span.attributes.setdefault("mcp.ok", bool(getattr(result, "ok", True)))
                span.set_status(SpanStatus.OK)
        finally:
            span.end()
        return result

    wrapped._loopy_observed = True
    setattr(wrapped, _INSTRUMENTED_ATTR, True)
    MCPClient.call_tool = wrapped  # type: ignore[assignment]


def build_otlp_envelope(spans: list[Span], service: str = "loopy") -> dict[str, Any]:
    """Build an OTLP ``ExportTraceServiceRequest``-shaped envelope.

    The shape mirrors the OTel collector's HTTP/JSON intake
    (``POST /v1/traces`` with ``Content-Type: application/json``).
    """
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service}},
                        {"key": "service.version", "value": {"stringValue": __version__}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "loopy", "version": __version__},
                        "spans": [
                            {
                                "traceId": s.trace_id,
                                "spanId": s.span_id,
                                "parentSpanId": s.parent_id or "",
                                "name": s.name,
                                "startTimeUnixNano": str(int(s.start_time * 1e9)),
                                "endTimeUnixNano": str(int((s.end_time or time.time()) * 1e9)),
                                "status": {"code": _otel_status_code(s.status)},
                                "attributes": [
                                    {"key": k, "value": {"stringValue": str(v)}}
                                    for k, v in s.attributes.items()
                                ],
                            }
                            for s in spans
                            if s.recorded
                        ],
                    }
                ],
            }
        ]
    }


def _otel_status_code(status: SpanStatus) -> int:
    return {
        SpanStatus.UNSET: 0,
        SpanStatus.OK: 1,
        SpanStatus.ERROR: 2,
    }.get(status, 0)
