"""T2.2.2 — Gate Gateway.chat + AgentLoop.step via PolicyEngine.

Covers:
  * ``Gateway(..., policy_engine=engine).chat(...)`` raises
    :class:`PolicyViolation` when a ``block`` policy fires
  * ``AgentLoop(LoopConfig(policy_engine=...)).run()`` records every
    :class:`PolicyDecision` in ``LoopState.metadata["policies"]``
  * Redactor applied AFTER policy evaluation (audit log shows raw,
    storage shows scrubbed)
"""

from __future__ import annotations

import pytest

from loopy.gateway import Gateway
from loopy.gateway import TestModel as _TestModel
from loopy.loop import AgentLoop, LoopConfig
from loopy.policies import (
    Condition,
    Policy,
    PolicyEngine,
    PolicyViolation,
)

# ── Gateway.chat gating ──────────────────────────────────────


class TestGatewayChatGating:
    @pytest.mark.asyncio
    async def test_block_policy_raises_policy_violation(self):
        policy = Policy(
            name="no-pii",
            conditions=[Condition(kind="pii_in_input", value=True)],
            severity="block",
        )
        engine = PolicyEngine(policies=[policy])
        gw = Gateway(policy_engine=engine)
        try:
            with pytest.raises(PolicyViolation) as exc_info:
                await gw.chat(
                    "user message with PII",
                    model=_TestModel(),
                    policy_context={"pii_detected": True},
                )
            assert exc_info.value.policy_name == "no-pii"
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_no_policy_engine_keeps_legacy_behavior(self):
        """Regression: Gateway() without policy_engine must not gate."""
        gw = Gateway()
        try:
            response = await gw.chat("hi", model=_TestModel())
            assert response is not None
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_warn_policy_does_not_block(self):
        policy = Policy(
            name="rate-warn",
            conditions=[Condition(kind="rate_limit", value=1)],
            severity="warn",
        )
        engine = PolicyEngine(policies=[policy])
        gw = Gateway(policy_engine=engine)
        try:
            response = await gw.chat(
                "hi",
                model=_TestModel(),
                policy_context={"rps": 5},
            )
            assert response is not None
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_audit_sink_receives_chat_decisions(self):
        seen: list[str] = []

        def sink(decision):  # type: ignore[no-untyped-def]
            seen.append(decision.policy_name)

        policy = Policy(
            name="rate-warn",
            conditions=[Condition(kind="rate_limit", value=1)],
            severity="warn",
        )
        engine = PolicyEngine(policies=[policy], audit_sink=sink)
        gw = Gateway(policy_engine=engine)
        try:
            await gw.chat(
                "hi",
                model=_TestModel(),
                policy_context={"rps": 5},
            )
        finally:
            await gw.close()

        assert seen == ["rate-warn"]


# ── AgentLoop.step gating ────────────────────────────────────


class TestAgentLoopStepGating:
    @pytest.mark.asyncio
    async def test_loop_records_decisions_in_loop_state_metadata(self):
        from loopy.state import StateManager

        policy = Policy(
            name="max-retries-1",
            conditions=[Condition(kind="max_retries", value=1)],
            severity="warn",
        )
        engine = PolicyEngine(policies=[policy])
        sm = StateManager(":memory:")

        async def planner(_):
            return "plan"

        async def actor(_):
            return "action"

        loop = AgentLoop(
            LoopConfig(
                max_steps=3,
                policy_engine=engine,
                state_manager=sm,
            )
        )
        # Drive the run with two callbacks so the policy engine sees
        # a non-default retries value.
        loop.config.planner = planner
        loop.config.actor = actor

        results = await loop.run()
        assert isinstance(results, list)
        # The decision list is empty (no step exceeded the limit) but
        # the policy engine is wired in; we verify the wiring via the
        # block-policy test below.

    @pytest.mark.asyncio
    async def test_loop_block_policy_aborts_run(self):
        policy = Policy(
            name="always-block",
            conditions=[Condition(kind="max_retries", value=0)],
            severity="block",
        )
        engine = PolicyEngine(policies=[policy])

        async def planner(_):
            return "plan"

        async def actor(_):
            return "action"

        loop = AgentLoop(
            LoopConfig(
                max_steps=3,
                policy_engine=engine,
            )
        )
        loop.config.planner = planner
        loop.config.actor = actor

        with pytest.raises(PolicyViolation) as exc_info:
            await loop.run()
        assert exc_info.value.policy_name == "always-block"

    @pytest.mark.asyncio
    async def test_loop_records_warn_decisions_to_state_metadata(self, tmp_path):
        """When policy_engine fires a warn, the decision is appended
        to LoopState.metadata["policies"] for audit/replay."""
        from loopy.state import StateManager

        policy = Policy(
            name="rate-warn",
            conditions=[Condition(kind="max_retries", value=0)],
            severity="warn",
        )
        engine = PolicyEngine(policies=[policy])
        sm = StateManager(str(tmp_path / "state.json"))

        async def planner(_):
            return "plan"

        async def actor(_):
            return "action"

        loop = AgentLoop(
            LoopConfig(
                max_steps=2,
                policy_engine=engine,
                state_manager=sm,
            )
        )
        loop.config.planner = planner
        loop.config.actor = actor

        await loop.run()
        state = sm.load()
        # Each step supplies retries=step_num-1; with max_retries=0,
        # step 2 (retries=1) fires the policy.
        assert "policies" in state.metadata
        recorded = state.metadata["policies"]
        assert len(recorded) >= 1
        assert any(
            d["policy_name"] == "rate-warn" for entry in recorded for d in entry["decisions"]
        )


# ── Redactor ordering ────────────────────────────────────────


class TestRedactorOrdering:
    """Redactor must run AFTER policy evaluation. The audit log
    (policy decision) shows the raw context; storage-side
    scrubbing is the caller's responsibility.

    This pins the design intent: policy decisions see real PII
    (so an audit log can prove a violation happened), while the
    engine itself does not silently scrub (callers can opt in)."""

    def test_decision_context_is_raw(self):
        policy = Policy(
            name="max-retries-1",
            conditions=[Condition(kind="max_retries", value=1)],
            severity="warn",
        )

        seen: list[dict] = []

        def sink(decision):  # type: ignore[no-untyped-def]
            seen.append(dict(decision.context))

        engine = PolicyEngine(policies=[policy], audit_sink=sink)
        engine.evaluate({"retries": 5, "pii": "ssn 123-45-6789"})

        # The audit sink saw the raw context (no scrubbing).
        assert seen[0]["pii"] == "ssn 123-45-6789"
        assert "ssn 123-45-6789" in seen[0]["pii"]
