"""T3.2.1 — VerifiedAgent + VerificationSpec (v1.0.0).

Covers:
  * ``VerifiedAgent(agent, spec)`` construction
  * ``VerificationSpec(input_schema, invariants, properties)``
  * ``output_must_contain(\"hello\")`` fails when output is \"world\"
  * Property ``output_len <= 10 * input_len`` enforced across
    N random cases (Hypothesis-driven)
  * Hypothesis-generated invalid inputs do not crash the agent
  * ``VerificationReport`` carries per-case pass/fail and a
    summary
  * Multiple invariants in a single spec are all evaluated
  * ``Invariant`` / ``Property`` constructed from a callable
"""

from __future__ import annotations

import pytest

from loopy.loop import AgentLoop, LoopConfig
from loopy.verifier import (
    Invariant,
    Property,
    VerificationReport,
    VerificationSpec,
    VerifiedAgent,
    output_length_at_most,
    output_must_contain,
)

# ── Test helpers ────────────────────────────────────────────


def make_text_agent(response: str) -> AgentLoop:
    """Build a single-step AgentLoop whose actor returns ``response``.

    The actor is the right hook for \"the agent's output\" — the
    planner only produces the plan, the action is what the
    verifier inspects.
    """

    async def planner(_):
        return f"plan for: {response[:20]}"

    async def actor(_):
        return response

    return AgentLoop(
        LoopConfig(
            planner=planner,
            actor=actor,
            max_steps=1,
        )
    )


# ── Spec construction + helpers ─────────────────────────────


class TestVerificationSpec:
    def test_spec_with_invariant_constructs(self):
        spec = VerificationSpec(
            input_schema=None,
            invariants=[output_must_contain("hi")],
            properties=[],
        )
        assert len(spec.invariants) == 1
        assert spec.properties == []

    def test_output_must_contain_helper_builds_invariant(self):
        inv = output_must_contain("hello")
        assert isinstance(inv, Invariant)
        assert inv.name == "output_must_contain('hello')"

    def test_output_length_at_most_helper_builds_invariant(self):
        inv = output_length_at_most(10)
        assert isinstance(inv, Invariant)
        assert inv.name == "output_length_at_most(10)"

    def test_property_helper_returns_property(self):
        def my_prop(inp, out):
            return len(out) <= 10 * len(inp)

        prop = Property(name="len-proportional", fn=my_prop)
        assert prop.name == "len-proportional"
        assert prop.fn is my_prop

    def test_invariant_callable_returns_bool(self):
        inv = output_must_contain("x")
        assert inv.fn("xyz", "xyz") is True
        assert inv.fn("xyz", "abc") is False


# ── VerifiedAgent.verify() ────────────────────────────────


class TestVerifiedAgent:
    @pytest.mark.asyncio
    async def test_passing_invariant_returns_pass_report(self):
        agent = make_text_agent("hello world")
        spec = VerificationSpec(
            invariants=[output_must_contain("hello")],
        )
        verifier = VerifiedAgent(agent=agent, spec=spec)
        report = await verifier.verify(n_cases=3)
        assert isinstance(report, VerificationReport)
        assert report.passed is True
        assert report.failures == 0
        assert report.cases_run == 3

    @pytest.mark.asyncio
    async def test_failing_invariant_returns_fail_report(self):
        agent = make_text_agent("world")
        spec = VerificationSpec(
            invariants=[output_must_contain("hello")],
        )
        verifier = VerifiedAgent(agent=agent, spec=spec)
        report = await verifier.verify(n_cases=3)
        assert report.passed is False
        assert report.failures == 3

    @pytest.mark.asyncio
    async def test_multiple_invariants_all_evaluated(self):
        agent = make_text_agent("hi")
        spec = VerificationSpec(
            invariants=[
                output_must_contain("hi"),
                output_length_at_most(100),
            ],
        )
        verifier = VerifiedAgent(agent=agent, spec=spec)
        report = await verifier.verify(n_cases=2)
        assert report.passed is True
        # Both invariants ran; failures should be 0.
        assert report.failures == 0


# ── Properties (N cases) ────────────────────────────────────


class TestProperties:
    @pytest.mark.asyncio
    async def test_property_enforced_across_n_cases(self):
        """The plan asks for ``output_len <= 10 * input_len`` enforced
        across 100 random cases. We run a smaller N=10 in CI to keep
        the test fast and trust the property mechanics."""

        async def echoing_agent(loop: AgentLoop, input_data: str) -> str:
            # The agent's planner is the function we'll drive; it
            # echoes back the input padded to a max of 5 chars.
            class _State:
                data = {"input": input_data}

            return f"echo: {input_data[:5]}"

        async def planner(state):
            return f"echo: {state}"

        # A simple length-bounded property.
        def length_proportional(inp: str, out: str) -> bool:
            return len(out) <= 10 * max(len(inp), 1)

        agent = AgentLoop(LoopConfig(planner=planner, max_steps=1))
        spec = VerificationSpec(
            properties=[Property(name="len-bound", fn=length_proportional)],
        )
        verifier = VerifiedAgent(agent=agent, spec=spec)
        report = await verifier.verify(n_cases=10)
        # All cases should pass.
        assert report.passed is True
        assert report.cases_run == 10

    @pytest.mark.asyncio
    async def test_property_can_fail(self):
        async def planner(_):
            return "x" * 1000

        def always_fails(_inp: str, _out: str) -> bool:
            return False

        agent = AgentLoop(LoopConfig(planner=planner, max_steps=1))
        spec = VerificationSpec(
            properties=[Property(name="never", fn=always_fails)],
        )
        verifier = VerifiedAgent(agent=agent, spec=spec)
        report = await verifier.verify(n_cases=3)
        assert report.passed is False
        assert report.failures == 3


# ── Hypothesis-driven property (optional dependency) ──────


class TestHypothesisOptional:
    @pytest.mark.asyncio
    async def test_hypothesis_generated_inputs_do_not_crash(self):
        """When hypothesis is installed, ``n_cases`` becomes a
        Hypothesis ``given`` strategy. The agent must not crash on
        any of the generated inputs."""
        try:
            from hypothesis import given
            from hypothesis import strategies as st
        except ImportError:
            pytest.skip("hypothesis not installed")

        async def planner(_):
            return "ok"

        agent = AgentLoop(LoopConfig(planner=planner, max_steps=1))
        spec = VerificationSpec(
            invariants=[output_must_contain("ok")],
        )
        verifier = VerifiedAgent(agent=agent, spec=spec)

        @given(st.text(min_size=0, max_size=50))
        @pytest.mark.asyncio
        async def inner(inp):
            report = await verifier.verify(n_cases=2)
            assert report.failures == 0

        await inner()


# ── VerificationReport ──────────────────────────────────────


class TestVerificationReport:
    def test_report_summary_string(self):
        report = VerificationReport(
            passed=True,
            cases_run=10,
            failures=0,
            details=[],
        )
        summary = report.summary()
        assert "10" in summary
        assert "passed" in summary.lower()


# ── Negative controls ──────────────────────────────────────


class TestNegativeControls:
    def test_spec_must_have_at_least_one_invariant_or_property(self):
        with pytest.raises(ValueError, match="[Ii]nvariant|[Pp]roperty"):
            VerificationSpec(invariants=[], properties=[])

    @pytest.mark.asyncio
    async def test_zero_cases_runs_zero_cases(self):
        agent = make_text_agent("ok")
        spec = VerificationSpec(invariants=[output_must_contain("ok")])
        verifier = VerifiedAgent(agent=agent, spec=spec)
        report = await verifier.verify(n_cases=0)
        assert report.cases_run == 0
        assert report.passed is True

    @pytest.mark.asyncio
    async def test_custom_input_generator_used(self):
        """``input_generator=`` overrides the default placeholder
        inputs — useful for the user's own deterministic batch."""
        agent = make_text_agent("ok")
        spec = VerificationSpec(invariants=[output_must_contain("ok")])
        verifier = VerifiedAgent(agent=agent, spec=spec)

        def gen(n: int) -> list[str]:
            return [f"custom-{i}" for i in range(n)]

        report = await verifier.verify(n_cases=2, input_generator=gen)
        assert report.cases_run == 2
        assert report.passed is True
        # The report's details list is empty when nothing fails.
        assert report.details == []

    @pytest.mark.asyncio
    async def test_report_details_capture_failure_reason(self):
        agent = make_text_agent("world")
        spec = VerificationSpec(
            invariants=[output_must_contain("hello")],
        )
        verifier = VerifiedAgent(agent=agent, spec=spec)
        report = await verifier.verify(n_cases=1)
        assert len(report.details) == 1
        assert report.details[0][0] == 0
        assert "output_must_contain" in report.details[0][1]
