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

## What's next?

- [Concepts](concepts.md) — the 21 modules at a glance
- [Recipes](recipes/index.md) — common patterns including MCP,
  multi-agent, evaluation, and RAG
- [API reference](api/index.md) — every public symbol