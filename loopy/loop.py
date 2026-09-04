"""
Agentic Loop — Plan → Act → Observe → Reflect

The core execution cycle for autonomous AI agents.
Each iteration: plan next steps, execute actions, observe results, reflect on progress.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loopy.state import StateManager
else:
    StateManager = None  # type: ignore[assignment,misc]

logger = logging.getLogger("loopy.loop")


class StepStatus(str, Enum):
    PLANNING = "planning"
    ACTING = "acting"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class StepResult:
    """Result of a single loop iteration."""

    step: int
    status: StepStatus
    plan: str = ""
    action: str = ""
    observation: str = ""
    reflection: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class LoopConfig:
    """Configuration for the agentic loop."""

    max_steps: int = 10
    max_retries: int = 3
    stop_on_error: bool = False

    # Callbacks
    planner: Callable[[list[StepResult]], Awaitable[str]] | None = None
    actor: Callable[[str], Awaitable[str]] | None = None
    observer: Callable[[str], Awaitable[str]] | None = None
    reflector: Callable[[list[StepResult]], Awaitable[str]] | None = None

    # Optional: custom stop condition
    should_stop: Callable[[list[StepResult]], Awaitable[bool]] | None = None

    # v0.7.8 — Resume from checkpoint
    # Set to an integer step number to skip ahead, or leave None to start fresh.
    # When `state_manager` is provided, history is checkpointed after each step
    # and a `RunRecord` is appended so crashed runs can be resumed.
    resume_from: int | None = None
    state_manager: StateManager | None = None
    task: str = ""  # Label for RunRecord metadata

    # v0.9.0 — Compliance-as-Code policy engine. When set, the loop
    # evaluates the policies before each step and raises
    # ``PolicyViolation`` on a ``block`` decision. ``warn`` / ``info``
    # decisions are recorded but do not abort the loop. When
    # ``state_manager`` is configured, the per-step decisions are
    # persisted as ``metadata["policies"]`` on the saved LoopState.
    policy_engine: Any = None

    # v0.8.0 — Human-in-the-loop interrupts
    # Each list is a set of phase names that should pause BEFORE / AFTER
    # running, returning an :class:`Interrupt` to the caller for review.
    # Phase names: ``"plan"``, ``"actor"``, ``"observer"``, ``"reflector"``.
    interrupt_before: list[str] | None = None
    interrupt_after: list[str] | None = None

    def __post_init__(self) -> None:
        # Negative control: cannot configure interrupts on a zero-step loop.
        if self.max_steps < 1:
            raise ValueError(
                f"max_steps must be >= 1, got {self.max_steps}; "
                "set max_steps to at least 1 (or use Workflow.run directly) "
                "(see https://loopy.dev/docs/agent-loop#max-steps)"
            )
        # Negative control: cannot configure interrupts on a zero-step loop.
        if (self.interrupt_before or self.interrupt_after) and self.max_steps <= 0:
            raise ValueError(
                "interrupt_before / interrupt_after require max_steps >= 1; "
                "set max_steps to at least 1 or remove the interrupt config "
                "(see https://loopy.dev/docs/agent-loop#interrupts)"
            )
        for phase in self.interrupt_before or []:
            if phase not in {"plan", "actor", "observer", "reflector"}:
                raise ValueError(
                    f"interrupt_before: unknown phase {phase!r}; "
                    "must be one of plan/actor/observer/reflector "
                    "(see https://loopy.dev/docs/agent-loop#interrupts)"
                )
        for phase in self.interrupt_after or []:
            if phase not in {"plan", "actor", "observer", "reflector"}:
                raise ValueError(
                    f"interrupt_after: unknown phase {phase!r}; "
                    "must be one of plan/actor/observer/reflector "
                    "(see https://loopy.dev/docs/agent-loop#interrupts)"
                )


# v0.8.0 — Human-in-the-loop interrupt payload.
@dataclass
class Interrupt:
    """Returned by ``AgentLoop.run()`` when an interrupt fires.

    Carries the proposed action for human review and a ``decision``
    field that starts as ``None``. The caller sets ``decision`` to
    ``"approve"`` or ``"reject"`` and passes the Interrupt back to
    ``loop.run(input, resume_from=interrupt)`` to continue.
    """

    proposed_action: str
    decision: str | None = None  # "approve" | "reject" | None
    context: dict[str, Any] = field(default_factory=dict)
    phase: str = ""  # which phase raised the interrupt
    step: int = 0

    def __post_init__(self) -> None:
        if self.decision is not None and self.decision not in {"approve", "reject"}:
            raise ValueError(
                f"decision must be None, 'approve', or 'reject'; got {self.decision!r}"
            )


# v0.8.0 — Exception raised when an Interrupt is rejected.
class AgentLoopRejected(Exception):
    """Raised when ``resume_from=Interrupt(decision="reject")``.

    Carries the original proposal and context so a UI can render a
    re-prompt or surface the rejection to its caller.
    """

    def __init__(self, proposal: str, context: dict[str, Any] | None = None) -> None:
        self.proposal = proposal
        self.context = context or {}
        super().__init__(f"AgentLoop rejected proposal: {proposal}")

    def __str__(self) -> str:
        return f"AgentLoopRejected(proposal={self.proposal!r})"


class AgentLoop:
    """
    The agentic loop engine.

    Example:
        async def my_planner(history):
            return "I will search for information about Python."

        async def my_actor(plan):
            return "Searched the web and found 3 results."

        async def my_observer(action):
            return "Found relevant docs about Python asyncio."

        async def my_reflector(history):
            return "Good progress, but need more details on threading."

        loop = AgentLoop(LoopConfig(
            planner=my_planner,
            actor=my_actor,
            observer=my_observer,
            reflector=my_reflector,
        ))

        results = await loop.run()
    """

    def __init__(self, config: LoopConfig | None = None):
        self.config = config or LoopConfig()
        self.history: list[StepResult] = []
        # v0.8.0 — set by run() when resuming past a before-gate interrupt,
        # so _run_step can skip that single (step, phase) gate on re-entry.
        self._skip_before: tuple[int, str] | None = None

    async def run(
        self,
        initial_context: str = "",
        *,
        resume_from: Interrupt | None = None,
    ) -> Interrupt | list[StepResult]:
        """
        Execute the full agentic loop.

        v0.8.0 — HITL interrupts: if ``LoopConfig.interrupt_before`` or
        ``LoopConfig.interrupt_after`` matches the current phase, this
        method returns an :class:`Interrupt` instance instead of a list
        of ``StepResult``. To continue, pass the Interrupt back via
        ``resume_from=Interrupt(decision="approve")``.

        Returns:
            ``Interrupt`` if the loop paused for human review;
            ``list[StepResult]`` if the loop completed without pausing.

        Raises:
            AgentLoopRejected: when ``resume_from`` carries ``decision="reject"``.
        """
        # v0.8.0 — handle resume_from decision before entering the loop.
        if resume_from is not None:
            if resume_from.decision is None:
                raise ValueError(
                    "resume_from must carry a decision ('approve' or 'reject'); "
                    "received Interrupt with decision=None"
                )
            if resume_from.decision == "reject":
                raise AgentLoopRejected(
                    proposal=resume_from.proposed_action,
                    context=resume_from.context,
                )
            # decision == "approve" — re-enter at the same step so the
            # after-gate (if any) still fires for the same step. The
            # before-gate we just approved is suppressed via _skip_before.
            self._skip_before = (resume_from.step, resume_from.phase)
            start_step = max(1, resume_from.step)
        elif self.config.resume_from is not None:
            start_step = max(1, self.config.resume_from + 1)
            self._skip_before = None
            logger.info("Resuming loop at step %d", start_step)
        else:
            start_step = 1
            self._skip_before = None

        self.history = []

        if initial_context:
            self.history.append(
                StepResult(
                    step=0,
                    status=StepStatus.OBSERVING,
                    observation=initial_context,
                )
            )

        # legacy compatibility: keep this no-op assignment for any
        # downstream consumer that read start_step here before the
        # v0.8.0 restructure (see ``test_t1001_characterization.py``).
        _ = start_step

        try:
            for step_num in range(start_step, self.config.max_steps + 1):
                # v0.9.0 — Compliance-as-Code: evaluate policies before
                # the step runs. ``gate()`` raises on ``block`` and
                # returns the full list of decisions otherwise. We
                # record the raw context (audit fidelity) so
                # post-hoc scrubbing is the storage layer's job.
                if self.config.policy_engine is not None:
                    step_decisions = self.config.policy_engine.gate(
                        {"step": step_num, "retries": step_num - 1}
                    )
                    if step_decisions and self.config.state_manager is not None:
                        try:
                            self._record_policy_decisions(step_num, step_decisions)
                        except Exception as e:  # noqa: BLE001
                            logger.warning(
                                "Failed to record policy decisions at step %d: %s",
                                step_num,
                                e,
                            )

                result = await self._run_step(step_num)
                self.history.append(result)

                # v0.7.8 — checkpoint after every step when configured
                self._checkpoint(result)

                if result.status == StepStatus.FAILED and self.config.stop_on_error:
                    logger.error("Loop stopped at step %d: %s", step_num, result.error)
                    break

                # Check custom stop condition
                if self.config.should_stop:
                    try:
                        if await self.config.should_stop(self.history):
                            logger.info("Stop condition met at step %d", step_num)
                            break
                    except Exception as e:
                        logger.warning("Stop condition check failed: %s", e)

                # Default stop: all callbacks are None (no-op loop)
                if not any(
                    [
                        self.config.planner,
                        self.config.actor,
                        self.config.observer,
                        self.config.reflector,
                    ]
                ):
                    logger.info("No callbacks configured, stopping loop")
                    break
        except _InterruptedRun as ir:
            # v0.8.0 — a phase triggered an Interrupt. Persist it via
            # the configured state manager (best-effort) so a crash+resume
            # can replay, then return it to the caller for review.
            self._persist_interrupt(ir.interrupt)
            return ir.interrupt

        return self.history

    def _record_policy_decisions(self, step_num: int, decisions: list[Any]) -> None:
        """v0.9.0 — Append raw policy decisions to LoopState.metadata
        so a crash+resume can replay the audit trail.

        The decisions are stored verbatim (no redaction) so the
        audit log has the raw facts; storage-side scrubbing is the
        caller's responsibility when reading the LoopState back out.
        """
        if not self.config.state_manager:
            return

        from loopy.state import RunOutcome, RunRecord

        sm = self.config.state_manager
        state = sm.load()
        existing = list(state.metadata.get("policies", []))
        existing.append(
            {
                "step": step_num,
                "decisions": [d.to_dict() for d in decisions],
            }
        )
        state.metadata["policies"] = existing

        # Also surface one RunRecord per decision so compliance
        # dashboards that read RunRecords (without parsing metadata)
        # see the audit trail.
        for d in decisions:
            state.add_record(
                RunRecord(
                    task=self.config.task or f"policy_step_{step_num}",
                    outcome=RunOutcome.SUCCESS,
                    tokens_used=0,
                    duration_ms=0,
                    timestamp=datetime.now().isoformat(),
                    metadata={
                        "kind": "policy_decision",
                        "step": step_num,
                        "policy_name": d.policy_name,
                        "verdict": d.verdict,
                    },
                )
            )

        if len(state.history) > 100:
            state.history = state.history[-100:]

        sm.save(state)

    def _checkpoint(self, result: StepResult) -> None:
        """v0.7.8 — Persist a step result to the configured StateManager.

        Records a RunRecord per step and updates LoopState.attempts so a
        subsequent run with ``resume_from`` can pick up where this one left off.
        Failures are logged but do not interrupt the loop — checkpointing is
        best-effort observability, not a transactional write-ahead log.
        """
        if not self.config.state_manager:
            return

        try:
            from loopy.state import RunOutcome, RunRecord

            state_manager = self.config.state_manager
            state = state_manager.load()
            state.current_task = self.config.task or None
            state.attempts = result.step

            outcome = (
                RunOutcome.SUCCESS if result.status == StepStatus.COMPLETE else RunOutcome.FAILURE
            )
            state.add_record(
                RunRecord(
                    task=self.config.task or f"step_{result.step}",
                    outcome=outcome,
                    tokens_used=0,
                    duration_ms=0,
                    timestamp=datetime.now().isoformat(),
                    metadata={
                        "step": result.step,
                        "plan": result.plan[:200],
                        "action": result.action[:200],
                        "observation": result.observation[:200],
                    },
                )
            )

            # Cap stored RunRecords to avoid unbounded growth (matches the
            # DecisionTracker FIFO bound from v0.7.6).
            if len(state.history) > 100:
                state.history = state.history[-100:]

            state_manager.save(state)
        except Exception as e:
            logger.warning("Checkpoint failed at step %d: %s", result.step, e)

    def _persist_interrupt(self, interrupt: Interrupt) -> None:
        """v0.8.0 — record an interrupt on the configured state manager.

        Best-effort: failures are logged but do not change the return
        value of :meth:`run`. The interrupt is appended to
        ``LoopState.metadata["interrupts"]`` and a paired ``RunRecord``
        is added to ``LoopState.history`` so a subsequent resume can see
        what was paused.
        """
        if not self.config.state_manager:
            return

        try:
            from loopy.state import RunOutcome, RunRecord

            state_manager = self.config.state_manager
            state = state_manager.load()
            state.current_task = self.config.task or None
            state.attempts = interrupt.step

            state.add_record(
                RunRecord(
                    task=self.config.task or f"interrupt_step_{interrupt.step}",
                    outcome=RunOutcome.INTERRUPTED,
                    tokens_used=0,
                    duration_ms=0,
                    timestamp=datetime.now().isoformat(),
                    metadata={
                        "kind": "interrupt",
                        "phase": interrupt.phase,
                        "step": interrupt.step,
                        "proposed_action": interrupt.proposed_action,
                    },
                )
            )

            interrupts = list(state.metadata.get("interrupts", []))
            interrupts.append(
                {
                    "phase": interrupt.phase,
                    "step": interrupt.step,
                    "proposed_action": interrupt.proposed_action,
                    "context": interrupt.context,
                }
            )
            state.metadata["interrupts"] = interrupts

            if len(state.history) > 100:
                state.history = state.history[-100:]

            state_manager.save(state)
        except Exception as e:
            logger.warning("Persist interrupt failed: %s", e)

    async def _run_step(self, step_num: int) -> StepResult:
        """Execute a single iteration of the loop."""
        result = StepResult(step=step_num, status=StepStatus.PLANNING)

        # v0.8.0 — Interrupt gates. Each phase can be paused BEFORE the
        # phase runs (``interrupt_before``) or AFTER (``interrupt_after``)
        # by raising ``_InterruptedRun`` which the public ``run()`` catches
        # and converts to an :class:`Interrupt` return value.
        ib = self.config.interrupt_before or []
        ia = self.config.interrupt_after or []
        # v0.8.0 — clear single-shot skip once we enter the target step.
        if self._skip_before is not None and self._skip_before[0] != step_num:
            self._skip_before = None

        async def _pause_before(phase: str, proposed: str, ctx: dict[str, Any]) -> None:
            """Raise ``_InterruptedRun`` if this phase is configured to pause BEFORE running."""
            if phase in ib and self._skip_before != (step_num, phase):
                raise _InterruptedRun(
                    Interrupt(
                        proposed_action=proposed,
                        context={**ctx, "when": "before"},
                        phase=phase,
                        step=step_num,
                    )
                )

        async def _pause_after(phase: str, proposed: str, ctx: dict[str, Any]) -> None:
            """Raise ``_InterruptedRun`` if this phase is configured to pause AFTER running."""
            if phase in ia:
                raise _InterruptedRun(
                    Interrupt(
                        proposed_action=proposed,
                        context={**ctx, "when": "after"},
                        phase=phase,
                        step=step_num,
                    )
                )

        try:
            # PLAN
            if self.config.planner:
                await _pause_before(
                    "plan",
                    proposed=f"run plan step {step_num}",
                    ctx={"step": step_num, "phase": "plan"},
                )
                result.plan = await self.config.planner(self.history)
                await _pause_after(
                    "plan",
                    proposed=f"plan step {step_num} produced: {result.plan[:80]}",
                    ctx={"step": step_num, "phase": "plan", "plan": result.plan},
                )
                logger.debug("Step %d plan: %s...", step_num, result.plan[:100])

            # ACT
            result.status = StepStatus.ACTING
            if self.config.actor:
                await _pause_before(
                    "actor",
                    proposed=f"run actor step {step_num} with plan: {result.plan[:80]}",
                    ctx={"step": step_num, "phase": "actor", "plan": result.plan},
                )
                result.action = await self.config.actor(result.plan)
                await _pause_after(
                    "actor",
                    proposed=f"actor step {step_num} produced: {result.action[:80]}",
                    ctx={
                        "step": step_num,
                        "phase": "actor",
                        "plan": result.plan,
                        "action": result.action,
                    },
                )
                logger.debug("Step %d action: %s...", step_num, result.action[:100])

            # OBSERVE
            result.status = StepStatus.OBSERVING
            if self.config.observer:
                await _pause_before(
                    "observer",
                    proposed=f"observe action result: {result.action[:80]}",
                    ctx={"step": step_num, "phase": "observer", "action": result.action},
                )
                result.observation = await self.config.observer(result.action)
                await _pause_after(
                    "observer",
                    proposed=f"observer step {step_num} produced: {result.observation[:80]}",
                    ctx={
                        "step": step_num,
                        "phase": "observer",
                        "action": result.action,
                        "observation": result.observation,
                    },
                )
                logger.debug("Step %d observation: %s...", step_num, result.observation[:100])

            # REFLECT
            result.status = StepStatus.REFLECTING
            if self.config.reflector:
                await _pause_before(
                    "reflector",
                    proposed=f"reflect on history ({len(self.history)} entries)",
                    ctx={"step": step_num, "phase": "reflector"},
                )
                result.reflection = await self.config.reflector(self.history)
                await _pause_after(
                    "reflector",
                    proposed=f"reflector step {step_num} produced: {result.reflection[:80]}",
                    ctx={
                        "step": step_num,
                        "phase": "reflector",
                        "reflection": result.reflection,
                    },
                )
                logger.debug("Step %d reflection: %s...", step_num, result.reflection[:100])

            result.status = StepStatus.COMPLETE

        except _InterruptedRun as ir:
            # Carry the interrupt up to the public run() entry point.
            raise ir
        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = str(e)
            logger.error("Step %d failed: %s", step_num, e)

            if self.config.stop_on_error:
                raise

        return result


class _InterruptedRun(Exception):
    """v0.8.0 — internal sentinel: ``_run_step`` raised to surface an Interrupt.

    Caught and converted to a return value by the public ``run()`` method.
    """

    def __init__(self, interrupt: Interrupt) -> None:
        super().__init__(f"interrupted at {interrupt.phase!r} step {interrupt.step}")
        self.interrupt = interrupt
