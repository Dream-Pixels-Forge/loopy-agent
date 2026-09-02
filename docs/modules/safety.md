# `loopy.safety` — Safety gate

A safety gate for actions like file system writes, network requests,
and shell commands. Each call returns a structured `SafetyCheck` and
optionally escalates to a human reviewer.

## Quickstart

```python
import asyncio
from loopy import SafetyGate, EscalationReason

async def main():
    gate = SafetyGate()
    check = await gate.check_path("/tmp/loopy.log")
    print(check.allowed, check.reason, check.escalation)

    check = await gate.check(
        action="shell",
        target="rm",
        args=["-rf", "/"],
    )
    print(check.allowed)  # False, dangerous command

asyncio.run(main())
```

## API

| Symbol | Purpose |
|---|---|
| `SafetyGate` | The gate itself |
| `SafetyCheck` | Result of a single check |
| `SafetyResult` | Aggregate result |
| `EscalationReason` | BLOCKED / NEEDS_REVIEW / ALLOWED |