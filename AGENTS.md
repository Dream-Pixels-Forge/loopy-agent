# AGENTS.md — context for AI coding assistants

> For Cursor, Cline, Continue, Aider, Windsurf, and any tool that
> reads `AGENTS.md` automatically.

## What this project is

`loopy-agent` is a Python SDK for production agentic AI — 21 modules
in one package, zero heavy core dependencies (just `httpx` +
`pydantic`), optional extras for gateway/cache/guardrails/observe/voice.

- **Package name** (PyPI): `loopy-agent`
- **Import name**: `loopy`
- **Python**: `>=3.10`
- **License**: MIT
- **Repository**: <https://github.com/Dream-Pixels-Forge/loopy-agent>

## The 21 modules

`loopy.loop`, `loopy.gateway`, `loopy.guardrails`, `loopy.evals`,
`loopy.cache`, `loopy.observe`, `loopy.mcp`, `loopy.agents`,
`loopy.middleware`, `loopy.plugins`, `loopy.state`, `loopy.safety`,
`loopy.cost`, `loopy.drift`, `loopy.skills`, `loopy.verification`,
`loopy.audit`, `loopy.streaming`, `loopy.multimodal`,
`loopy.compliance`, `loopy.explainability`.

## Coding conventions

- **Imports**: `from __future__ import annotations` at the top of
  every module.
- **Type hints**: Use `T | None` (PEP 604), not `Optional[T]`. Use
  `dict[str, Any]`, not `Dict[str, Any]`.
- **Dataclasses**: Prefer `@dataclass` over `pydantic.BaseModel` for
  internal data; use `BaseModel` only at module boundaries where
  validation matters.
- **Async**: All I/O is async. Use `httpx.AsyncClient`, never
  `requests`.
- **Enums**: Subclass `str, Enum` so values serialize cleanly.
- **Logging**: Use `logger = logging.getLogger("loopy.<module>")` and
  module-level name.
- **Comments**: None by default. Only add when the *why* is not
  conveyed by the code itself.
- **No print()**: Use the logger.

## Testing conventions

- **Framework**: `pytest` + `pytest-asyncio` (strict mode).
- **File naming**: `tests/test_<module>.py` or
  `tests/test_<module>_coverage.py`.
- **Test classes**: `class TestFooBar:` with method names like
  `test_<specific_behavior>`. Avoid `test_<thing>` if it conflicts
  with pytest's Test* collector (rename the imported symbol with an
  underscore prefix, e.g. `TestModel as _TestModelClass`).
- **Async tests**: Use `@pytest.mark.asyncio` on async test methods.
- **No mocking if you can avoid it**: prefer real objects with
  test-only configurations (`TestModel`, `LocalMCP`,
  in-memory `Tracer`).
- **Coverage target**: 90%+ overall, 100% on public API.

## Linting

- **Tool**: `ruff` with the project's strict config (E, F, W, I, UP,
  B, SIM, C4, PIE, RET). Strict warnings = errors in tests.
- **Before pushing**: `python -m ruff check loopy/ tests/` and
  `python -m ruff format --check loopy/ tests/`.

## Adding a new module

1. Create `loopy/<module>.py` with `from __future__ import annotations` and module-level `logger = logging.getLogger("loopy.<module>")`.
2. Add to `loopy/__init__.py` imports and `__all__`.
3. Add tests in `tests/test_<module>.py`.
4. Update `README.md` concept count and the docs site (`docs/concepts.md`).
5. Run `python -m pytest` — all 500+ tests must pass.

## Adding a new release

1. Bump version in `loopy/_version.py` and `pyproject.toml`.
2. Add a `[X.Y.Z] - YYYY-MM-DD` section to `CHANGELOG.md`.
3. Commit + tag (`git tag -a vX.Y.Z`) + push. The release pipeline handles PyPI + GitHub Release automatically.

## Headline features (since 0.7.8)

- **TestModel** (`loopy.gateway.TestModel`) — zero-network LLM for unit tests
- **StructuredOutput** (`Gateway.chat(response_format=...)`) — Pydantic-validated chat outputs
- **Redactor** (`Tracer(redactor=Redactor())`) — PII/secret scrubbing for traces
- **Skill A2A interop** (`Skill.to_a2a_card()` / `Skill.from_a2a_card()`)
- **RealtimeSession** (`loopy.multimodal.RealtimeSession`) — pluggable transport for voice-first agents

## Architecture notes

- The `loop.py` Plan→Act→Observe→Reflect engine is the spine. Most
  modules modules compose with it (Tracer for spans, StateManager for
  persistence, Redactor for scrubbing).
- `Gateway` is **provider-agnostic** but has OpenAI/Anthropic/Ollama
  handlers built in. New providers subclass + add a handler.
- The `plugins/` subpackage has a strict PEP-508 validator to
  defend against plugin supply-chain attacks. New plugin classes
  should subclass `Plugin` and pass the validator.

## Files most often edited

- `loopy/<module>.py` — module implementation
- `loopy/__init__.py` — exports
- `tests/test_<module>.py` — tests
- `CHANGELOG.md` — release notes
- `pyproject.toml` — version + deps
- `docs/` — mkdocs site (see `docs/mkdocs.yml`)

## Don't touch without care

- `loopy/gateway.py` — large, lots of state; TestModel was added carefully
- `loopy/state.py` — `LoopState` / `RunRecord` shape is on-disk contract
- `loopy/mcp.py` — security-sensitive (SSRF guard, capability gates)
- `loopy/marketplace.py` (in `loopy/plugins/`) — supply-chain security
- `.github/workflows/` — CI release pipeline