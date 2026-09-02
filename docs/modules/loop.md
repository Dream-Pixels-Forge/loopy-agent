# `loopy.loop` — Agentic loop engine

The core execution cycle for autonomous AI agents: **Plan → Act → Observe → Reflect**.

## Quickstart

```python
import asyncio
from loopy import AgentLoop, LoopConfig

async def plan(_):     return "ask the user"
async def act(_):      return "what is your goal?"
async def obs(_):      return "user said: ship an agent"
async def refl(_):     return "ready"

loop = AgentLoop(LoopConfig(
    planner=plan, actor=act, observer=obs, reflector=refl,
    max_steps=3,
))
history = asyncio.run(loop.run())
```

## Resume after crash

```python
from loopy import AgentLoop, LoopConfig, StateManager

sm = StateManager("./state.json")
loop = AgentLoop(LoopConfig(
    state_manager=sm,
    task="long-running-job",
    resume_from=50,  # pick up at step 51
))
```

## API

| Symbol | Purpose |
|---|---|
| `AgentLoop` | The loop engine |
| `LoopConfig` | Configurable callbacks + state manager |
| `StepResult` | Per-step output |
| `StepStatus` | PLANNING / ACTING / OBSERVING / REFLECTING / COMPLETE / FAILED |