"""T2.2.1 — Compliance-as-Code policy engine (v0.9.0).

Covers the new ``loopy.policies`` module:
  * ``Policy`` / ``Condition`` / ``PolicyDecision`` dataclasses
  * ``PolicyEngine.evaluate(context)`` — evaluates every policy
  * ``PolicyViolation`` exception raised when a ``block`` policy fires
  * ``audit_sink`` callback receives every decision
  * 5 policies evaluate in <1ms (no I/O)
  * ``warn`` and ``info`` verdicts do not raise
"""

from __future__ import annotations

import time

import pytest

from loopy.policies import (
    Condition,
    Policy,
    PolicyDecision,
    PolicyEngine,
    PolicyViolation,
)

# ── Construction + validation ────────────────────────────────


class TestConditionValidation:
    def test_known_condition_kinds_accepted(self):
        for kind, value in [
            ("max_retries", 3),
            ("max_cost_usd", 0.05),
            ("pii_in_input", True),
            ("rate_limit", 60),
        ]:
            cond = Condition(kind=kind, value=value)
            assert cond.kind == kind
            assert cond.value == value

    def test_unknown_condition_kind_raises_value_error(self):
        with pytest.raises(ValueError, match="[Uu]nknown condition"):
            Condition(kind="frobnicate", value=42)


class TestPolicyValidation:
    def test_policy_requires_at_least_one_condition(self):
        with pytest.raises(ValueError, match="[Cc]ondition"):
            Policy(name="empty", conditions=[], severity="block")

    def test_policy_severity_must_be_known(self):
        cond = Condition(kind="max_retries", value=3)
        with pytest.raises(ValueError, match="[Ss]everity"):
            Policy(name="bad", conditions=[cond], severity="critical")

    def test_policy_name_must_be_non_empty(self):
        cond = Condition(kind="max_retries", value=3)
        with pytest.raises(ValueError, match="[Nn]ame"):
            Policy(name="", conditions=[cond], severity="warn")


# ── evaluate() ───────────────────────────────────────────────


class TestEvaluate:
    def test_max_retries_blocked_when_exceeded(self):
        policy = Policy(
            name="max-retries-3",
            conditions=[Condition(kind="max_retries", value=3)],
            severity="block",
        )
        engine = PolicyEngine(policies=[policy])

        # Within budget: no decision
        decisions = engine.evaluate({"retries": 2})
        assert decisions == []

        # Over budget: one block decision
        decisions = engine.evaluate({"retries": 5})
        assert len(decisions) == 1
        assert decisions[0].policy_name == "max-retries-3"
        assert decisions[0].verdict == "block"

    def test_max_cost_usd_blocks_overrun(self):
        policy = Policy(
            name="cost-cap",
            conditions=[Condition(kind="max_cost_usd", value=0.05)],
            severity="block",
        )
        engine = PolicyEngine(policies=[policy])
        decisions = engine.evaluate({"cost_usd": 0.10})
        assert decisions[0].verdict == "block"
        assert decisions[0].context["cost_usd"] == 0.10

    def test_pii_in_input_blocks_when_detected(self):
        policy = Policy(
            name="no-pii",
            conditions=[Condition(kind="pii_in_input", value=True)],
            severity="block",
        )
        engine = PolicyEngine(policies=[policy])
        # Detected: blocked.
        decisions = engine.evaluate({"pii_detected": True})
        assert decisions[0].verdict == "block"
        # Clean: no decision.
        assert engine.evaluate({"pii_detected": False}) == []

    def test_rate_limit_blocks_overrun(self):
        policy = Policy(
            name="rate-60",
            conditions=[Condition(kind="rate_limit", value=60)],
            severity="warn",
        )
        engine = PolicyEngine(policies=[policy])
        decisions = engine.evaluate({"rps": 120})
        assert decisions[0].verdict == "warn"
        assert decisions[0].context["rps"] == 120

    def test_warn_verdict_does_not_raise(self):
        policy = Policy(
            name="rate-warn",
            conditions=[Condition(kind="rate_limit", value=10)],
            severity="warn",
        )
        engine = PolicyEngine(policies=[policy])
        # evaluate() never raises; callers decide whether to act on
        # the verdict.
        decisions = engine.evaluate({"rps": 1000})
        assert decisions[0].verdict == "warn"

    def test_empty_policies_evaluates_to_empty_list(self):
        engine = PolicyEngine(policies=[])
        assert engine.evaluate({"retries": 99, "cost_usd": 100}) == []


# ── PolicyViolation + audit_sink ─────────────────────────────


class TestViolationAndAudit:
    def test_block_violation_raises_policy_violation(self):
        policy = Policy(
            name="cost-cap",
            conditions=[Condition(kind="max_cost_usd", value=0.01)],
            severity="block",
        )
        engine = PolicyEngine(policies=[policy])
        with pytest.raises(PolicyViolation) as exc_info:
            engine.gate({"cost_usd": 0.5})
        assert exc_info.value.policy_name == "cost-cap"
        assert exc_info.value.context["cost_usd"] == 0.5

    def test_audit_sink_receives_every_decision(self):
        policy = Policy(
            name="rate-warn",
            conditions=[Condition(kind="rate_limit", value=10)],
            severity="warn",
        )
        seen: list[PolicyDecision] = []

        def sink(decision: PolicyDecision) -> None:
            seen.append(decision)

        engine = PolicyEngine(policies=[policy], audit_sink=sink)
        engine.evaluate({"rps": 50})
        engine.evaluate({"rps": 5})  # within budget, no decision
        engine.evaluate({"rps": 100})

        # Only the over-budget evaluations emit a decision; the
        # in-budget one is silent.
        assert len(seen) == 2
        assert all(d.verdict == "warn" for d in seen)

    def test_decision_carries_timestamp(self):
        policy = Policy(
            name="r",
            conditions=[Condition(kind="rate_limit", value=1)],
            severity="info",
        )
        engine = PolicyEngine(policies=[policy])
        decisions = engine.evaluate({"rps": 5})
        assert decisions[0].timestamp > 0


# ── Performance ──────────────────────────────────────────────


class TestPerformance:
    def test_five_policies_evaluate_under_one_ms(self):
        policies = [
            Policy(
                name=f"p{i}",
                conditions=[Condition(kind="max_retries", value=i + 1)],
                severity="warn",
            )
            for i in range(5)
        ]
        engine = PolicyEngine(policies=policies)
        # Warmup + measure: 1000 evaluations under 1s budget is plenty
        # of headroom (target is <1ms per call).
        engine.evaluate({"retries": 99})  # warmup
        start = time.perf_counter()
        for _ in range(1000):
            engine.evaluate({"retries": 99})
        elapsed = time.perf_counter() - start
        per_call_us = (elapsed / 1000) * 1e6
        assert per_call_us < 1000, f"5 policies evaluated in {per_call_us:.1f}us (target <1000us)"
