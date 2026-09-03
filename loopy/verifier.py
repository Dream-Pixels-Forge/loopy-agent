"""v1.0.0 — Verified Agent Programs.

Ship an :class:`AgentLoop` with a :class:`VerificationSpec` of
invariants and properties; the verifier drives the agent on a
batch of inputs (deterministic or Hypothesis-generated) and
returns a :class:`VerificationReport` so CI can block on a
behavioural regression.

The design mirrors Langfuse's ``Evaluator`` and OpenAI Evals
but stays tiny: no extra dependencies, optional Hypothesis
integration behind the ``[hypothesis]`` extra.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("loopy.verifier")


InvariantFn = Callable[[str, str], bool]
PropertyFn = Callable[[str, str], bool]


@dataclass
class Invariant:
    """A single ``output must ...`` rule.

    ``fn`` is ``(input, output) -> bool``. ``True`` means the
    invariant is satisfied; ``False`` (or a falsy return) is a
    failure.
    """

    name: str
    fn: InvariantFn


@dataclass
class Property:
    """A property-based rule, evaluated over a batch of random inputs.

    Same shape as :class:`Invariant` but conventionally used in
    ``VerificationSpec.properties`` for Hypothesis-driven
    fuzzing.
    """

    name: str
    fn: PropertyFn


@dataclass
class VerificationSpec:
    """Bundle of invariants + properties to enforce.

    At construction, the spec rejects an empty list of both
    invariants and properties (a no-op spec is almost always a
    bug — surface it).
    """

    invariants: list[Invariant] = field(default_factory=list)
    properties: list[Property] = field(default_factory=list)
    input_schema: type | None = None

    def __post_init__(self) -> None:
        if not self.invariants and not self.properties:
            raise ValueError("VerificationSpec must declare at least one Invariant or Property")


@dataclass
class VerificationReport:
    """Outcome of a :meth:`VerifiedAgent.verify` run.

    ``cases_run`` is the number of inputs driven through the
    agent. ``failures`` is the count of cases where at least one
    invariant or property returned ``False``. ``details`` is a
    list of (case_index, reason) pairs for debugging.
    """

    passed: bool
    cases_run: int
    failures: int
    details: list[tuple[int, str]] = field(default_factory=list)

    def summary(self) -> str:
        status = "passed" if self.passed else "FAILED"
        return (
            f"Verification {status}: {self.cases_run - self.failures}/{self.cases_run} cases passed"
        )


# ── Built-in invariant factories ─────────────────────────────


def output_must_contain(needle: str) -> Invariant:
    """``Invariant`` that fails when the output does not contain
    ``needle``."""

    def fn(_inp: str, output: str) -> bool:
        return needle in output

    return Invariant(name=f"output_must_contain({needle!r})", fn=fn)


def output_length_at_most(n: int) -> Invariant:
    """``Invariant`` that fails when the output exceeds ``n`` chars."""

    def fn(_inp: str, output: str) -> bool:
        return len(output) <= n

    return Invariant(name=f"output_length_at_most({n})", fn=fn)


# ── VerifiedAgent ────────────────────────────────────────────


def _generate_inputs(n_cases: int) -> list[str]:
    """Default input generator: deterministic placeholder strings.

    When Hypothesis is installed, callers can wrap ``verify`` with
    ``@given`` to feed property-generated inputs instead — the
    public surface does not require Hypothesis.
    """
    return [f"case-{i}" for i in range(n_cases)]


@dataclass
class VerifiedAgent:
    """An :class:`AgentLoop` wrapped with a :class:`VerificationSpec`.

    ``verify(n_cases=100)`` drives the agent on ``n_cases`` inputs
    (default deterministic, override by passing a custom
    generator) and returns a :class:`VerificationReport`.
    """

    agent: Any
    spec: VerificationSpec

    async def _drive_once(self, input_data: str) -> str:
        """Run the agent on a single input and return the final
        step's action as the output."""
        history = await self.agent.run(input_data)
        # ``agent.run`` returns either an Interrupt or a
        # list[StepResult]. We map both to a single string output.
        if isinstance(history, list) and history:
            last = history[-1]
            return str(getattr(last, "action", "") or "")
        return ""

    async def verify(
        self,
        n_cases: int = 100,
        *,
        input_generator: Callable[[int], list[str]] | None = None,
    ) -> VerificationReport:
        inputs = (
            input_generator(n_cases) if input_generator is not None else _generate_inputs(n_cases)
        )

        failures: list[tuple[int, str]] = []
        for idx, inp in enumerate(inputs):
            try:
                output = await self._drive_once(inp)
            except Exception as exc:  # noqa: BLE001
                # Hypothesis-fuzzed invalid inputs must NOT crash
                # the verifier — record the failure and move on.
                failures.append((idx, f"agent raised: {exc!r}"))
                continue

            for inv in self.spec.invariants:
                if not inv.fn(inp, output):
                    failures.append((idx, f"invariant {inv.name} failed"))
            for prop in self.spec.properties:
                if not prop.fn(inp, output):
                    failures.append((idx, f"property {prop.name} failed"))

        return VerificationReport(
            passed=not failures,
            cases_run=len(inputs),
            failures=len(failures),
            details=failures,
        )
