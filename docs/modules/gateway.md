# `loopy.gateway` — Multi-provider LLM gateway

Unified interface for routing requests across OpenAI, Anthropic, and
Ollama, with **zero-network TestModel** and **typed structured outputs**.

## Quickstart

```python
import asyncio
from loopy import Gateway

async def main():
    gw = Gateway()
    response = await gw.chat(
        "Explain the Plan → Act → Observe → Reflect loop in 2 sentences.",
        provider="openai",
    )
    print(response.content)

asyncio.run(main())
```

## Zero-network testing

```python
from loopy import Gateway, TestModel

gw = Gateway()
test_m = TestModel(responses=["hi back"])
r = await gw.chat("hi", model=test_m)
assert r.content == "hi back"
assert r.metadata["test_model"] is True
```

Or use the sentinel string:

```python
r = await gw.chat("hi", model="test")
```

## Typed structured outputs

```python
from pydantic import BaseModel
from loopy import Gateway, TestModel

class Sentiment(BaseModel):
    label: str
    score: float

gw = Gateway()
test_m = TestModel(responses=['{"label":"positive","score":0.92}'])
r = await gw.chat("rate this", model=test_m, response_format=Sentiment)
assert isinstance(r.structured, Sentiment)
assert r.structured.label == "positive"
```

## API

| Symbol | Purpose |
|---|---|
| `Gateway` | The gateway engine |
| `GatewayResponse` | Response with `content`, `tokens_used`, `latency_ms`, `structured` |
| `TestModel` | Zero-network scripted model |
| `TEST_MODEL_SENTINEL` | Use `"test"` instead of constructing a TestModel |
| `ModelProvider` | OPENAI / ANTHROPIC / OLLAMA enum |
| `ProviderConfig` | Per-provider configuration |