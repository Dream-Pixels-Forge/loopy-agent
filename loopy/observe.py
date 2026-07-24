"""
Observability — You can't fix what you can't see.

Traces, logs, and metrics for LLM observability.
Includes OpenTelemetry export for external observability backends.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })
    
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

    def __init__(self, service: str = "loopy"):
        self.service = service
        self._spans: list[Span] = []
        self._current_trace_id: str | None = None
        self._span_counter = 0

    def _generate_id(self) -> str:
        """Generate a unique ID."""
        self._span_counter += 1
        return f"{self.service}-{self._span_counter:08d}"

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
            New Span instance
        """
        trace_id = self._current_trace_id or self._generate_id()
        span_id = self._generate_id()
        
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_id=parent_id,
            attributes={"service": self.service, **attributes},
        )
        
        self._spans.append(span)
        logger.debug(f"Started span: {name} ({span_id})")
        
        return span

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

    def export_otlp(self) -> list[dict[str, Any]]:
        """
        Export spans in OTLP-compatible format.
        
        Ready to send to Jaeger, Zipkin, or other observability backends.
        """
        return [s.to_dict() for s in self._spans]

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
                    "service.version": "0.3.0",
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
        """Export traces to a JSON file."""
        import json
        data = self.tracer.export_opentelemetry()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Exported {len(self.tracer.get_spans())} spans to {path}")
    
    def export_stdout(self) -> str:
        """Export traces to stdout."""
        import json
        data = self.tracer.export_opentelemetry()
        output = json.dumps(data, indent=2)
        print(output)
        return output
    
    async def export_http(self, endpoint: str, timeout: float = 10.0) -> bool:
        """
        Export traces to an HTTP endpoint (e.g., Jaeger, Zipkin).
        
        Args:
            endpoint: The OTLP/HTTP endpoint URL
            timeout: Request timeout in seconds
        
        Returns:
            True if successful
        """
        try:
            import httpx
            data = self.tracer.export_opentelemetry()
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    endpoint,
                    json=data,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                logger.info(f"Exported traces to {endpoint}")
                return True
        except Exception as e:
            logger.error(f"Failed to export traces: {e}")
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
        """Increment a counter."""
        self._metrics.append(MetricPoint(name=name, value=value, tags=tags))

    def histogram(self, name: str, value: float, **tags: str) -> None:
        """Record a histogram value."""
        self._metrics.append(MetricPoint(name=name, value=value, tags=tags))

    def gauge(self, name: str, value: float, **tags: str) -> None:
        """Set a gauge value."""
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
