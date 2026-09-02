# Milestone Template — copy this for every new milestone

> Use this skeleton when adding a milestone to `dev-notes/GOAL.md`.
> Replace placeholders with concrete content. Delete this comment block when committing.

## Milestone {TIER}.{PHASE}.{N} — {Title}

- **Objective**: One sentence. What does the user gain?
- **File(s) to {create|modify}**: `path/to/file.py` — describe what changes in one line.
- **Public surface**: bullet list of every new/added/changed export.
- **Boundaries**: bullet list of constraints (no I/O in pure functions; idempotency required; etc.).
- **Preconditions**: bullet list — what must be true before starting.
- **Verification Command**: `python -m pytest tests/test_X.py --no-header` exits 0 with N tests passing.
- **Acceptance Criteria**:
  - [ ] Test: human-readable description
  - [ ] Test: another scenario
  - [ ] Coverage of `module.py` ≥ X%
- **Negative Controls**:
  - [ ] Test: malformed input raises `SpecificError`
  - [ ] Test: backward compatibility — old call sites still work
- **Commit message**: `feat(scope): short imperative summary`
- **CHANGELOG**: add bullet under `[X.Y.Z]` section
- **Public-API surface**: add to `loopy/__init__.py` + `__all__` + `docs/api/index.md` + `scripts/generate_llms_txt.py::PUBLIC_MODULES` + regenerate `llms-full.txt`

## Execution checklist

Before moving to the next milestone:

- [ ] `git status` clean before starting
- [ ] Test file created alongside implementation
- [ ] All acceptance criteria checked
- [ ] All negative controls checked
- [ ] Coverage target met (`python -m pytest --cov=loopy --cov-fail-under=90`)
- [ ] `python -m ruff check loopy/ tests/` exits 0
- [ ] `python -m ruff format --check loopy/ tests/` exits 0
- [ ] Strict warnings clean (no `RuntimeWarning`, no `PytestUnraisableExceptionWarning`)
- [ ] Commit made with Conventional Commits message
- [ ] CHANGELOG.md + llms-full.txt + docs/api/index.md updated if any new export added
- [ ] Next milestone's preconditions met