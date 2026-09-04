# `examples/` — copy-pasteable loopy-agent recipes

> Single-file, no-API-key-required demonstrations of every
> loopy-agent v1.0.0 surface. Each recipe is fewer than 100
> lines and runs with a single ``python examples/0X_name.py``
> command. See [`dev-notes/V1.1_GOAL.md`](../dev-notes/V1.1_GOAL.md)
> for the v1.1 acceptance contract.

## Constraints (every recipe)

- Single file under `examples/`
- Fewer than 100 lines (enforced by `tests/test_examples.py`)
- Uses `TestModel` (no API key required)
- Runs end-to-end with `python examples/<file>`

## Index

| File | What you'll learn | Expected stdout |
|------|-------------------|-------------------|
| [`00_hello_world.py`](00_hello_world.py) | minimal `AgentLoop` | `agent output: ...` |
| [`01_streaming.py`](01_streaming.py) | token-by-token output | `streaming: ...` |
| [`02_cost_capped.py`](02_cost_capped.py) | `max_cost_usd` + provider fallback | `cost-cap: ...` |
| [`03_policies.py`](03_policies.py) | Compliance-as-Code `Policy` gate | `policy: ...` |
| [`04_durable.py`](04_durable.py) | `DAG` + Saga + journal | `durable: final data = ...` |
| [`05_verified.py`](05_verified.py) | `VerifiedAgent` + invariants | `verifier: passed=...` |
| [`06_federation.py`](06_federation.py) | `FederatedServer` HTTP endpoint | `federation: GET ...` |
| [`07_hitl.py`](07_hitl.py) | HITL pause + resume via `Interrupt` | `interrupt: ...` |
| [`08_redaction.py`](08_redaction.py) | `Redactor` PII scrubbing in spans | `redact: ...` |
| [`09_otel.py`](09_otel.py) | `@observe` OpenTelemetry auto-instrumentation | `otel: ...` |

## Running all recipes

```bash
pytest tests/test_examples.py -v
```

This runs every recipe in a fresh subprocess, asserts exit
code 0, and confirms the expected stdout marker is present.

## Cross-links

- Quickstart: [`docs/getting-started.md`](../docs/getting-started.md)
- v1.1 roadmap: [`dev-notes/V1.1_PLAYGROUND_AND_ROADMAP.md`](../dev-notes/V1.1_PLAYGROUND_AND_ROADMAP.md)
- API reference: [`docs/api/index.md`](../docs/api/index.md)
