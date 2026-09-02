# Recipes

Common patterns in `loopy-agent`.

## Unit-test an agent without API keys

```python
from loopy import Gateway, TestModel

async def test_my_agent():
    gw = Gateway()
    test_m = TestModel(responses=["expected reply"])
    r = await gw.chat("hi", model=test_m)
    assert r.content == "expected reply"
```

## Typed structured outputs

```python
from pydantic import BaseModel
from loopy import Gateway, TestModel

class Greeting(BaseModel):
    message: str
    tone: str

async def main():
    gw = Gateway()
    tm = TestModel(responses=['{"message":"hi","tone":"warm"}'])
    r = await gw.chat("hi", model=tm, response_format=Greeting)
    assert r.structured.tone == "warm"
```

## PII-safe tracing

```python
from loopy import Tracer, Redactor

tracer = Tracer(redactor=Redactor())  # 9 built-in patterns
span = tracer.start_span("llm_call", user_email="alice@example.com")
assert span.attributes["user_email"] == "[EMAIL_REDACTED]"
```

## Resume a crashed loop

```python
from loopy import AgentLoop, LoopConfig, StateManager

sm = StateManager("./state.json")
loop = AgentLoop(LoopConfig(state_manager=sm, task="long-job", max_steps=100))
asyncio.run(loop.run())  # crashes at step 50? run again with resume_from=50.
```

## Connect to an MCP server

```python
from loopy import MCPClient

async with MCPClient(command="npx", args=["-y", "@some/mcp-server"]) as client:
    tools = await client.list_tools()
    result = await client.call_tool(tools[0].name, {})
```

## Export skills to A2A

```python
from loopy import Skill, SkillRegistry

reg = SkillRegistry()
reg.add(Skill(name="CI Triage", description="...", instructions="...", triggers=["ci"]))
cards = reg.to_a2a_skills()  # list of A2A Skill dicts
```