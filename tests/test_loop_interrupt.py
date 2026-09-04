"""v0.8.0 — Human-in-the-loop interrupt semantics for AgentLoop.

Covers:
  * interrupt_before / interrupt_after on each phase
  * combined before+after pausing twice per iteration
  * resume_from(decision="approve") continues the loop
  * resume_from(decision="reject") raises AgentLoopRejected
  * resume_from without a decision raises ValueError
  * Interrupt dataclass validation (decision must be None/approve/reject)
  * LoopConfig validation (unknown phase, max_steps=0)
  * state_manager persistence: interrupt is recorded in LoopState.metadata
  * regression: interrupt_before=[] / interrupt_after=None behave as today
"""

from __future__ import annotations

import pytest

from loopy.loop import AgentLoop, AgentLoopRejected, Interrupt, LoopConfig, StepStatus
from loopy.state import StateManager


async def _planner(_history):  # type: ignore[no-untyped-def]
    return "plan-text"


async def _actor(_plan):  # type: ignore[no-untyped-def]
    return "action-text"


async def _observer(_action):  # type: ignore[no-untyped-def]
    return "obs-text"


async def _reflector(_history):  # type: ignore[no-untyped-def]
    return "ref-text"


class TestInterruptBefore:
    @pytest.mark.asyncio
    async def test_pauses_before_actor_runs(self):
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                observer=_observer,
                reflector=_reflector,
                max_steps=1,
                interrupt_before=["actor"],
            )
        )

        result = await loop.run()

        assert isinstance(result, Interrupt)
        assert result.phase == "actor"
        assert result.step == 1
        assert "actor step 1" in result.proposed_action
        assert result.context["step"] == 1
        assert result.context["phase"] == "actor"

    @pytest.mark.asyncio
    async def test_pauses_before_plan(self):
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                max_steps=1,
                interrupt_before=["plan"],
            )
        )

        result = await loop.run()

        assert isinstance(result, Interrupt)
        assert result.phase == "plan"
        assert "plan step 1" in result.proposed_action

    @pytest.mark.asyncio
    async def test_pauses_before_observer_carries_action(self):
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                observer=_observer,
                max_steps=1,
                interrupt_before=["observer"],
            )
        )

        result = await loop.run()

        assert isinstance(result, Interrupt)
        assert result.phase == "observer"
        # Observer's interrupt context surfaces the action that already ran
        assert result.context["action"] == "action-text"


class TestInterruptAfter:
    @pytest.mark.asyncio
    async def test_pauses_after_actor_carries_output(self):
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                observer=_observer,
                reflector=_reflector,
                max_steps=1,
                interrupt_after=["actor"],
            )
        )

        result = await loop.run()

        assert isinstance(result, Interrupt)
        assert result.phase == "actor"
        # After-gate: the proposal carries the work that was just done.
        assert "actor step 1 produced" in result.proposed_action
        assert result.context["action"] == "action-text"
        assert result.context["when"] == "after"

    @pytest.mark.asyncio
    async def test_pauses_after_reflector(self):
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                observer=_observer,
                reflector=_reflector,
                max_steps=1,
                interrupt_after=["reflector"],
            )
        )

        result = await loop.run()

        assert isinstance(result, Interrupt)
        assert result.phase == "reflector"
        assert "reflector step 1 produced" in result.proposed_action
        assert result.context["when"] == "after"


class TestInterruptBeforeAndAfter:
    @pytest.mark.asyncio
    async def test_before_and_after_pause_twice_per_iteration(self):
        """First call: before-actor interrupt. After approval, second call: after-actor interrupt."""
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                observer=_observer,
                reflector=_reflector,
                max_steps=1,
                interrupt_before=["actor"],
                interrupt_after=["actor"],
            )
        )

        first = await loop.run()
        assert isinstance(first, Interrupt)
        assert first.phase == "actor"
        # The first interrupt should be the BEFORE one.
        assert "run actor step" in first.proposed_action
        assert first.context["when"] == "before"

        # Approve the first interrupt, then expect a second interrupt (the AFTER).
        approved = Interrupt(
            proposed_action=first.proposed_action,
            decision="approve",
            context=first.context,
            phase=first.phase,
            step=first.step,
        )
        second = await loop.run(resume_from=approved)
        assert isinstance(second, Interrupt)
        assert second.phase == "actor"
        assert second.step == 1
        assert "actor step 1 produced" in second.proposed_action
        assert second.context["when"] == "after"


class TestInterruptNoOp:
    @pytest.mark.asyncio
    async def test_unknown_phase_in_list_is_noop_at_runtime(self):
        """interrupt_before=[] matches no phases and is a clean no-op."""
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                max_steps=1,
                interrupt_before=[],
            )
        )

        results = await loop.run()

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].status == StepStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_interrupt_after_none_is_noop(self):
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                max_steps=1,
                interrupt_after=None,
            )
        )

        results = await loop.run()

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].status == StepStatus.COMPLETE


class TestResume:
    @pytest.mark.asyncio
    async def test_resume_from_approve_runs_interrupted_phase_then_continues(self):
        """Approving a before-gate interrupt re-enters the same step, executes the phase,
        then moves on to the next step. The next step's before-gate fires again, returning
        a new Interrupt that we then approve to finish the run."""
        actor_calls: list[str] = []

        async def counting_actor(plan):  # type: ignore[no-untyped-def]
            actor_calls.append(plan)
            return f"action-for-{plan}"

        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=counting_actor,
                observer=_observer,
                reflector=_reflector,
                max_steps=2,
                interrupt_before=["actor"],
            )
        )

        first = await loop.run()
        assert isinstance(first, Interrupt)
        assert first.step == 1
        assert first.phase == "actor"
        # No actor call yet — the before-gate fired first.
        assert actor_calls == []

        approved_1 = Interrupt(
            proposed_action=first.proposed_action,
            decision="approve",
            context=first.context,
            phase=first.phase,
            step=first.step,
        )
        second = await loop.run(resume_from=approved_1)
        # Step 1's actor ran; step 2's before-gate fires a new Interrupt.
        assert isinstance(second, Interrupt)
        assert second.step == 2
        assert actor_calls == ["plan-text"]

        approved_2 = Interrupt(
            proposed_action=second.proposed_action,
            decision="approve",
            context=second.context,
            phase=second.phase,
            step=second.step,
        )
        results = await loop.run(resume_from=approved_2)
        assert isinstance(results, list)
        assert actor_calls == ["plan-text", "plan-text"]

    @pytest.mark.asyncio
    async def test_resume_from_reject_raises_agent_loop_rejected(self):
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                max_steps=1,
                interrupt_before=["actor"],
            )
        )

        first = await loop.run()
        assert isinstance(first, Interrupt)

        rejected = Interrupt(
            proposed_action=first.proposed_action,
            decision="reject",
            context=first.context,
            phase=first.phase,
            step=first.step,
        )
        with pytest.raises(AgentLoopRejected) as exc_info:
            await loop.run(resume_from=rejected)

        assert exc_info.value.proposal == first.proposed_action
        assert exc_info.value.context == first.context
        # str(exc) renders the class-formatted summary (no "rejected" word);
        # repr() carries the original message.
        assert first.proposed_action in repr(exc_info.value)

    @pytest.mark.asyncio
    async def test_resume_from_without_decision_raises_value_error(self):
        interrupt = Interrupt(proposed_action="x", decision=None, phase="actor", step=1)
        loop = AgentLoop(LoopConfig(planner=_planner, actor=_actor, max_steps=1))
        with pytest.raises(ValueError, match="decision"):
            await loop.run(resume_from=interrupt)


class TestInterruptDataclass:
    def test_rejects_invalid_decision(self):
        with pytest.raises(ValueError, match="decision must be"):
            Interrupt(proposed_action="x", decision="maybe")

    def test_accepts_approve(self):
        i = Interrupt(proposed_action="x", decision="approve")
        assert i.decision == "approve"

    def test_accepts_reject(self):
        i = Interrupt(proposed_action="x", decision="reject")
        assert i.decision == "reject"

    def test_accepts_none(self):
        i = Interrupt(proposed_action="x")
        assert i.decision is None


class TestLoopConfigInterruptValidation:
    def test_unknown_phase_in_interrupt_before_raises(self):
        with pytest.raises(ValueError, match="unknown phase"):
            LoopConfig(planner=_planner, max_steps=1, interrupt_before=["nope"])

    def test_unknown_phase_in_interrupt_after_raises(self):
        with pytest.raises(ValueError, match="unknown phase"):
            LoopConfig(planner=_planner, max_steps=1, interrupt_after=["nope"])

    def test_max_steps_zero_with_interrupts_raises(self):
        with pytest.raises(ValueError, match="max_steps"):
            LoopConfig(
                planner=_planner,
                max_steps=0,
                interrupt_before=["actor"],
            )

    def test_max_steps_zero_raises_v1_1(self):
        # v1.1 — max_steps=0 is now universally rejected (the loop
        # never runs anything). Previously this was only enforced
        # when interrupts were configured.
        with pytest.raises(ValueError, match="max_steps"):
            LoopConfig(max_steps=0)


class TestInterruptStatePersistence:
    @pytest.mark.asyncio
    async def test_interrupt_is_persisted_to_state_manager_metadata(self, tmp_path):
        state_path = tmp_path / "loop-state.json"
        manager = StateManager(str(state_path))

        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                observer=_observer,
                reflector=_reflector,
                max_steps=1,
                state_manager=manager,
                task="hitl-demo",
                interrupt_before=["actor"],
            )
        )

        result = await loop.run()
        assert isinstance(result, Interrupt)

        state = manager.load()
        # The interrupt must be visible in the persisted LoopState metadata
        # so a crash+resume can replay.
        assert "interrupts" in state.metadata
        persisted = state.metadata["interrupts"]
        assert len(persisted) == 1
        assert persisted[0]["phase"] == "actor"
        assert persisted[0]["step"] == 1
        assert persisted[0]["proposed_action"] == result.proposed_action


class TestInterruptRegression:
    @pytest.mark.asyncio
    async def test_empty_interrupts_equals_legacy_behavior(self):
        """interrupt_before=[] + interrupt_after=None must match pre-v0.8.0 behavior exactly."""
        loop = AgentLoop(
            LoopConfig(
                planner=_planner,
                actor=_actor,
                observer=_observer,
                reflector=_reflector,
                max_steps=2,
                interrupt_before=[],
                interrupt_after=None,
            )
        )

        results = await loop.run()

        assert isinstance(results, list)
        assert len(results) == 2
        for r in results:
            assert r.status == StepStatus.COMPLETE
            assert r.plan == "plan-text"
            assert r.action == "action-text"
            assert r.observation == "obs-text"
            assert r.reflection == "ref-text"
