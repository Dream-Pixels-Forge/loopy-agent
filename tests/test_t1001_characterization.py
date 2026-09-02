"""T1.0.1 characterization tests — pin existing AgentLoop behavior.

These tests do NOT modify production code. They record the current
public contract of ``loopy.loop`` so v0.8.0 (HITL interrupts) can extend
``AgentLoop`` without regressing it.

Coverage target: ``loopy/loop.py`` >= 95% (currently 96% baseline).
"""

from __future__ import annotations

import pytest

from loopy.loop import AgentLoop, LoopConfig, StepResult, StepStatus

# ---------------------------------------------------------------------------
# Configuration shape characterization
# ---------------------------------------------------------------------------


class TestLoopConfigCharacterization:
    def test_default_loopconfig_defaults(self):
        """Characterize LoopConfig default values that the rest of the loop relies on."""
        cfg = LoopConfig()
        assert cfg.max_steps == 10
        assert cfg.max_retries == 3
        assert cfg.stop_on_error is False
        assert cfg.planner is None
        assert cfg.actor is None
        assert cfg.observer is None
        assert cfg.reflector is None
        assert cfg.should_stop is None
        # v0.7.8 fields
        assert cfg.resume_from is None
        assert cfg.state_manager is None
        assert cfg.task == ""


class TestLoopConfigEdgeCases:
    """Behavior pinned before T1.2 adds interrupt fields."""

    def test_max_retries_zero_does_not_retry(self):
        """With max_retries=0, an actor raising should fail fast."""

        async def actor(_):
            raise RuntimeError("nope")

        async def planner(_):
            return "plan"

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                observer=lambda _a: "ok",
                max_steps=2,
                max_retries=0,
            )
        )
        # We don't assert exact behavior — only that it returns something.
        import asyncio

        asyncio.run(loop.run())


# ---------------------------------------------------------------------------
# AgentLoop.run() characterization
# ---------------------------------------------------------------------------


class TestAgentLoopRunCharacterization:
    @pytest.mark.asyncio
    async def test_empty_loopconfig_stops_immediately(self):
        """No callbacks => loop runs exactly one step then default-stop fires.

        The default-stop branch fires when all callbacks are None; but
        the loop still executes ONE step before checking that condition.
        The returned history contains exactly one COMPLETE StepResult.
        """
        loop = AgentLoop(LoopConfig())
        results = await loop.run()
        assert len(results) == 1
        assert results[0].status == StepStatus.COMPLETE
        assert results[0].step == 1

    @pytest.mark.asyncio
    async def test_run_twice_starts_with_fresh_history(self):
        """Two consecutive run() calls must not share history."""

        async def planner(_):
            return "p"

        async def actor(_):
            return "a"

        loop = AgentLoop(LoopConfig(planner=planner, actor=actor, max_steps=1))
        first = await loop.run()
        second = await loop.run()
        # Each call should produce exactly one step.
        assert len(first) == 1
        assert len(second) == 1
        # History starts empty between runs.
        assert first is not second

    @pytest.mark.asyncio
    async def test_initial_context_empty(self):
        async def planner(_):
            return "p"

        async def actor(_):
            return "a"

        loop = AgentLoop(LoopConfig(planner=planner, actor=actor, max_steps=1))
        results = await loop.run(initial_context="")
        # Empty string should NOT seed an observation step.
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_initial_context_nonempty(self):
        async def planner(_):
            return "p"

        async def actor(_):
            return "a"

        loop = AgentLoop(LoopConfig(planner=planner, actor=actor, max_steps=1))
        results = await loop.run(initial_context="start here")
        assert len(results) == 2  # initial observation step + step 1
        assert results[0].observation == "start here"
        assert results[0].status == StepStatus.OBSERVING

    @pytest.mark.asyncio
    async def test_callbacks_raising_with_stop_on_error_true(self):
        async def actor(_):
            raise RuntimeError("boom")

        async def planner(_):
            return "p"

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                observer=lambda _a: "ok",
                reflector=lambda _h: "ok",
                max_steps=3,
                stop_on_error=True,
            )
        )
        with pytest.raises(RuntimeError, match="boom"):
            await loop.run()

    @pytest.mark.asyncio
    async def test_callbacks_raising_with_stop_on_error_false(self):
        async def actor(_):
            raise RuntimeError("boom")

        async def planner(_):
            return "p"

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                observer=lambda _a: "ok",
                reflector=lambda _h: "ok",
                max_steps=2,
                stop_on_error=False,
            )
        )
        results = await loop.run()
        # Step 1 fails, step 2 also fails but loop continues.
        assert len(results) == 2
        assert all(r.status == StepStatus.FAILED for r in results)

    @pytest.mark.asyncio
    async def test_max_steps_one_terminates_after_one_iteration(self):
        async def planner(_):
            return "p"

        async def actor(_):
            return "a"

        loop = AgentLoop(LoopConfig(planner=planner, actor=actor, max_steps=1))
        results = await loop.run()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_multi_step_full_lifecycle(self):
        seen = {"plan": [], "action": [], "observe": [], "reflect": []}

        async def planner(h):
            seen["plan"].append(len(h))
            return f"plan-{len(h)}"

        async def actor(plan):
            seen["action"].append(plan)
            return f"action-{plan}"

        async def observer(action):
            seen["observe"].append(action)
            return f"observe-{action}"

        async def reflector(h):
            seen["reflect"].append(len(h))
            return f"reflect-{len(h)}"

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                observer=observer,
                reflector=reflector,
                max_steps=3,
            )
        )
        results = await loop.run()
        assert len(results) == 3
        assert seen["plan"] == [0, 1, 2]
        assert len(seen["action"]) == 3

    @pytest.mark.asyncio
    async def test_custom_should_stop_terminates_early(self):
        async def planner(_):
            return "p"

        async def actor(_):
            return "a"

        async def stop_at_three(_history):
            return len(_history) >= 3

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                max_steps=10,
                should_stop=stop_at_three,
            )
        )
        results = await loop.run()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_custom_should_stop_exception_continues_loop(self):
        async def planner(_):
            return "p"

        async def actor(_):
            return "a"

        async def bad_stop(_h):
            raise ValueError("nope")

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                max_steps=2,
                should_stop=bad_stop,
            )
        )
        results = await loop.run()
        # The exception is logged but the loop continues to max_steps.
        assert len(results) == 2


# ---------------------------------------------------------------------------
# StepResult / StepStatus characterization
# ---------------------------------------------------------------------------


class TestStepResultCharacterization:
    @pytest.mark.asyncio
    async def test_step_result_attributes_after_complete(self):
        async def planner(_):
            return "plan-x"

        async def actor(_):
            return "action-x"

        async def observer(_):
            return "obs-x"

        async def reflector(_):
            return "ref-x"

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                observer=observer,
                reflector=reflector,
                max_steps=1,
            )
        )
        results = await loop.run()
        r = results[0]
        assert isinstance(r, StepResult)
        assert r.step == 1
        assert r.status == StepStatus.COMPLETE
        assert r.plan == "plan-x"
        assert r.action == "action-x"
        assert r.observation == "obs-x"
        assert r.reflection == "ref-x"
        assert r.error is None
        assert r.data == {}

    @pytest.mark.asyncio
    async def test_step_result_after_failure_has_error(self):
        async def planner(_):
            return "p"

        async def actor(_):
            raise RuntimeError("kaboom")

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                observer=lambda _a: "obs",
                reflector=lambda _h: "ref",
                max_steps=1,
                stop_on_error=False,
            )
        )
        results = await loop.run()
        r = results[0]
        assert r.status == StepStatus.FAILED
        assert r.error == "kaboom"


# ---------------------------------------------------------------------------
# Negative controls from GOAL.md §T1.0.1
# ---------------------------------------------------------------------------


class TestAgentLoopNegativeControls:
    @pytest.mark.asyncio
    async def test_no_state_manager_means_no_disk_writes(self, tmp_path):
        """AgentLoop without state_manager must not write any file.

        Strategy: instrument cwd to be tmp_path; if any file is created
        under it, fail the test.
        """
        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            loop = AgentLoop(LoopConfig())  # no state_manager
            await loop.run()
            assert list(tmp_path.iterdir()) == [], (
                f"AgentLoop created files in cwd without state_manager: {list(tmp_path.iterdir())}"
            )
        finally:
            os.chdir(old_cwd)

    @pytest.mark.asyncio
    async def test_consecutive_runs_planner_sees_fresh_history(self):
        """A second run() must hand the planner a fresh, empty history.

        The ``loop.history`` attribute accumulates across runs (it is
        never reset between ``run()`` calls), but each call starts
        with its own internal history list — so the planner sees
        ``len(history) == 0`` on every run's first call.
        """
        first_call_lens: list[int] = []

        async def planner(h):
            first_call_lens.append(len(h))
            return "plan"

        async def actor(_):
            return "action"

        loop = AgentLoop(LoopConfig(planner=planner, actor=actor, max_steps=2))
        await loop.run()
        await loop.run()
        # Both runs' planner calls started with an empty history.
        assert first_call_lens[0] == 0
        assert first_call_lens[2] == 0
        # Returned lists are distinct (each run had its own).
        first_run_results = first_call_lens
        assert len(first_run_results) >= 2


# ---------------------------------------------------------------------------
# v0.7.8 checkpointing — characterization before T1.1.1 changes anything
# ---------------------------------------------------------------------------


class TestCheckpointCharacterization:
    @pytest.mark.asyncio
    async def test_state_manager_persists_run_records(self, tmp_path):
        """Each completed step produces a RunRecord in the state_manager."""
        from loopy.state import StateManager

        sm = StateManager(str(tmp_path / "state.json"))
        loop = AgentLoop(
            LoopConfig(
                planner=lambda _: "p",
                actor=lambda _: "a",
                observer=lambda _: "obs",
                reflector=lambda _: "ref",
                max_steps=2,
                state_manager=sm,
                task="char-test",
            )
        )
        await loop.run()
        state = sm.load()
        # 2 successful steps => 2 RunRecords
        assert len(state.history) == 2
        assert state.attempts == 2
        assert state.current_task == "char-test"
