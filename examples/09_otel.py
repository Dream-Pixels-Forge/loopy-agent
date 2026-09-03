"""09 — OpenTelemetry auto-instrumentation.

Run with::

    python examples/09_otel.py

No API key required. Demonstrates the ``@observe`` decorator:
a sync or async function is wrapped in a span. The span is
exposed via the default tracer.
"""

import asyncio

from loopy import Tracer
from loopy.observe import observe


@observe(name="compute_thing", attributes={"kind": "demo"})
def compute_thing(x: int) -> int:
    return x * 2


async def compute_async(x: int) -> int:
    @observe(name="compute_async")
    async def inner() -> int:
        return x + 1

    return await inner()


async def main() -> None:
    tracer = Tracer()
    compute_thing(21)
    await compute_async(10)
    spans = tracer.get_spans()
    names = [s.name for s in spans]
    print(f"otel: spans recorded: {names}")


if __name__ == "__main__":
    asyncio.run(main())
