"""
State — Durable Loop State Management.

Persistent state for agent loops across sessions.
Inspired by loop-engineering's STATE.md files.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.state")


class RunOutcome(str, Enum):
    """Outcome of a loop run."""
    SUCCESS = "success"
    FAILURE = "failure"
    ESCALATED = "escalated"


@dataclass
class RunRecord:
    """Record of a single loop run."""
    task: str
    outcome: RunOutcome
    tokens_used: int = 0
    duration_ms: float = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "outcome": self.outcome.value,
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        return cls(
            task=data["task"],
            outcome=RunOutcome(data["outcome"]),
            tokens_used=data.get("tokens_used", 0),
            duration_ms=data.get("duration_ms", 0),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class LoopState:
    """Durable state for an agent loop."""
    current_task: str | None = None
    attempts: int = 0
    max_attempts: int = 5
    history: list[RunRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(r.tokens_used for r in self.history)

    @property
    def last_run(self) -> RunRecord | None:
        return self.history[-1] if self.history else None

    def add_record(self, record: RunRecord) -> None:
        self.history.append(record)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_task": self.current_task,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "history": [r.to_dict() for r in self.history],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopState:
        return cls(
            current_task=data.get("current_task"),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 5),
            history=[RunRecord.from_dict(r) for r in data.get("history", [])],
            metadata=data.get("metadata", {}),
        )


class StateManager:
    """
    Read/write loop state to disk.

    Example:
        manager = StateManager("./loop-state.json")
        state = manager.load()
        state.current_task = "Fix CI"
        manager.save(state)
    """

    def __init__(self, path: str = "./loop-state.json"):
        self.path = Path(path)

    def load(self) -> LoopState:
        """Load state from disk, or return empty state."""
        if not self.path.exists():
            return LoopState()

        try:
            data = json.loads(self.path.read_text())
            return LoopState.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
            return LoopState()

    def save(self, state: LoopState) -> None:
        """Save state to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state.to_dict(), indent=2))

    def prune(self, max_age_days: int = 30) -> int:
        """
        Remove records older than max_age_days.

        Returns:
            Number of records pruned
        """
        state = self.load()
        cutoff = datetime.now() - timedelta(days=max_age_days)
        cutoff_str = cutoff.isoformat()

        original_count = len(state.history)
        state.history = [
            r for r in state.history
            if r.timestamp >= cutoff_str
        ]
        pruned = original_count - len(state.history)

        if pruned > 0:
            self.save(state)
            logger.info(f"Pruned {pruned} old records")

        return pruned
