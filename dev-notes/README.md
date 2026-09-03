# `dev-notes/` — Machine-Verifiable Implementation Plan

> **For AI agents (and humans) implementing the Tier 1 → Tier 3 roadmap from `docs/research/competitive-analysis-2026.md`.**
>
> Generated using the [production-agentic-engineering skill](https://github.com/donald-stigbert). Read these files in order before writing any code.

## Read order (mandatory)

1. **[`DISCOVERY.md`](./DISCOVERY.md)** — current codebase state, dependencies, CI, public API surface. 5 min read.
2. **[`AUDIT.md`](./AUDIT.md)** — gap assessment against the production-readiness matrix. 10 min read.
3. **[`GOAL.md`](./GOAL.md)** — deterministic execution contract: phase-gated milestones with executable verification commands. **THIS IS THE SOURCE OF TRUTH.**
4. **[`templates/milestone-template.md`](./templates/milestone-template.md)** — skeleton for adding new milestones.

## The contract in one sentence

> Ship the v0.8.0 → v0.9.0 → v1.0.0 roadmap **without ever** committing code that breaks the 581-test suite, ruff lint, ruff format, strict-warnings, or 92% coverage baseline. Every milestone has an executable verification command that MUST return exit code 0 before that milestone is considered complete.

## Tier summary

| Tier       | Release                                  | Theme                                           | Headline features                                              | # new tests | Source                                                             |
| ---------- | ---------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------- | ----------- | ------------------------------------------------------------------ |
| **Tier 1** | **v0.8.0** "Agent Control Plane"         | Ship the missing 2026 primitives                | graph control flow, HITL interrupts, OTel auto-instrumentation | ≥70         | [GOAL.md §T1](../GOAL.md#tier-1--v080-agent-control-plane)         |
| **Tier 2** | **v0.9.0** "Trust Layer"                 | A2A handoff + Compliance-as-Code + cost routing | A2A handoff protocol, Policy DSL, adaptive routing             | ≥100        | [GOAL.md §T2](../GOAL.md#tier-2--v090-trust-layer)                 |
| **Tier 3** | **v1.0.0** "Production-Grade by Default" | The moonshot                                    | durable runtime, verified agents, federated topology           | ≥150        | [GOAL.md §T3](../GOAL.md#tier-3--v100-production-grade-by-default) |
| **Tier 4** | **v1.1** "Try It Now"                    | Adoptability                                    | Playground UI, 10 recipes, `loopy init`, error-message audit  | (planned)   | [`V1.1_PLAYGROUND_AND_ROADMAP.md`](./V1.1_PLAYGROUND_AND_ROADMAP.md) |
| **Tier 5** | **v1.2** "Bring Your Team"               | Federation                                     | multi-tenant gateway, LSP, dev server, adaptive retry         | (planned)   | [`V1.1_PLAYGROUND_AND_ROADMAP.md`](./V1.1_PLAYGROUND_AND_ROADMAP.md) |
| **Tier 6** | **v1.3** "A Mesh of Agents"               | Platform                                        | marketplace, cross-agent memory, learning, formal verification | (planned)   | [`V1.1_PLAYGROUND_AND_ROADMAP.md`](./V1.1_PLAYGROUND_AND_ROADMAP.md) |

## How to use this when you start work

```bash
# 1. Verify environment
cd /path/to/loopy-agent
git status --short                          # must be clean
git log -n 1 origin/master                  # must match HEAD
python -m pytest --no-header                # must show "581 passed"
python -m ruff check loopy/ tests/          # must say "All checks passed!"
python -m ruff format --check loopy/ tests/ # must pass
python -m pytest --cov=loopy --cov-fail-under=90

# 2. Read the milestone you're starting
# Open dev-notes/GOAL.md, find the milestone header.
# Copy templates/milestone-template.md into a new file under dev-notes/milestones/
# (or inline it in GOAL.md if that's the convention).

# 3. Implement + test
# Follow the milestone's verification command.

# 4. Commit
git add -A
git commit -m "feat(scope): what changed and why"

# 5. Move to next milestone
```

## What you MUST NOT do

- ❌ Modify a test assertion to make it pass
- ❌ Disable a ruff rule to silence it
- ❌ Skip a verification command
- ❌ Add a new public symbol without updating CHANGELOG.md + llms-full.txt + docs/api/index.md
- ❌ Tag a release with failing CI

## What you MUST do

- ✅ Read the milestone's verification command BEFORE writing code
- ✅ Run all 5 P0.x pre-flight checks before each Phase
- ✅ Commit after every milestone with `feat(scope): ...` Conventional Commits
- ✅ Update `CHANGELOG.md` + regenerate `llms-full.txt` when adding public symbols
- ✅ When stuck, re-read `dev-notes/AUDIT.md` and `docs/research/competitive-analysis-2026.md`

## Cross-references

- **Strategic landscape + roadmap**: [`docs/research/competitive-analysis-2026.md`](../research/competitive-analysis-2026.md)
- **Public API surface**: [`docs/api/index.md`](../api/index.md)
- **Quick-start**: [`docs/getting-started.md`](../getting-started.md)
- **CI workflows**: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/release.yml`](../../.github/workflows/release.yml)
- **AI-coding-assistant context**: [`../AGENTS.md`](../../AGENTS.md)
- **AI-coding-assistant context**: [`../QWEN.md`](../../QWEN.md)
- **Skill for Claude Code/Copilot**: [`../skills/loopy-router.md`](../../skills/loopy-router.md)
