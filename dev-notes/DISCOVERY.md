# Discovery — `loopy-agent` codebase as of 2026-09-02

> **Purpose**: Mandatory pre-document deep discovery. Documents the runtime ecosystem, server entry points, public API surface, dependencies, CI pipelines, and active conventions so a future agent can plan against ground truth (not assumptions).

## 1. Repository topology

| Path | Purpose |
|---|---|
| `loopy/` | Production source (21 modules + 5 support files: `__init__.py`, `_version.py`, `_types.pyi`, `cli.py`, `netutil.py`, `prompting.py`) |
| `loopy/plugins/` | Plugin subpackage — 5 first-party plugins (rag, tools, memory, audio, marketplace) |
| `tests/` | 581 tests across 35 test files |
| `examples/` | Worked examples (01_basic_loop.py, 02_gateway_routing.py, ...) |
| `scripts/` | Release scripts |
| `docs/` | mkdocs-material site + research (added v0.7.10) |
| `AGENTS.md` | Context for Cursor/Cline/Continue/Aider |
| `skills/` | Routing skill for Claude Code/Copilot/Codex/Windsurf |
| `.github/workflows/` | `ci.yml` + `release.yml` |

## 2. Manifest / dependencies (`pyproject.toml`)

- **Python**: `>=3.10` (tested 3.10/3.11/3.12 in CI)
- **Core deps**: `httpx>=0.25.0`, `pydantic>=2.0.0` — **zero heavy deps**
- **Optional extras**:
  - `gateway` → `tenacity>=8.0.0`
  - `cache` → `diskcache>=5.0.0`
  - `guardrails` → `regex>=2023.0.0`
  - `observe` → `rich>=13.0.0`
  - `voice` (v0.7.10) → `websockets>=12.0`
  - `all` → all of the above
  - `dev` → `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`
- **Build**: hatchling, target `loopy/`
- **Entry point**: `loopy` CLI via `loopy.cli:main`
- **PyPI**: `loopy-agent` (import name `loopy`)
- **Current version**: **0.7.10** (tagged, released, latest)

## 3. The 21 modules

`loop` · `gateway` · `guardrails` · `evals` · `cache` · `observe` · `mcp` · `agents` · `middleware` · `plugins` · `state` · `safety` · `cost` · `drift` · `skills` · `verification` · `audit` · `streaming` · `multimodal` · `compliance` · `explainability`

Plus `patterns.py` (added 0.5.0; not counted in headline "21 modules").

## 4. CI pipelines

- **`.github/workflows/ci.yml`** — push/PR trigger. Runs `ruff check`, `ruff format --check`, `pytest --cov=loopy --cov-fail-under=90` on Python 3.10/3.11/3.12 matrix.
- **`.github/workflows/release.yml`** — `v*` tag trigger. Runs tests → build wheel+sdist → publish to PyPI via `pypa/gh-action-pypi-publish` (OIDC / Trusted Publishing) → creates GitHub Release.

## 5. Test infrastructure

- **Framework**: `pytest` + `pytest-asyncio` (strict mode).
- **Coverage target**: 90% line coverage (currently 92%).
- **Strict warnings**: `pyproject.toml` sets `filterwarnings = ["error", ...]` so any deprecation/runtime warning becomes a test failure. Third-party deps (`pkg_resources`, `diskcache`, `dateutil`) are explicitly whitelisted.
- **Lint config**: `ruff` with `select = ["E", "F", "W", "I", "UP", "B", "SIM", "C4", "PIE", "RET"]`. Per-file ignores for tests (`ARG`, `E501`, `W293`).
- **Format config**: `ruff format` with `quote-style = "double"`.

## 6. Public API surface (`loopy/__init__.py`)

~120 exports across 21 modules. Re-exports under `__all__`. The canonical public symbols are documented in:
- `docs/api/index.md` (mkdocs)
- `llms-full.txt` + `llms-*.txt` (22 files, AI-coding-assistant discovery)

## 7. Strategic landscape (cross-references)

The competitive landscape + roadmap lives in **`docs/research/competitive-analysis-2026.md`**. Three tiers of roadmap work:

- **v0.8.0** "Agent Control Plane" — graph control flow, HITL interrupts, OTel auto-instrumentation
- **v0.9.0** "Trust Layer" — A2A handoff, Compliance-as-Code policies, cost-aware adaptive routing
- **v1.0.0** "Production-Grade by Default" — durable agent runtime (Temporal-grade), verified agent programs

Plus open v0.7.10 quick wins shipped.

## 8. Active conventions (from `AGENTS.md`)

- `from __future__ import annotations` at top of every module
- Type hints use PEP 604 `T | None` syntax
- `pydantic.BaseModel` only at module boundaries; `@dataclass` for internal data
- All I/O is async (httpx.AsyncClient; never `requests`)
- Enums subclass `(str, Enum)` for serialization
- Module-level `logger = logging.getLogger("loopy.<module>")`
- No `print()`, no comments unless "why" is non-obvious
- Tests use `TestModel` / `LocalMCP` instead of mocks

## 9. Git conventions

- Branch: `master` (protected, single working branch)
- Conventional Commits v1.0.0 (`feat(scope): ...`, `fix(scope): ...`, `chore(scope): ...`)
- SemVer 2.0.0 tags (`vX.Y.Z`)
- Release flow: bump `_version.py` + `pyproject.toml` + commit + `git tag -a vX.Y.Z` + push → CI publishes to PyPI + creates GitHub Release

## 10. Known gaps vs production standards (see `AUDIT.md`)

The audit (next document) tracks each finding against the production-readiness matrix. Headline gaps:

- **No graph control flow** — `AgentLoop` is flat (Plan→Act→Observe→Reflect); no `StateGraph` like LangGraph
- **No HITL interrupts** — no `interrupt` primitive in `AgentLoop`
- **No durable execution** — no Temporal-grade crash recovery beyond StateManager
- **No OTel auto-instrumentation** — manual `tracer.start_span()` calls
- **No A2A handoff** — only `A2AClient.broadcast` (since v0.7.0; v0.7.10 added Skill interop)
- **No voice/realtime** — `RealtimeSession` skeleton shipped v0.7.10; no concrete WebSocket transport in core
- **No code-execution sandbox** — `SafetyGate` for paths only