# Getting started

This guide walks you through your first production-quality agent in
about ten minutes, using `loopy-agent`'s headline primitives.

## Install

```bash
pip install loopy-agent
```

Optional extras (pick what you need):

```bash
pip install loopy-agent[gateway]   # tenacity for gateway retries
pip install loopy-agent[cache]     # diskcache for LLM response cache
pip install loopy-agent[guardrails] # regex for PII/jailbreak patterns
pip install loopy-agent[observe]   # rich for trace pretty-printing
pip install loopy-agent[voice]     # websockets for RealtimeSession
pip install loopy-agent[all]       # everything
```

## Hello world

The simplest agent is a 5-line `AgentLoop`:

```python
import asyncio
from loopy import AgentLoop, LoopConfig

async def main():
        loop = AgentLoop(LoopConfig(max_steps=3))
        history = await loop.run(initial_context="Find the best Python agent SDK")
        print(f"ran {len(history)} steps")

asyncio.run(main())
```

That's it — no API keys, no setup. The loop runs with no callbacks
configured and exits immediately.

## A testable agent

The headline feature of `loopy-agent` is `TestModel`, which lets you
exercise the full agent loop **with zero network and zero API keys**.

```python
import asyncio
from loopy import Gateway, TestModel
from pydantic import BaseModel

class Greeting(BaseModel):
    message: str
    tone: str

async def main():
    gw = Gateway()

    # 1. Zero-network model with scripted responses
    test_m = TestModel(responses=[
        'hi there',
        '{"message": "Hello!", "tone": "warm"}',
    ])

    # 2. Typed structured output validated against Greeting
    response = await gw.chat(
        "hi",
        model=test_m,
        response_format=Greeting,
    )

    # 3. Access the validated Pydantic instance
    assert response.structured is not None
    assert response.structured.message == "Hello!"
    assert response.structured.tone == "warm"
    print(response.structured)

asyncio.run(main())
```

This is **the most important pattern** in loopy-agent — every agent
component can be unit-tested without HTTP mocks, network stubs, or
API key management.

## PII-safe traces

Wire a `Redactor` into your tracer and spans are scrubbed before
storage:

```python
from loopy import Tracer, Redactor

tracer = Tracer(redactor=Redactor())  # 9 built-in patterns
span = tracer.start_span("llm_call", user_email="alice@example.com")
assert span.attributes["user_email"] == "[EMAIL_REDACTED]"
```

Built-in patterns: email, phone, SSN, credit card, OpenAI key, AWS
key, JWT, Bearer, IPv4. Add your own with
`redactor.add_pattern("employee_id", r"EID-\d{6}")`.

## Resume on crash

`LoopConfig.state_manager` records every step, so a crashed loop can
be resumed:

```python
import asyncio
from loopy import AgentLoop, LoopConfig, StateManager

async def main():
    sm = StateManager("./state.json")
    loop = AgentLoop(LoopConfig(
        max_steps=100,
        state_manager=sm,
        task="long-running-job",
    ))

    # Crashed at step 50? Pick up where you left off:
    history = await loop.run(initial_context="...")
    print(f"ran {len(history)} steps, persisted {sm.load().attempts} attempts")

asyncio.run(main())
```

## Human-in-the-loop interrupts (v0.8.0)

Pause the loop at any phase so a human can review the proposed
action before it runs (or after it runs, to review the output):

```python
import asyncio
from loopy import AgentLoop, LoopConfig, Interrupt

async def main():
    loop = AgentLoop(LoopConfig(
        max_steps=5,
        interrupt_before=["actor"],   # pause right before the actor runs
    ))

    first = await loop.run()
    if isinstance(first, Interrupt):
        # Show the user `first.proposed_action` + `first.context`
        approved = Interrupt(
            proposed_action=first.proposed_action,
            decision="approve",
            context=first.context,
            phase=first.phase,
            step=first.step,
        )
        results = await loop.run(resume_from=approved)
        # ...or pass decision="reject" to raise AgentLoopRejected

asyncio.run(main())
```

`interrupt_before` and `interrupt_after` accept any subset of
`"plan"`, `"actor"`, `"observer"`, `"reflector"`. Combine them to
review twice per iteration (e.g. `interrupt_before=["actor"]` and
`interrupt_after=["actor"]`). When `LoopConfig.state_manager` is
configured, pending interrupts persist as
`RunRecord(outcome=INTERRUPTED)` so a crashed run can be replayed.

## OTel auto-instrumentation (v0.8.0)

Zero-config tracing: decorate any function, or one-shot auto-patch
the Gateway and MCPClient surfaces:

```python
import asyncio
from loopy import (
    Tracer,
    observe,
    auto_instrument_gateway,
    auto_instrument_mcp,
    build_otlp_envelope,
)

# (1) Decorate any sync or async function with one line.
@observe(name="search", attributes={"kind": "web"})
async def search(q: str) -> str:
    return f"<results for {q}>"

# (2) Auto-patch Gateway.chat and MCPClient.call_tool. Both helpers
# are idempotent. The redactor argument scrubs PII/secrets from
# every recorded span attribute.
from loopy.observe import Redactor

tracer = Tracer(service="my-app", redactor=Redactor())
auto_instrument_gateway(tracer=tracer)
auto_instrument_mcp(tracer=tracer)

async def main():
    await search("loopy")
    # Spans land on ``tracer``. Export in OTLP JSON for any collector:
    envelope = build_otlp_envelope(tracer.get_spans(), service="my-app")
    # POST envelope to /v1/traces (the OTel collector HTTP intake).

asyncio.run(main())
```

`Tracer.disabled` is a runtime flag — set it to `True` to suppress
span recording without touching call sites. `Tracer.shutdown()` is a
one-way latch: after shutdown, every public entry point is a
graceful no-op so decorated functions never raise.

## What's next?

- [Concepts](concepts.md) — the 21 modules at a glance
- [Recipes](recipes/index.md) — common patterns including MCP,
  multi-agent, evaluation, and RAG
- [API reference](api/index.md) — every public symbol