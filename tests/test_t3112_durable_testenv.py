"""T3.1.2 — TestEnv with virtual clock (v1.0.0).

Covers:
  * ``Workflow.test_env(journal_path=None)`` returns a ``TestEnv``
  * ``env.now()`` returns a virtual timestamp starting at the
    epoch-like zero
  * ``await env.sleep(days=7)`` advances the virtual clock by
    seven days without real waiting
  * ``env.sleep(seconds=...)`` / ``minutes=...`` / ``hours=...``
    also work
  * Sleep total: chaining two sleeps adds up
  * Two TestEnvs have independent clocks (no shared state)
"""

from __future__ import annotations

import asyncio
import time

import pytest

from loopy.durable import TestEnv as _TestEnv
from loopy.durable import Workflow


class TestEnvVirtualClock:
    def test_test_env_factory_returns_testenv(self):
        env = Workflow.test_env()
        assert isinstance(env, _TestEnv)

    @pytest.mark.asyncio
    async def test_now_returns_starting_timestamp(self):
        env = Workflow.test_env()
        before = env.now()
        await asyncio.sleep(0.001)  # real time, not virtual
        after = env.now()
        # Virtual clock is independent of real time.
        assert before == after

    @pytest.mark.asyncio
    async def test_sleep_days_advances_virtual_clock(self):
        env = Workflow.test_env()
        start = env.now()
        await env.sleep(days=7)
        delta = env.now() - start
        # 7 days = 604800 seconds.
        assert delta == pytest.approx(7 * 86400, abs=1e-3)

    @pytest.mark.asyncio
    async def test_sleep_real_time_does_not_block(self):
        """A virtual sleep of 7 days must complete in well under a
        real second. (Confirms the clock is virtual, not real.)"""
        env = Workflow.test_env()
        start_real = time.monotonic()
        await env.sleep(days=7)
        elapsed = time.monotonic() - start_real
        assert elapsed < 1.0, f"Virtual sleep took {elapsed:.3f}s; expected <1s"

    @pytest.mark.asyncio
    async def test_sleep_hours_minutes_seconds_add(self):
        env = Workflow.test_env()
        start = env.now()
        await env.sleep(hours=2)
        await env.sleep(minutes=30)
        await env.sleep(seconds=45)
        delta = env.now() - start
        # 2h + 30m + 45s = 2*3600 + 30*60 + 45 = 9045 seconds.
        assert delta == pytest.approx(9045, abs=1e-3)

    @pytest.mark.asyncio
    async def test_two_envs_have_independent_clocks(self):
        a = Workflow.test_env()
        b = Workflow.test_env()
        await a.sleep(days=3)
        # b's clock is untouched.
        assert a.now() > b.now()
        assert b.now() == 0.0

    @pytest.mark.asyncio
    async def test_sleep_with_journal_path(self, tmp_path):
        """``test_env(journal_path=...)`` shares the journal with
        ``Workflow.run(journal_path=...)`` for end-to-end
        deterministic-replay tests."""
        journal_path = str(tmp_path / "testenv.json")
        env = Workflow.test_env(journal_path=journal_path)
        await env.sleep(days=2)
        # env writes its clock to the journal so the next run can
        # pick up the virtual timeline.
        import json
        from pathlib import Path

        data = json.loads(Path(journal_path).read_text())
        assert "clock" in data or "now" in data
