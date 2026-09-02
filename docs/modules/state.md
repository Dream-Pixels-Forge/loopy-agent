# `loopy.state` — State persistence + resume

Persist `LoopState` and `RunRecord` objects to disk. Wire into
`LoopConfig(state_manager=...)` and your loop becomes resumable.

## Quickstart

```python
from loopy import StateManager

sm = StateManager("./state.json")
state = sm.load()
state.attempts += 1
sm.save(state)

# After a crash:
state = sm.load()
print(f"resuming from step {state.attempts}")
```

## API

| Symbol | Purpose |
|---|---|
| `StateManager` | Load / save to disk |
| `LoopState` | Loop-wide state (attempts, current_task, history) |
| `RunRecord` | One step's outcome + metadata |
| `RunOutcome` | SUCCESS / FAILURE / SKIPPED |