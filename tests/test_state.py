"""Tests for loopy.state — Durable Loop State Management."""

import os
import tempfile

from loopy.state import (
    LoopState,
    RunOutcome,
    RunRecord,
    StateManager,
)


class TestRunOutcome:
    def test_outcome_enum(self):
        """Test run outcome enum values."""
        assert RunOutcome.SUCCESS.value == "success"
        assert RunOutcome.FAILURE.value == "failure"
        assert RunOutcome.ESCALATED.value == "escalated"


class TestRunRecord:
    def test_run_record_creation(self):
        """Test run record creation."""
        record = RunRecord(
            task="Fix CI",
            outcome=RunOutcome.SUCCESS,
            tokens_used=500,
            duration_ms=1200.5,
        )
        assert record.task == "Fix CI"
        assert record.outcome == RunOutcome.SUCCESS
        assert record.tokens_used == 500
        assert record.timestamp is not None

    def test_run_record_to_dict(self):
        """Test run record serialization."""
        record = RunRecord(
            task="Fix CI",
            outcome=RunOutcome.SUCCESS,
            tokens_used=500,
            duration_ms=1200.5,
        )
        d = record.to_dict()
        assert d["task"] == "Fix CI"
        assert d["outcome"] == "success"
        assert d["tokens_used"] == 500

    def test_run_record_from_dict(self):
        """Test run record deserialization."""
        d = {
            "task": "Fix CI",
            "outcome": "failure",
            "tokens_used": 300,
            "duration_ms": 800.0,
            "timestamp": "2025-07-24T12:00:00",
        }
        record = RunRecord.from_dict(d)
        assert record.task == "Fix CI"
        assert record.outcome == RunOutcome.FAILURE


class TestLoopState:
    def test_state_creation(self):
        """Test state creation with defaults."""
        state = LoopState()
        assert state.current_task is None
        assert state.attempts == 0
        assert len(state.history) == 0

    def test_state_add_record(self):
        """Test adding run records."""
        state = LoopState()
        record = RunRecord(
            task="Fix CI",
            outcome=RunOutcome.SUCCESS,
            tokens_used=500,
            duration_ms=1000.0,
        )
        state.add_record(record)
        assert len(state.history) == 1
        assert state.history[0].task == "Fix CI"

    def test_state_total_tokens(self):
        """Test total token calculation."""
        state = LoopState()
        state.add_record(
            RunRecord(task="a", outcome=RunOutcome.SUCCESS, tokens_used=100, duration_ms=100)
        )
        state.add_record(
            RunRecord(task="b", outcome=RunOutcome.FAILURE, tokens_used=200, duration_ms=100)
        )
        assert state.total_tokens == 300

    def test_state_to_dict(self):
        """Test state serialization."""
        state = LoopState()
        state.current_task = "Fix bug"
        state.attempts = 3
        d = state.to_dict()
        assert d["current_task"] == "Fix bug"
        assert d["attempts"] == 3

    def test_state_from_dict(self):
        """Test state deserialization."""
        d = {
            "current_task": "Fix bug",
            "attempts": 2,
            "history": [],
        }
        state = LoopState.from_dict(d)
        assert state.current_task == "Fix bug"
        assert state.attempts == 2


class TestStateManager:
    def test_manager_creation(self):
        """Test manager creation."""
        manager = StateManager()
        assert manager is not None

    def test_save_and_load(self):
        """Test save and load cycle."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            manager = StateManager(path)
            state = LoopState()
            state.current_task = "Test task"
            state.attempts = 5

            manager.save(state)
            loaded = manager.load()

            assert loaded.current_task == "Test task"
            assert loaded.attempts == 5
        finally:
            os.unlink(path)

    def test_load_nonexistent(self):
        """Test loading nonexistent file returns empty state."""
        manager = StateManager("/tmp/nonexistent_state.json")
        state = manager.load()
        assert state.current_task is None
        assert state.attempts == 0

    def test_prune_old_records(self):
        """Test pruning old records."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            manager = StateManager(path)
            state = LoopState()

            # Add records with old timestamps
            old_record = RunRecord(
                task="old", outcome=RunOutcome.SUCCESS, tokens_used=10, duration_ms=100
            )
            old_record.timestamp = "2020-01-01T00:00:00"
            state.add_record(old_record)

            new_record = RunRecord(
                task="new", outcome=RunOutcome.SUCCESS, tokens_used=10, duration_ms=100
            )
            state.add_record(new_record)

            manager.save(state)
            pruned = manager.prune(max_age_days=30)

            assert pruned == 1
            loaded = manager.load()
            assert len(loaded.history) == 1
            assert loaded.history[0].task == "new"
        finally:
            os.unlink(path)
