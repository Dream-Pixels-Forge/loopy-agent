# loopy-agent

> **The Python agent SDK with built-in zero-cost testing, typed LLM outputs, and compliance-grade PII redaction.**

`loopy-agent` is a modular Python toolkit for production agentic AI —
**21 essential AI concepts in one package**. Zero heavy core
dependencies (just `httpx` + `pydantic`), optional extras for gateway
retries, caching, guardrails, observability, and voice/realtime.

```python
from pydantic import BaseModel
from loopy import Gateway, TestModel

class Sentiment(BaseModel):
    label: str
    score: float

gw = Gateway()
response = await gw.chat(
    "How does this product make you feel?",
    model=TestModel(responses=['{"label":"positive","score":0.92}']),
    response_format=Sentiment,
)

print(response.structured.label)   # => "positive"
print(response.structured.score)   # => 0.92
```

## Why loopy-agent?

| Capability | Status |
|---|---|
| **Zero-network `TestModel`** for unit tests | ✅ built-in (since 0.7.9) |
| **Typed structured outputs** via Pydantic | ✅ built-in (since 0.7.9) |
| **PII/secret redaction** for trace storage | ✅ built-in (since 0.7.9) |
| **Loop resume + checkpointing** | ✅ built-in (since 0.7.8) |
| **Async cache + ranked skill matching** | ✅ built-in (since 0.7.8) |
| **MCP client** with capability gates | ✅ built-in (since 0.7.0) |
| **Realtime voice session** (pluggable transport) | ✅ built-in (since 0.7.10) |
| **A2A Skill interop** | ✅ built-in (since 0.7.10) |
| **Compliance-as-code** (SOC2/GDPR/EU-AI-Act) | ✅ unique |
| **Cost budget + drift detection** | ✅ unique |
| **Plugin marketplace + PEP-508 validation** | ✅ unique |
| **Decision audit trail** | ✅ unique |

## The 21 concepts

`loopy-agent` ships **21 modules** in one package — every primitive you need
to build, ship, and observe an agentic system:

`loop` · `gateway` · `guardrails` · `evals` · `cache` · `observe` ·
`mcp` · `agents` · `middleware` · `plugins` · `state` · `safety` ·
`cost` · `drift` · `skills` · `verification` · `audit` · `streaming` ·
`multimodal` · `compliance` · `explainability`

Each module is **opt-in** — use what you need, ignore the rest. The core
package has zero deps beyond `httpx` + `pydantic`.

## Install

```bash
pip install loopy-agent                  # core
pip install loopy-agent[all]             # with every extra
pip install loopy-agent[voice]           # adds websockets for RealtimeSession
pip install loopy-agent[gateway,cache]   # pick what you need
```

## Quickstart

=== "Async"

    ```python
    import asyncio
    from loopy import AgentLoop, LoopConfig

    async def plan(_):  return "ask the user"
    async def act(_):   return "what is your goal?"
    async def obs(_):   return "user said: ship an agent"
    async def refl(_):  return "ready"

    loop = AgentLoop(LoopConfig(
        planner=plan, actor=act, observer=obs, reflector=refl,
        max_steps=3,
    ))

    asyncio.run(loop.run())

=== "TestModel"

    ```python
    import asyncio
    from loopy import Gateway, TestModel

    async def main():
        gw = Gateway()
        r = await gw.chat(
            "hi",
            model=TestModel(responses=["hello world"]),
        )
        assert r.content == "hello world"
        assert r.metadata["test_model"] is True

    asyncio.run(main())
```

## Next steps

- 📚 [Getting started](getting-started.md) — build your first agent in 10 minutes
- 🧠 [Concepts](concepts.md) — the 21 modules at a glance
- 🧪 [Recipes](recipes/index.md) — common patterns
- 📊 [Research](research/competitive-analysis-2026.md) — how loopy stacks against Pydantic AI, LangGraph, CrewAI, OpenAI Agents SDK, AutoGen, LlamaIndex, Atomic Agents