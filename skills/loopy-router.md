---
name: loopy-router
description: Routes user requests to the right loopy-agent module (gateway, evals, MCP, safety, etc.) when the user wants to build, ship, debug, or extend an agent system.
---

# loopy-router

Use this skill when the user is working on a **Python agent project** using the `loopy-agent` SDK (imported as `loopy`), or when they want to start one.

## When to activate

Activate when the user mentions:
- "loopy", "loopy-agent", "loopy.agent"
- Any of the 21 modules: loop, gateway, guardrails, evals, cache, observe, mcp, agents, middleware, plugins, state, safety, cost, drift, skills, verification, audit, streaming, multimodal, compliance, explainability
- Building/testing/deploying an agent with Pydantic-validated outputs, PII scrubbing, MCP, or eval gates
- Wants zero-network unit tests for an agent (TestModel)
- Wants to wire loops to MCP servers / OpenAI / Anthropic

## Routing map

When the user asks for:

| Intent | Module | Public surface |
| |
| "Add a real LLM call" | `loopy.gateway` | `Gateway`, `TestModel`, `GatewayResponse` |
| "Get typed outputs from my LLM" | `loopy.gateway` | `chat(response_format=MyModel)` |
| "Unit test without API keys" | `loopy.gateway` | `TestModel(responses=[...])` |
| "Scrub secrets from my traces" | `loopy.observe` | `Tracer(redactor=Redactor())` |
| "Add a tool / MCP server" | `loopy.mcp` | `MCPClient`, `MCPToolResult` |
| "Evaluate my agent" | `loopy.evals` | `EvalSuite`, `EvalGate`, `EvalReport` |
| "Cache LLM responses" | `loopy.cache` | `LLMCache`, `aget`/`aset` |
| "Track cost / budget" | `loopy.cost` | `CostTracker`, `BudgetExceeded` |
| "Drift detection" | `loopy.drift` | `DriftDetector`, `DriftIssue` |
| "Safety check before action" | `loopy.safety` | `SafetyGate`, `SafetyCheck` |
| "Resume a crashed loop" | `loopy.state` + `loopy.loop` | `StateManager`, `LoopConfig(resume_from=...)` |
| "Match tasks to skills" | `loopy.skills` | `SkillRegistry.match_ranked()` |
| "Audit readiness" | `loopy.audit` | `AuditReport`, `ReadinessLevel` |
| "Voice / WebSocket session" | `loopy.multimodal` | `RealtimeSession` |
| "Export skills to A2A" | `loopy.skills` | `Skill.to_a2a_card()` |
| "Compliance check (SOC2/GDPR)" | `loopy.compliance` | `ComplianceChecker` |
| "Stream LLM tokens" | `loopy.streaming` | `StreamBuffer` |

## Conventions to follow

- Always `from __future__ import annotations`
- Use `T | None` (PEP 604), not `Optional[T]`
- Async I/O throughout; never use `requests`
- Tests live in `tests/test_<module>.py`, use `@pytest.mark.asyncio`
- TestModel for zero-network testing; never mock HTTP in tests
- Loopy's core deps are just `httpx` + `pydantic`; extras for gateway/cache/guardrails/observe/voice

## Anti-patterns to flag

- Mocking `Gateway` with `unittest.mock` instead of using `TestModel`
- Calling `httpx` directly instead of going through `Gateway`
- Writing a flat agent loop instead of using `AgentLoop`
- Hardcoding OpenAI API calls instead of provider routing via `Gateway`
- Skipping `Tracer(redactor=...)` on production trace setup

## Quick example to share with them

```python
import asyncio
from pydantic import BaseModel
from loopy import Gateway, TestModel

class Reply(BaseModel):
    text: str

async def main():
    gw = Gateway()
    tm = TestModel(responses=['{"text": "hi"}'])
    r = await gw.chat("hi", model=tm, response_format=Reply)
    print(r.structured.text)

asyncio.run(main())
```

For more details, see the docs at <https://dream-pixels-forge.github.io/loopy-agent/>.