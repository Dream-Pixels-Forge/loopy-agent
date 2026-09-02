# `loopy.observe` — Traces, logs, metrics + OpenTelemetry auto-instrumentation

You can't fix what you can't see. The `observe` module ships a
**zero-deps tracer** (`Tracer`, `Span`, `SpanContext`), a PII redactor
(`Redactor`, `RedactionMatch`), a metrics collector, an OTLP-shaped
exporter, and the v0.8.0 auto-instrumentation surface (`@observe`,
`auto_instrument_gateway`, `auto_instrument_mcp`, `build_otlp_envelope`).

## Quickstart

```python
import asyncio
from loopy import Tracer, Redactor, observe

@observe(name="plan", attributes={"phase": "planning"})
async def make_plan(goal: str) -> str:
    return f"plan for {goal}"

async def main():
    tracer = Tracer(service="my-app", redactor=Redactor())
    with tracer.start("llm_call") as span:
        span.set_attribute("model", "gpt-4")
        plan = await make_plan("ship an agent")
        span.set_attribute("plan_chars", len(plan))
    print(tracer.export_opentelemetry())

asyncio.run(main())
```

## OTel auto-instrumentation (v0.8.0)

Three one-liner surfaces turn the tracer into a wire-ready OTel
pipeline:

```python
from loopy import (
    Tracer,
    Redactor,
    observe,
    auto_instrument_gateway,
    auto_instrument_mcp,
    build_otlp_envelope,
)
```

### `@observe()`

Decorator that wraps any sync or async function in a span.

| Argument    | Type                | Description                                 |
|-------------|---------------------|---------------------------------------------|
| `name`      | `str \| None`       | Span name; defaults to the qualified name.  |
| `attributes`| `dict \| None`      | Static attributes on every span.            |
| `tracer`    | `Tracer \| None`    | Defaults to `get_default_tracer()`.         |

- Exceptions inside the wrapped function mark the span `SpanStatus.ERROR`
  with `error.message` and `error.type` set, then re-raise.
- Re-applying `@observe()` is a no-op (`_loopy_observed` marker).
- Honors `Tracer.disabled` (no spans when `True`) and
  `Tracer.shutdown()` (one-way latch: subsequent calls are silent
  no-ops so decorated functions never raise).

### `auto_instrument_gateway()` / `auto_instrument_mcp()`

Monkey-patch `Gateway.chat` and `MCPClient.call_tool` so every call is
wrapped in a span without touching call sites. Both helpers are
idempotent (re-calling is a no-op).

```python
tracer = Tracer(redactor=Redactor())
auto_instrument_gateway(tracer=tracer)
auto_instrument_mcp(tracer=tracer)
# every Gateway.chat() call now produces a "gateway.chat" span
# every MCPClient.call_tool() call now produces a "mcp.call_tool" span
```

### `build_otlp_envelope(spans, service="loopy")`

Returns an `ExportTraceServiceRequest`-shaped dict ready for `POST`
to the OTel collector's `/v1/traces` HTTP/JSON intake. Filters out
sentinel `recorded=False` spans so disabled/shutdown tracers leave
no trace.

## Operational controls

| Surface                | What it does                                       |
|------------------------|----------------------------------------------------|
| `Tracer.disabled = True` | Runtime flag — no spans recorded.                 |
| `Tracer.shutdown()`    | One-way latch — entry points become silent no-ops. |
| `Tracer(redactor=...)` | Scrubs PII/secrets from every span attribute.     |
| `get_default_tracer()` | Process-wide default the @observe() resolves to.  |
| `set_default_tracer(t)`| Replace or clear (`None`) the default tracer.     |

## Exports

```python
data = tracer.export_opentelemetry()   # OTel collector shape
text = tracer.export_json()            # raw span dicts
```
