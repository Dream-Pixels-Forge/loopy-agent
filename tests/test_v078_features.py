"""Tests for v0.7.8 features.

Four small additions that complete existing modules rather than introducing
new ones:

  1. ``LoopConfig`` resume + checkpoint via ``StateManager``  (``loop.py``)
  2. ``SkillRegistry.match_ranked`` / ``match_one``  (``skills.py``)
  3. ``LLMCache.aget`` / ``aset``  (``cache.py``)
  4. ``EvalReport`` JSON I/O  (``evals.py``)
"""

from __future__ import annotations

import pytest

from loopy.cache import LLMCache
from loopy.evals import EvalCase, EvalReport, EvalResult, Verdict
from loopy.loop import AgentLoop, LoopConfig
from loopy.skills import Skill, SkillRegistry
from loopy.state import StateManager

# ---------------------------------------------------------------------------
# Feature 1 — AgentLoop resume + checkpoint
# ---------------------------------------------------------------------------


class TestLoopResume:
    @pytest.mark.asyncio
    async def test_resume_from_skips_earlier_steps(self, tmp_path):
        """Setting resume_from=N should make the loop start at step N+1."""

        planner_calls: list[int] = []

        async def planner(history):
            planner_calls.append(len(history))
            return "plan"

        async def actor(plan):
            return "act"

        async def observer(action):
            return "obs"

        async def reflector(history):
            return "ref"

        loop = AgentLoop(
            LoopConfig(
                planner=planner,
                actor=actor,
                observer=observer,
                reflector=reflector,
                max_steps=5,
                resume_from=3,
            )
        )

        history = await loop.run()

        # Loop should produce steps 4 and 5 only (resume from step 3)
        assert [r.step for r in history] == [4, 5]
        # Planner should have been invoked exactly twice (steps 4 and 5)
        assert len(planner_calls) == 2

    @pytest.mark.asyncio
    async def test_resume_from_none_starts_at_one(self):
        async def noop(_=None):
            return ""

        loop = AgentLoop(
            LoopConfig(
                planner=noop,
                actor=noop,
                observer=noop,
                reflector=noop,
                max_steps=3,
            )
        )
        history = await loop.run()
        assert [r.step for r in history] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_checkpoint_writes_run_record_per_step(self, tmp_path):
        """Each completed step should produce a ``RunRecord`` on disk."""

        async def noop(_=None):
            return ""

        sm = StateManager(str(tmp_path / "state.json"))
        loop = AgentLoop(
            LoopConfig(
                planner=noop,
                actor=noop,
                observer=noop,
                reflector=noop,
                max_steps=3,
                state_manager=sm,
                task="unit-test",
            )
        )

        await loop.run()

        state = sm.load()
        # 3 successful steps => 3 records, attempts == 3
        assert len(state.history) == 3
        assert state.attempts == 3
        assert state.current_task == "unit-test"
        # All steps recorded as SUCCESS
        assert all(r.outcome.value == "success" for r in state.history)

    @pytest.mark.asyncio
    async def test_checkpoint_records_failure_outcome(self, tmp_path):
        async def ok(_=None):
            return "x"

        async def boom(_):
            raise RuntimeError("nope")

        sm = StateManager(str(tmp_path / "state.json"))
        loop = AgentLoop(
            LoopConfig(
                planner=ok,
                actor=boom,
                observer=ok,
                reflector=ok,
                max_steps=2,
                stop_on_error=False,  # keep checkpointing after the failure
                state_manager=sm,
            )
        )

        await loop.run()

        state = sm.load()
        assert state.history, "expected at least one RunRecord"
        # Each step records a RunRecord with step number metadata
        steps = [r.metadata["step"] for r in state.history]
        assert steps == [1, 2]
        # Both steps failed (actor raised every time)
        assert all(r.outcome.value == "failure" for r in state.history)
        # Plan metadata is captured (planner succeeded before actor raised)
        assert state.history[0].metadata["plan"] == "x"

    @pytest.mark.asyncio
    async def test_checkpoint_bounded_at_100(self, tmp_path):
        async def noop(_=None):
            return ""

        sm = StateManager(str(tmp_path / "state.json"))
        loop = AgentLoop(
            LoopConfig(
                planner=noop,
                actor=noop,
                observer=noop,
                reflector=noop,
                max_steps=120,  # > 100 so we exceed the cap
                state_manager=sm,
            )
        )

        await loop.run()

        state = sm.load()
        assert len(state.history) <= 100


# ---------------------------------------------------------------------------
# Feature 2 — SkillRegistry.match_ranked / match_one
# ---------------------------------------------------------------------------


class TestSkillRanking:
    def test_score_zero_when_no_triggers(self):
        skill = Skill(name="x", description="x", instructions="x", triggers=[])
        assert skill.score("anything") == 0.0

    def test_score_returns_float_in_range(self):
        skill = Skill(
            name="ci-triage",
            description="triage ci",
            instructions="x",
            triggers=["ci failed", "flaky tests"],
        )
        score = skill.score("My CI failed overnight")
        assert 0.0 < score <= 1.0

    def test_match_ranked_orders_by_score(self):
        reg = SkillRegistry()
        strong = Skill(
            name="strong",
            description="x",
            instructions="x",
            triggers=["ci failed", "tests failing"],
        )
        weak = Skill(
            name="weak",
            description="x",
            instructions="x",
            triggers=["unrelated keyword"],
        )
        reg.add(strong)
        reg.add(weak)

        ranked = reg.match_ranked("ci failed on tests")
        names = [s.name for s, _ in ranked]
        assert names[0] == "strong"
        assert ranked[0][1] > 0.0

    def test_match_ranked_min_score_filter(self):
        reg = SkillRegistry()
        reg.add(Skill(name="s", description="x", instructions="x", triggers=["alpha"]))
        assert reg.match_ranked("nothing here", min_score=0.5) == []

    def test_match_ranked_limit(self):
        reg = SkillRegistry()
        for n in "abcdef":
            reg.add(Skill(name=n, description=n, instructions="x", triggers=[n]))
        ranked = reg.match_ranked("a b c d e f", limit=2)
        assert len(ranked) == 2

    def test_match_one_returns_best(self):
        reg = SkillRegistry()
        reg.add(Skill(name="other", description="x", instructions="x", triggers=["car"]))
        reg.add(
            Skill(name="python", description="x", instructions="x", triggers=["python", "snake"])
        )

        best = reg.match_one("python snake")
        assert best is not None
        assert best.name == "python"

    def test_match_one_returns_none_when_below_min(self):
        reg = SkillRegistry()
        reg.add(Skill(name="x", description="x", instructions="x", triggers=["alpha"]))
        assert reg.match_one("nothing matches", min_score=0.5) is None

    def test_matches_uses_score_for_backward_compat(self):
        """`matches` must remain a boolean API."""
        skill = Skill(name="x", description="x", instructions="x", triggers=["hello"])
        assert skill.matches("say hello world") is True
        assert skill.matches("nothing here") is False


# ---------------------------------------------------------------------------
# Feature 3 — LLMCache.aget / aset
# ---------------------------------------------------------------------------


class TestAsyncCache:
    @pytest.mark.asyncio
    async def test_aget_miss_returns_none(self):
        cache = LLMCache()
        assert await cache.aget("nope", model="gpt-4") is None

    @pytest.mark.asyncio
    async def test_aset_then_aget_hit(self):
        cache = LLMCache()
        await cache.aset("hello", "world", model="gpt-4", tokens=10)
        result = await cache.aget("hello", model="gpt-4")
        assert result == "world"

    @pytest.mark.asyncio
    async def test_aset_persists_to_disk_async(self, tmp_path):
        """aset with persist_path must write via to_thread (no event-loop block)."""
        path = tmp_path / "cache.json"
        cache = LLMCache(persist_path=str(path))
        await cache.aset("k", "v", model="gpt-4")
        # File should exist after the await
        assert path.exists()
        loaded = LLMCache(persist_path=str(path))
        assert loaded.get("k", model="gpt-4") == "v"

    @pytest.mark.asyncio
    async def test_aset_evicts_when_full(self):
        cache = LLMCache(max_size=2)
        await cache.aset("a", "1", model="m")
        await cache.aset("b", "2", model="m")
        await cache.aset("c", "3", model="m")  # forces eviction
        # 'a' is the LRU now; 'b' and 'c' remain
        assert await cache.aget("a", model="m") is None
        assert await cache.aget("b", model="m") == "2"
        assert await cache.aget("c", model="m") == "3"

    @pytest.mark.asyncio
    async def test_aset_records_tokens_in_stats(self):
        cache = LLMCache()
        await cache.aset("k", "v", model="m", tokens=50)
        await cache.aget("k", model="m")
        stats = cache.stats()
        assert stats.hits == 1
        assert stats.total_saved_tokens == 50


# ---------------------------------------------------------------------------
# Feature 4 — EvalReport JSON I/O
# ---------------------------------------------------------------------------


def _make_report() -> EvalReport:
    case = EvalCase(
        name="addition",
        input_text="What is 2+2?",
        expected_output="4",
        criteria=["correct", "concise"],
        tags=["math"],
        threshold=0.7,
    )
    result = EvalResult(
        case=case,
        actual_output="4",
        verdict=Verdict.PASS,
        score=1.0,
        reasoning="exact match",
        criteria_scores={"correct": 1.0, "concise": 0.9},
    )
    return EvalReport(suite_name="math_basic", results=[result])


class TestEvalReportJSON:
    def test_to_dict_includes_suite_and_results(self):
        report = _make_report()
        d = report.to_dict()
        assert d["suite_name"] == "math_basic"
        assert len(d["results"]) == 1
        assert d["results"][0]["verdict"] == "pass"

    def test_to_json_round_trip(self):
        report = _make_report()
        js = report.to_json()
        assert isinstance(js, str)
        restored = EvalReport.from_json(js)
        assert restored.suite_name == "math_basic"
        assert len(restored.results) == 1
        assert restored.results[0].verdict == Verdict.PASS
        assert restored.results[0].score == 1.0
        assert restored.results[0].case.name == "addition"
        assert restored.results[0].case.input_text == "What is 2+2?"
        assert restored.results[0].case.criteria == ["correct", "concise"]
        assert restored.results[0].reasoning == "exact match"
        assert restored.results[0].criteria_scores == {"correct": 1.0, "concise": 0.9}

    def test_save_and_load_file(self, tmp_path):
        path = tmp_path / "subdir" / "report.json"  # exercises mkdir -p
        report = _make_report()
        report.save(str(path))
        assert path.exists()

        loaded = EvalReport.load(str(path))
        assert loaded.suite_name == "math_basic"
        assert len(loaded.results) == 1
        assert loaded.results[0].case.name == "addition"

    def test_load_missing_file_returns_empty(self, tmp_path):
        # Should not raise; logs a warning and returns an empty report
        loaded = EvalReport.load(str(tmp_path / "does_not_exist.json"))
        assert loaded.suite_name == ""
        assert loaded.results == []

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        loaded = EvalReport.load(str(path))
        assert loaded.results == []

    def test_empty_report_round_trip(self):
        report = EvalReport(suite_name="empty")
        js = report.to_json()
        restored = EvalReport.from_json(js)
        assert restored.suite_name == "empty"
        assert restored.results == []
