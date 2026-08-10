"""Loop coverage tests — error paths, custom stop, no-callback stop."""

from __future__ import annotations

import pytest

from loopy.loop import AgentLoop, LoopConfig, StepStatus


class TestLoopErrorPaths:
    @pytest.mark.asyncio
    async def test_stop_on_error_true(self):
        async def planner(h):
            return "plan"

        async def actor(plan):
            raise RuntimeError("boom")

        async def observer(action):
            return "obs"

        async def reflector(h):
            return "ref"

        loop = AgentLoop(LoopConfig(
            planner=planner,
            actor=actor,
            observer=observer,
            reflector=reflector,
            max_steps=5,
            stop_on_error=True,
        ))

        with pytest.raises(RuntimeError, match="boom"):
            await loop.run()

    @pytest.mark.asyncio
    async def test_stop_on_error_false_continues(self):
        call_count = 0

        async def planner(h):
            return "plan"

        async def actor(plan):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first fail")
            return "ok"

        async def observer(action):
            return "obs"

        async def reflector(h):
            return "ref"

        loop = AgentLoop(LoopConfig(
            planner=planner,
            actor=actor,
            observer=observer,
            reflector=reflector,
            max_steps=3,
            stop_on_error=False,
        ))

        results = await loop.run()
        # Step 1 failed, step 2 succeeded
        assert any(r.status == StepStatus.FAILED for r in results)
        assert any(r.status == StepStatus.COMPLETE for r in results)

    @pytest.mark.asyncio
    async def test_no_callbacks_stops(self):
        loop = AgentLoop(LoopConfig(max_steps=10))
        results = await loop.run()
        # No callbacks → default stop condition fires immediately
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_custom_stop_condition(self):
        async def planner(h):
            return "plan"

        async def actor(plan):
            return "action"

        async def should_stop(history):
            return len(history) >= 2

        loop = AgentLoop(LoopConfig(
            planner=planner,
            actor=actor,
            max_steps=10,
            should_stop=should_stop,
        ))

        results = await loop.run()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_stop_condition_error_handled(self):
        async def bad_stop(history):
            raise ValueError("stop check failed")

        async def planner(h):
            return "plan"

        loop = AgentLoop(LoopConfig(
            planner=planner,
            max_steps=2,
            should_stop=bad_stop,
        ))

        results = await loop.run()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_initial_context(self):
        async def planner(h):
            return "plan"

        async def actor(plan):
            return "action"

        loop = AgentLoop(LoopConfig(
            planner=planner,
            actor=actor,
            max_steps=1,
        ))

        results = await loop.run(initial_context="starting point")
        assert results[0].observation == "starting point"

    @pytest.mark.asyncio
    async def test_step_status_flow(self):
        async def planner(h):
            return "plan"

        async def actor(plan):
            return "action"

        async def observer(action):
            return "obs"

        async def reflector(h):
            return "ref"

        loop = AgentLoop(LoopConfig(
            planner=planner,
            actor=actor,
            observer=observer,
            reflector=reflector,
            max_steps=1,
        ))

        results = await loop.run()
        result = results[0]
        assert result.plan == "plan"
        assert result.action == "action"
        assert result.observation == "obs"
        assert result.reflection == "ref"
        assert result.status == StepStatus.COMPLETE
