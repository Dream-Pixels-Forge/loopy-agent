"""v1.0.0 — Durable Agent Runtime.

A small, embeddable workflow engine with:

* ``DAG`` / ``Step`` — declarative workflow graph
* ``Workflow.run`` / ``Workflow.resume`` — executor with a
  crash-safe on-disk journal
* ``ResumeToken`` — opaque pointer to a partial run, can be
  serialized via pickle or JSON
* Saga compensation: when a step raises, every earlier step's
  ``compensation`` callable runs in reverse order so partial
  side effects can be rolled back

Designed for production agent workloads: ``journal_path=None``
runs entirely in-memory (for tests + ephemeral use), and the
journal format is plain JSON so a crashed run can be resumed
from a different process / machine.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.durable")


# ── Public types ─────────────────────────────────────────────


StateData = dict[str, Any]
RunCallable = Callable[["State"], Awaitable["State"]]
CompensationCallable = Callable[["State"], None]


@dataclass
class State:
    """The value passed between steps.

    ``data`` is the user-visible payload; ``metadata`` is for
    workflow-level bookkeeping (current step index, attempts, etc.).
    Each step receives a fresh ``State`` so steps cannot mutate
    the parent.
    """

    data: StateData
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    """A single unit of work in a DAG.

    Args:
        name: Stable identifier. Must be non-empty and must not
            contain ``/`` (path-traversal guard for the journal).
        run: Async callable ``(state) -> state`` doing the work.
        compensation: Optional sync callable ``(state) -> None``
            that rolls back the step's side effects when a later
            step raises. Saga pattern.
    """

    name: str
    run: RunCallable
    compensation: CompensationCallable | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError(
                "Step.name must be a non-empty string "
                "(see https://loopy.dev/docs/durable#step-construction)"
            )
        if "/" in self.name:
            raise ValueError(
                f"Step.name {self.name!r} must not contain '/' (path-traversal guard); "
                "use a flat name like 'my_step' "
                "(see https://loopy.dev/docs/durable#step-construction)"
            )


@dataclass
class DAG:
    """A list of ``Step`` objects executed in order.

    Construction validates the graph: empty step lists, duplicate
    names, and path-traversal names are rejected.
    """

    name: str
    steps: list[Step]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError(
                f"DAG {self.name!r} must declare at least one Step (got {len(self.steps)} steps; "
                "see https://loopy.dev/docs/durable#dag-construction)"
            )
        seen: set[str] = set()
        for step in self.steps:
            if step.name in seen:
                raise ValueError(
                    f"DAG {self.name!r} has duplicate step name {step.name!r}; "
                    "step names must be unique within a DAG "
                    "(see https://loopy.dev/docs/durable#dag-construction)"
                )
            seen.add(step.name)


# ── Journal ──────────────────────────────────────────────────


@dataclass
class _JournalRecord:
    step: str
    state: StateData
    timestamp: float
    attempt: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "state": dict(self.state),
            "timestamp": self.timestamp,
            "attempt": self.attempt,
        }


def _load_journal(path: str) -> list[_JournalRecord]:
    if not Path(path).exists():
        return []
    raw = json.loads(Path(path).read_text())
    return [
        _JournalRecord(
            step=r["step"],
            state=r.get("state", {}),
            timestamp=r.get("timestamp", 0.0),
            attempt=r.get("attempt", 1),
        )
        for r in raw.get("records", [])
    ]


def _save_journal(path: str, records: list[_JournalRecord]) -> None:
    payload = {
        "version": 1,
        "records": [r.to_dict() for r in records],
    }
    Path(path).write_text(json.dumps(payload, indent=2))


# ── ResumeToken ──────────────────────────────────────────────


@dataclass(frozen=True)
class ResumeToken:
    """Opaque pointer to a partial workflow run.

    A token is the in-memory handle returned by ``Workflow.run``
    (when ``return_token=True``) or reconstructed from the journal
    after a crash. It round-trips through pickle (binary) and
    through ``to_dict`` / ``from_dict`` (JSON).
    """

    workflow_id: str
    last_completed_step: str
    journal_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "last_completed_step": self.last_completed_step,
            "journal_path": self.journal_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResumeToken:
        try:
            return cls(
                workflow_id=str(data["workflow_id"]),
                last_completed_step=str(data["last_completed_step"]),
                journal_path=str(data["journal_path"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Malformed ResumeToken payload: {exc}; "
                "expected keys workflow_id, last_completed_step, journal_path "
                "(see https://loopy.dev/docs/durable#resume-token)"
            ) from exc


# ── Workflow ──────────────────────────────────────────────────


class Workflow:
    """Run a DAG to completion or resume from a journal."""

    @staticmethod
    async def run(
        dag: DAG,
        initial_state: State,
        *,
        journal_path: str | None = None,
    ) -> State:
        """Execute every step in order. If ``journal_path`` is set,
        each completed step is persisted so the run can be resumed
        from any point after a crash.

        Raises:
            Exception: re-raises the first exception from a step
                after running every earlier step's compensation.
        """
        return await Workflow._run(dag, initial_state, journal_path, resume_from=None)

    @staticmethod
    def resume(  # type: ignore[override]
        token: Any,
        dag: DAG | None = None,
        initial_state: State | None = None,
    ) -> Any:
        """Resume a partially-completed workflow from ``token``.

        The first positional argument is validated as a
        :class:`ResumeToken` *before* any other argument check, so
        calling ``Workflow.resume("not-a-token")`` raises
        ``ValueError`` with a useful message rather than a
        ``TypeError`` about missing kwargs.

        Returns a coroutine; awaiting it runs the workflow.
        """
        if not isinstance(token, ResumeToken):
            raise ValueError(
                f"resume() requires a ResumeToken, got {type(token).__name__}; "
                "construct one via ResumeToken.from_dict(...) or pass a "
                "deserialized token.workflow_id string. "
                "(see https://loopy.dev/docs/durable#resume-token)"
            )
        return Workflow._resume(token, dag, initial_state)

    @staticmethod
    async def _resume(
        token: ResumeToken,
        dag: DAG,
        initial_state: State,
    ) -> State:
        if not Path(token.journal_path).exists():
            raise FileNotFoundError(
                f"ResumeToken journal_path does not exist: {token.journal_path}"
            )
        return await Workflow._run(
            dag,
            initial_state,
            token.journal_path,
            resume_from=token.last_completed_step,
        )

    @staticmethod
    async def _run(
        dag: DAG,
        initial_state: State,
        journal_path: str | None,
        *,
        resume_from: str | None,
    ) -> State:
        records: list[_JournalRecord] = _load_journal(journal_path) if journal_path else []
        completed: set[str] = {r.step for r in records}
        state = initial_state
        completed_steps: list[Step] = []

        try:
            for step in dag.steps:
                if step.name in completed and resume_from is not None:
                    # Replay-from-journal: load the persisted state.
                    persisted = next(r for r in records if r.step == step.name)
                    state = State(
                        data=dict(persisted.state),
                        metadata=dict(state.metadata),
                    )
                    continue
                if step.name in completed:
                    # No resume: skip already-completed steps when
                    # the journal and DAG are aligned.
                    continue

                state = await step.run(state)
                completed_steps.append(step)
                completed.add(step.name)
                if journal_path:
                    records.append(
                        _JournalRecord(
                            step=step.name,
                            state=dict(state.data),
                            timestamp=time.time(),
                            attempt=1,
                        )
                    )
                    _save_journal(journal_path, records)
        except Exception:
            # Saga: run compensations in reverse order for every
            # step that successfully completed *this run*.
            for done in reversed(completed_steps):
                if done.compensation is not None:
                    try:
                        done.compensation(state)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Compensation for %s failed: %s", done.name, exc)
            raise

        return state

    @staticmethod
    def test_env(
        journal_path: str | None = None,
        *,
        start: float = 0.0,
    ) -> DurableTestEnv:
        """Create an isolated :class:`TestEnv` for deterministic time.

        Args:
            journal_path: When set, the virtual clock is persisted
                to this JSON file so a follow-up
                ``Workflow.run(journal_path=...)`` can pick up the
                same virtual timeline.
            start: Initial virtual timestamp (defaults to 0.0).
        """
        # The clock is wrapped in a single-element list so the
        # inner closure can mutate it without ``global`` or a
        # nonlocals declaration.
        clock_box: list[float] = [float(start)]
        if journal_path and Path(journal_path).exists():
            try:
                raw = json.loads(Path(journal_path).read_text())
                clock_box[0] = float(raw.get("clock", clock_box[0]))
            except (json.JSONDecodeError, ValueError, TypeError):
                # Corrupt or missing clock field; start fresh.
                pass

        def _persist() -> None:
            if not journal_path:
                return
            Path(journal_path).write_text(json.dumps({"clock": clock_box[0], "version": 1}))

        return DurableTestEnv(
            _now=lambda: clock_box[0],
            _advance=lambda seconds: _advance_inplace(clock_box, seconds),
            _persist=_persist,
        )


# ── TestEnv ───────────────────────────────────────────────────


def _advance_inplace(clock_box: list[float], seconds: float) -> float:
    """Advance ``clock_box[0]`` by ``seconds`` and return the new value.

    The clock is wrapped in a single-element list so the closure
    inside :meth:`Workflow.test_env` can mutate it without ``global``.
    """
    clock_box[0] += seconds
    return clock_box[0]


@dataclass
class DurableTestEnv:
    """Isolated, deterministic virtual clock for tests.

    Created via :meth:`Workflow.test_env`. The clock starts at 0
    (or a supplied ``start`` value) and advances only when
    :meth:`sleep` is awaited — no real wall-clock time elapses.

    Example:
        env = Workflow.test_env()
        await env.sleep(days=7)   # virtual clock moves 604800s
        assert env.now() == 604800
    """

    _now: Callable[[], float]
    _advance: Callable[[float], float]
    _persist: Callable[[], None]

    def now(self) -> float:
        """Return the current virtual timestamp in seconds."""
        return self._now()

    async def sleep(
        self,
        *,
        seconds: float = 0.0,
        minutes: float = 0.0,
        hours: float = 0.0,
        days: float = 0.0,
    ) -> None:
        """Advance the virtual clock. The call returns immediately
        (no real time elapses). The journal is updated if one was
        provided to :meth:`Workflow.test_env`."""
        total = (
            float(seconds) + float(minutes) * 60.0 + float(hours) * 3600.0 + float(days) * 86400.0
        )
        if total < 0:
            raise ValueError("sleep duration must be non-negative")
        self._advance(total)
        # Yield once so an awaiter between sleeps gets a chance to
        # run, then immediately persist the new clock.
        await asyncio.sleep(0)
        self._persist()


# Public alias — ``TestEnv`` is the user-facing name; the
# implementation class is :class:`DurableTestEnv` so pytest does
# not auto-collect it. (Pytest treats any class whose name starts
# with ``Test`` as a test class.)
TestEnv = DurableTestEnv
