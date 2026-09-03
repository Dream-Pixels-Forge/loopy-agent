"""v0.9.0 — Compliance-as-Code policy engine.

Composable declarative policies that evaluate against a context
dict and emit :class:`PolicyDecision` records. Designed to be
applied at the boundaries of the SDK (Gateway.chat, AgentLoop.step)
so the user can branch, gate, or audit before a side effect.

Public surface:

  * :class:`Policy` — named bundle of conditions + a severity
  * :class:`Condition` — single (kind, value) predicate
  * :class:`PolicyDecision` — emitted when a policy fires
  * :class:`PolicyViolation` — raised by ``PolicyEngine.gate``
  * :class:`PolicyEngine` — evaluator with an optional
    ``audit_sink`` callback that receives every decision

The engine is intentionally pure (no I/O) so it stays fast
(5 policies evaluate in <1ms) and easy to test.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger("loopy.policies")

# ── Public types ──────────────────────────────────────────────


Severity = Literal["info", "warn", "block"]

ConditionKind = Literal[
    "max_retries",
    "max_cost_usd",
    "pii_in_input",
    "rate_limit",
]

_KNOWN_CONDITION_KINDS: frozenset[str] = frozenset(
    {"max_retries", "max_cost_usd", "pii_in_input", "rate_limit"}
)
_KNOWN_SEVERITIES: frozenset[str] = frozenset({"info", "warn", "block"})


@dataclass(frozen=True)
class Condition:
    """A single (kind, value) predicate.

    Supported kinds:

    * ``max_retries`` — fires when ``context["retries"] > value``
    * ``max_cost_usd`` — fires when ``context["cost_usd"] > value``
    * ``pii_in_input`` — fires when ``context["pii_detected"] is True``
    * ``rate_limit`` — fires when ``context["rps"] > value``
    """

    kind: str
    value: Any

    def __post_init__(self) -> None:
        if self.kind not in _KNOWN_CONDITION_KINDS:
            raise ValueError(
                f"Unknown condition kind {self.kind!r}; "
                f"must be one of {sorted(_KNOWN_CONDITION_KINDS)}"
            )


@dataclass(frozen=True)
class Policy:
    """A named bundle of conditions evaluated as a single decision."""

    name: str
    conditions: list[Condition]
    severity: Severity = "warn"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Policy.name must be a non-empty string")
        if not self.conditions:
            raise ValueError(f"Policy {self.name!r} must declare at least one Condition")
        if self.severity not in _KNOWN_SEVERITIES:
            raise ValueError(
                f"Policy {self.name!r} severity {self.severity!r} is not allowed; "
                f"must be one of {sorted(_KNOWN_SEVERITIES)}"
            )


@dataclass(frozen=True)
class PolicyDecision:
    """The result of a fired :class:`Policy`."""

    policy_name: str
    verdict: Severity
    context: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_name": self.policy_name,
            "verdict": self.verdict,
            "context": dict(self.context),
            "timestamp": self.timestamp,
        }


class PolicyViolation(Exception):
    """Raised by :meth:`PolicyEngine.gate` when a ``block`` policy fires."""

    def __init__(self, policy_name: str, context: dict[str, Any]) -> None:
        self.policy_name = policy_name
        self.context = context
        super().__init__(f"Policy {policy_name!r} blocked the operation")

    def __str__(self) -> str:
        return f"PolicyViolation(policy={self.policy_name!r})"


AuditSink = Callable[[PolicyDecision], None]


# ── Engine ────────────────────────────────────────────────────


class PolicyEngine:
    """Evaluate a list of :class:`Policy` against a context dict.

    Args:
        policies: the policies to evaluate. Order is preserved.
        audit_sink: optional callback that receives every
            :class:`PolicyDecision` emitted (block + warn + info).
    """

    def __init__(
        self,
        policies: list[Policy],
        *,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.policies = list(policies)
        self.audit_sink = audit_sink

    def evaluate(self, context: dict[str, Any]) -> list[PolicyDecision]:
        """Run every policy against ``context``.

        Returns the list of decisions (one per fired policy). The
        list is empty when nothing fires. The ``audit_sink`` is
        called once per decision before this method returns.
        """
        decisions: list[PolicyDecision] = []
        for policy in self.policies:
            if self._matches(policy, context):
                decision = PolicyDecision(
                    policy_name=policy.name,
                    verdict=policy.severity,
                    context=dict(context),
                )
                decisions.append(decision)
                if self.audit_sink is not None:
                    try:
                        self.audit_sink(decision)
                    except Exception as exc:  # noqa: BLE001 — audit must not break evaluation
                        logger.warning("audit_sink raised for %s: %s", policy.name, exc)
        return decisions

    def gate(self, context: dict[str, Any]) -> list[PolicyDecision]:
        """Evaluate and raise :class:`PolicyViolation` on the first
        ``block`` decision.

        Returns the list of all decisions (block + warn + info) for
        callers that want to log or surface non-blocking verdicts.
        """
        decisions = self.evaluate(context)
        for d in decisions:
            if d.verdict == "block":
                raise PolicyViolation(d.policy_name, d.context)
        return decisions

    # ── Predicates ────────────────────────────────────────────

    @staticmethod
    def _matches(policy: Policy, context: dict[str, Any]) -> bool:
        return all(_condition_matches(cond, context) for cond in policy.conditions)


def _condition_matches(cond: Condition, context: dict[str, Any]) -> bool:
    if cond.kind == "max_retries":
        return int(context.get("retries", 0)) > int(cond.value)
    if cond.kind == "max_cost_usd":
        return float(context.get("cost_usd", 0.0)) > float(cond.value)
    if cond.kind == "pii_in_input":
        return bool(context.get("pii_detected", False)) and bool(cond.value)
    if cond.kind == "rate_limit":
        return float(context.get("rps", 0.0)) > float(cond.value)
    return False
