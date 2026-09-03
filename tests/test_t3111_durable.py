"""T3.1.1 — Durable Agent Runtime (v1.0.0).

Covers:
  * ``DAG(name, steps)`` + ``Step(name, run, compensation)`` construction
  * ``Workflow.run(dag, state, journal_path=...)`` executes steps in order
  * Saga compensation: if a later step raises, the earlier steps'
    compensation callables run in reverse order
  * Journal: each step's output is recorded to disk
  * ``ResumeToken`` round-trips through pickle + json
  * Kill+restart: pick up at the last completed step
  * ``journal_path=None`` is fully in-memory
  * Negative controls: malformed token, step name with ``/``,
    duplicate step names
"""

from __future__ import annotations

import asyncio
import json
import pickle
from pathlib import Path

import pytest

from loopy.durable import (
    DAG,
    ResumeToken,
    State,
    Step,
    Workflow,
)

# ── Construction ─────────────────────────────────────────────


class TestDAGConstruction:
    def test_dag_with_three_steps_constructs(self):
        dag = DAG(
            name="etl",
            steps=[
                Step("extract", run=lambda s: s),
                Step("transform", run=lambda s: s),
                Step("load", run=lambda s: s),
            ],
        )
        assert dag.name == "etl"
        assert len(dag.steps) == 3

    def test_dag_with_empty_steps_raises(self):
        with pytest.raises(ValueError, match="[Ss]teps"):
            DAG(name="empty", steps=[])

    def test_dag_with_duplicate_step_names_raises(self):
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            DAG(
                name="dups",
                steps=[
                    Step("a", run=lambda s: s),
                    Step("a", run=lambda s: s),
                ],
            )

    def test_dag_with_path_traversal_in_step_name_raises(self):
        with pytest.raises(ValueError, match="/"):
            DAG(
                name="evil",
                steps=[Step("../etc/passwd", run=lambda s: s)],
            )

    def test_step_name_must_be_non_empty(self):
        async def passthrough(s: State) -> State:
            return s

        with pytest.raises(ValueError, match="[Nn]ame"):
            Step("", run=passthrough)


# ── Happy path ────────────────────────────────────────────────


class TestWorkflowRun:
    @pytest.mark.asyncio
    async def test_three_step_dag_runs_in_order(self):
        order: list[str] = []

        def make_step(name: str) -> Step:
            async def run(state: State) -> State:
                order.append(name)
                return state

            return Step(name, run=run)

        dag = DAG(
            name="order",
            steps=[make_step("a"), make_step("b"), make_step("c")],
        )
        final = await Workflow.run(dag, State(data={"v": 0}))

        assert order == ["a", "b", "c"]
        assert final.data == {"v": 0}

    @pytest.mark.asyncio
    async def test_journal_records_each_step_output(self, tmp_path: Path):
        async def step_a(state: State) -> State:
            return State(data={"a": 1})

        async def step_b(state: State) -> State:
            return State(data={"b": 2})

        dag = DAG(
            name="journal",
            steps=[Step("a", run=step_a), Step("b", run=step_b)],
        )
        journal_path = str(tmp_path / "journal.json")
        await Workflow.run(
            dag,
            State(data={}),
            journal_path=journal_path,
        )

        journal = json.loads(Path(journal_path).read_text())
        assert "records" in journal
        names = [r["step"] for r in journal["records"]]
        assert names == ["a", "b"]

    @pytest.mark.asyncio
    async def test_state_passes_through_each_step(self):
        async def make_state(state: State) -> State:
            return State(data={**state.data, "k": state.data.get("k", 0) + 1})

        dag = DAG(
            name="state-flow",
            steps=[
                Step("s1", run=make_state),
                Step("s2", run=make_state),
                Step("s3", run=make_state),
            ],
        )
        final = await Workflow.run(dag, State(data={"k": 0}))
        assert final.data["k"] == 3


# ── Saga compensation ────────────────────────────────────────


class TestSagaCompensation:
    @pytest.mark.asyncio
    async def test_step2_raises_triggers_step1_compensation(self):
        compensations: list[str] = []

        async def step1(state: State) -> State:
            return state

        def compensate1(state: State) -> None:
            compensations.append("step1")

        async def step2(state: State) -> State:
            raise RuntimeError("step2 failed")

        dag = DAG(
            name="saga",
            steps=[
                Step("s1", run=step1, compensation=compensate1),
                Step("s2", run=step2),
            ],
        )
        with pytest.raises(RuntimeError, match="step2 failed"):
            await Workflow.run(dag, State(data={}))

        assert compensations == ["step1"]

    @pytest.mark.asyncio
    async def test_compensations_run_in_reverse_order(self):
        compensations: list[str] = []

        async def passthrough(state: State) -> State:
            return state

        def make_comp(name: str):
            def comp(state: State) -> None:
                compensations.append(name)

            return comp

        async def fail(state: State) -> State:
            raise RuntimeError("boom")

        dag = DAG(
            name="reverse-saga",
            steps=[
                Step("a", run=passthrough, compensation=make_comp("a")),
                Step("b", run=passthrough, compensation=make_comp("b")),
                Step("c", run=fail),
            ],
        )
        with pytest.raises(RuntimeError):
            await Workflow.run(dag, State(data={}))

        assert compensations == ["b", "a"]


# ── Crash + resume ───────────────────────────────────────────


class TestCrashResume:
    @pytest.mark.asyncio
    async def test_resume_picks_up_at_last_completed_step(self, tmp_path: Path):
        """Simulate a crash mid-DAG: step a runs and is journaled;
        step b raises. The next run with a token pointing at step a
        skips a and re-runs from b."""
        ran: list[str] = []
        journal_path = str(tmp_path / "journal.json")

        async def step_a(state: State) -> State:
            ran.append("a")
            return state

        async def step_b(state: State) -> State:
            ran.append("b")
            return state

        async def step_c(state: State) -> State:
            ran.append("c")
            return state

        async def step_b_fails(state: State) -> State:
            ran.append("b")
            raise RuntimeError("simulated crash")

        # First run: a runs and is journaled, then b fails.
        crashed_dag = DAG(
            name="crash-resume",
            steps=[
                Step("a", run=step_a),
                Step("b", run=step_b_fails),
                Step("c", run=step_c),
            ],
        )
        with pytest.raises(RuntimeError, match="simulated crash"):
            await Workflow.run(
                crashed_dag,
                State(data={}),
                journal_path=journal_path,
            )

        # The journal must contain "a" as the last completed step.
        journal = json.loads(Path(journal_path).read_text())
        last_completed = journal["records"][-1]["step"]
        assert last_completed == "a"

        # Build a token and resume with the healthy DAG (b succeeds).
        token = ResumeToken.from_dict(
            {
                "workflow_id": "crash-resume",
                "last_completed_step": last_completed,
                "journal_path": journal_path,
            }
        )
        healthy_dag = DAG(
            name="crash-resume",
            steps=[
                Step("a", run=step_a),
                Step("b", run=step_b),
                Step("c", run=step_c),
            ],
        )
        await Workflow.resume(token, healthy_dag, State(data={}))

        # a ran once (before crash). b ran twice (failed + resumed).
        # c ran once (only on the resumed run, after b succeeded).
        assert ran.count("a") == 1
        assert ran.count("b") == 2
        assert ran.count("c") == 1


# ── ResumeToken round-trip ───────────────────────────────────


class TestResumeToken:
    def test_resume_token_pickle_roundtrip(self):
        token = ResumeToken(
            workflow_id="wf-1",
            last_completed_step="a",
            journal_path="/tmp/journal.json",
        )
        blob = pickle.dumps(token)
        revived = pickle.loads(blob)
        assert revived.workflow_id == "wf-1"
        assert revived.last_completed_step == "a"
        assert revived.journal_path == "/tmp/journal.json"

    def test_resume_token_json_roundtrip(self):
        token = ResumeToken(
            workflow_id="wf-2",
            last_completed_step="b",
            journal_path="/var/j.json",
        )
        blob = token.to_dict()
        revived = ResumeToken.from_dict(blob)
        assert revived == token

    def test_resume_with_malformed_token_raises(self):
        bad = "not-a-resume-token"
        with pytest.raises(ValueError, match="[Tt]oken"):
            Workflow.resume(bad)  # type: ignore[arg-type]

    def test_resume_with_missing_journal_raises(self):
        token = ResumeToken(
            workflow_id="wf-3",
            last_completed_step="a",
            journal_path="/nonexistent/journal.json",
        )
        dag = DAG(name="x", steps=[Step("a", run=lambda s: s)])

        async def run():
            await Workflow.resume(token, dag, State(data={}))

        with pytest.raises((ValueError, FileNotFoundError)):
            asyncio.run(run())


# ── In-memory mode ──────────────────────────────────────────


class TestInMemoryMode:
    @pytest.mark.asyncio
    async def test_journal_path_none_runs_in_memory(self, tmp_path: Path):
        """journal_path=None means no file is written or read."""
        import os

        cwd_before = Path.cwd()
        os.chdir(tmp_path)
        try:

            async def passthrough(state: State) -> State:
                return state

            dag = DAG(
                name="mem",
                steps=[
                    Step("a", run=passthrough),
                    Step("b", run=passthrough),
                ],
            )
            final = await Workflow.run(dag, State(data={"x": 1}))
            assert final.data == {"x": 1}
            # tmp_path is empty (no journal file written).
            assert list(tmp_path.iterdir()) == []
        finally:
            os.chdir(cwd_before)


# ── State dataclass ─────────────────────────────────────────


class TestState:
    def test_state_carries_data_and_metadata(self):
        s = State(data={"k": "v"}, metadata={"step": 1})
        assert s.data == {"k": "v"}
        assert s.metadata == {"step": 1}

    def test_state_data_is_isolated_per_instance(self):
        s1 = State(data={"k": 1})
        s2 = State(data={"k": 2})
        assert s1.data != s2.data

    def test_state_is_immutable_to_step_chains(self):
        """Steps must not mutate the input state in place — they
        return a new State. Verify by chaining two steps that
        replace ``data``."""

        async def replace(state: State) -> State:
            return State(data={"replaced": True})

        dag = DAG(
            name="immutable",
            steps=[
                Step("a", run=replace),
                Step("b", run=replace),
            ],
        )
        original = State(data={"original": 1})
        final = asyncio.run(Workflow.run(dag, original))

        # Original state is untouched.
        assert original.data == {"original": 1}
        # Final state has the replaced value.
        assert final.data == {"replaced": True}

    def test_dag_must_have_at_least_one_step(self):
        """Negative: empty DAG is rejected at construction."""
        with pytest.raises(ValueError, match="[Ss]tep"):
            DAG(name="empty", steps=[])
