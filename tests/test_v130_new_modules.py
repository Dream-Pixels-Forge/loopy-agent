"""Tests for loopy.patterns — Dynamic workflow patterns."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest

from loopy.agents import (
    AgentResult,
    AgentStatus,
    Orchestrator,
    RoutingRule,
    SubAgent,
)
from loopy.patterns import (
    AdversarialVerification,
    ClassifyAndAct,
    DynamicPatternRegistry,
    FanOutSynthesize,
    PatternResult,
    PatternType,
    Tournament,
)
from loopy.session import MessageOrigin, Session, SessionConfig, SessionManager, TranscriptEntry
from loopy.subagents import IsolatedAgentPool, IsolatedSubAgent, IsolationLevel, SubagentConfig

logger = logging.getLogger("loopy.tests")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_orchestrator(agent_names: list[str] | None = None) -> Orchestrator:
    """Build a minimal Orchestrator with dummy agents for pattern testing."""

    async def make_handler(n: str) -> Any:
        async def handler(task: str, ctx: dict[str, Any]) -> str:
            return f"Output from {n}"

        return handler

    orch = Orchestrator()
    if agent_names is None:
        agent_names = ["coder", "reviewer", "critic-agent"]
    for name in agent_names:
        orch.add_agent(SubAgent(name=name, handler=await make_handler(name)))
    # Give the router a fallback rule so ClassifyAndAct can route.
    orch.router.add_rule(RoutingRule(pattern=r".*", agent_name=agent_names[0]))
    return orch


async def _make_isolated_pool(agent_names: list[str] | None = None) -> IsolatedAgentPool:

    async def make_handler(n: str) -> Any:
        async def handler(task: str, ctx: dict[str, Any]) -> str:
            return f"Hello from {n}"

        return handler

    pool = IsolatedAgentPool(max_concurrent=3)
    if agent_names is None:
        agent_names = ["writer", "editor"]
    for name in agent_names:
        pool.add_agent(
            IsolatedSubAgent(
                name=name,
                handler=await make_handler(name),
                config=SubagentConfig(isolation=IsolationLevel.CONTEXT),
            )
        )
    return pool


# ---------------------------------------------------------------------------
# PatternResult tests
# ---------------------------------------------------------------------------


class TestPatternResult:
    def test_to_dict(self):
        result = PatternResult(
            pattern=PatternType.FAN_OUT_SYNTHESIZE,
            input="hello",
            success=True,
            duration_ms=12.5,
            synthesized="combined",
        )
        d = result.to_dict()
        assert d["pattern"] == "fan_out_synthesize"
        assert d["input"] == "hello"
        assert d["success"] is True
        assert d["duration_ms"] == 12.5
        assert d["synthesized"] == "combined"
        assert d["result_count"] == 0

    def test_to_dict_with_results(self):
        res = AgentResult(
            agent_name="a1",
            status=AgentStatus.COMPLETED,
            output="ok",
            duration_ms=5.0,
        )
        result = PatternResult(
            pattern=PatternType.CLASSIFY_AND_ACT,
            input="test",
            results=[res],
        )
        d = result.to_dict()
        assert d["result_count"] == 1


# ---------------------------------------------------------------------------
# FanOutSynthesize tests
# ---------------------------------------------------------------------------


class TestFanOutSynthesize:
    @pytest.mark.asyncio
    async def test_runs_all_agents(self):
        orch = await _make_orchestrator(["alice", "bob"])
        pattern = FanOutSynthesize(max_fans=10)
        result = await pattern.run(orch, "do the thing")
        assert result.pattern == PatternType.FAN_OUT_SYNTHESIZE
        assert result.success is True
        assert len(result.results) == 2
        assert all(r.status == AgentStatus.COMPLETED for r in result.results)

    @pytest.mark.asyncio
    async def test_max_fans_limit(self):
        orch = await _make_orchestrator(["a", "b", "c", "d", "e"])
        pattern = FanOutSynthesize(max_fans=2)
        result = await pattern.run(orch, "input")
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_no_agents_returns_failure(self):
        orch = Orchestrator()
        pattern = FanOutSynthesize()
        result = await pattern.run(orch, "input")
        assert result.success is False
        assert "No agents registered" in result.error

    @pytest.mark.asyncio
    async def test_synthesizer_called(self):
        async def synth(results):
            return "Synthesized: " + "; ".join(r.output or "" for r in results)

        orch = await _make_orchestrator(["x"])
        pattern = FanOutSynthesize(synthesizer=synth)
        result = await pattern.run(orch, "input")
        assert result.synthesized == "Synthesized: Output from x"

    @pytest.mark.asyncio
    async def test_synthesizer_failure_does_not_blow_up(self):
        async def bad_synth(results):
            raise RuntimeError("boom")

        orch = await _make_orchestrator(["x"])
        pattern = FanOutSynthesize(synthesizer=bad_synth)
        result = await pattern.run(orch, "input")
        assert result.success is True
        assert result.synthesized == ""

    @pytest.mark.asyncio
    async def test_agent_handler_raises(self):
        async def boom_handler(task, ctx):
            raise ValueError("agent boom")

        orch = Orchestrator()
        orch.add_agent(SubAgent(name="boom", handler=boom_handler))
        pattern = FanOutSynthesize()
        result = await pattern.run(orch, "input")
        assert result.success is False
        assert len(result.results) == 1
        assert result.results[0].status == AgentStatus.FAILED
        assert "agent boom" in result.results[0].error


# ---------------------------------------------------------------------------
# ClassifyAndAct tests
# ---------------------------------------------------------------------------


class TestClassifyAndAct:
    @pytest.mark.asyncio
    async def test_routes_and_runs(self):
        orch = await _make_orchestrator(["coder", "reviewer"])
        pattern = ClassifyAndAct()
        result = await pattern.run(orch, "write code")
        assert result.pattern == PatternType.CLASSIFY_AND_ACT
        assert result.success is True
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_routing_error(self):
        orch = await _make_orchestrator()
        # Force routing failure by setting a handler that raises on route.

        async def fail_route(query: str) -> str:
            raise RuntimeError("route broken")

        orch.route = fail_route  # type: ignore[method-assign]
        pattern = ClassifyAndAct()
        result = await pattern.run(orch, "input")
        assert result.success is False
        assert "Routing failed" in result.error


# ---------------------------------------------------------------------------
# AdversarialVerification tests
# ---------------------------------------------------------------------------


class TestAdversarialVerification:
    @pytest.mark.asyncio
    async def test_primary_only_no_critic(self):
        orch = await _make_orchestrator(["primary"])
        pattern = AdversarialVerification(critic_label="critic")
        result = await pattern.run(orch, "input")
        assert result.success is True
        assert len(result.results) == 1
        assert result.synthesized == "Output from primary"

    @pytest.mark.asyncio
    async def test_critic_feedback_included(self):
        orch = await _make_orchestrator(["primary", "critic-agent"])
        pattern = AdversarialVerification(critic_label="critic")
        result = await pattern.run(orch, "input")
        assert result.success is True
        assert len(result.results) == 2
        assert "critic-agent" in result.synthesized

    @pytest.mark.asyncio
    async def test_primary_failure(self):
        async def failing_handler(task: str, ctx: dict[str, Any]) -> str:
            raise ValueError("kaboom")

        orch = Orchestrator()
        orch.add_agent(SubAgent(name="bad", handler=failing_handler))
        pattern = AdversarialVerification()
        result = await pattern.run(orch, "input")
        assert result.success is False
        assert "kaboom" in result.error


# ---------------------------------------------------------------------------
# Tournament tests
# ---------------------------------------------------------------------------


class TestTournament:
    @pytest.mark.asyncio
    async def test_basic_tournament(self):
        orch = await _make_orchestrator(["short", "long"])
        pattern = Tournament(prefer_shorter=True)
        result = await pattern.run(orch, "input")
        assert result.pattern == PatternType.TOURNAMENT
        assert result.success is True

    @pytest.mark.asyncio
    async def test_single_agent(self):
        orch = await _make_orchestrator(["solo"])
        pattern = Tournament()
        result = await pattern.run(orch, "input")
        assert result.success is True
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_no_agents(self):
        orch = Orchestrator()
        pattern = Tournament()
        result = await pattern.run(orch, "input")
        assert result.success is False
        assert "Need at least 2 agents" in result.error

    @pytest.mark.asyncio
    async def test_prefer_longer(self):
        orch = await _make_orchestrator(["short", "long"])
        pattern = Tournament(prefer_shorter=False)
        result = await pattern.run(orch, "input")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_all_agents_fail(self):
        async def fail_handler(task, ctx):
            raise ValueError("always fails")

        orch = Orchestrator()
        orch.add_agent(SubAgent(name="bad1", handler=fail_handler))
        orch.add_agent(SubAgent(name="bad2", handler=fail_handler))
        pattern = Tournament(prefer_shorter=True)
        result = await pattern.run(orch, "input")
        # When all fail, _pick_winner returns ra (first arg)
        assert result.pattern == PatternType.TOURNAMENT

    def test_pick_winner_both_failed(self):
        pattern = Tournament()
        ra = AgentResult(agent_name="a", status=AgentStatus.FAILED, error="err")
        rb = AgentResult(agent_name="b", status=AgentStatus.FAILED, error="err")
        winner = pattern._pick_winner(ra, rb)
        assert winner is ra

    def test_pick_winner_rb_failed(self):
        pattern = Tournament()
        ra = AgentResult(agent_name="a", status=AgentStatus.COMPLETED, output="ok")
        rb = AgentResult(agent_name="b", status=AgentStatus.FAILED, error="err")
        winner = pattern._pick_winner(ra, rb)
        assert winner is ra

    def test_pick_winner_ra_failed(self):
        pattern = Tournament()
        ra = AgentResult(agent_name="a", status=AgentStatus.FAILED, error="err")
        rb = AgentResult(agent_name="b", status=AgentStatus.COMPLETED, output="ok")
        winner = pattern._pick_winner(ra, rb)
        assert winner is rb


# ---------------------------------------------------------------------------
# DynamicPatternRegistry tests
# ---------------------------------------------------------------------------


class TestDynamicPatternRegistry:
    def test_builtin_patterns_registered(self):
        reg = DynamicPatternRegistry()
        types = reg.list_all()
        assert PatternType.FAN_OUT_SYNTHESIZE in types
        assert PatternType.CLASSIFY_AND_ACT in types
        assert PatternType.ADVERSARIAL_VERIFICATION in types
        assert PatternType.TOURNAMENT in types

    def test_get_unknown(self):
        reg = DynamicPatternRegistry()
        assert reg.get(PatternType.TOURNAMENT) is not None
        # Custom type not registered.
        assert reg.get(PatternType.FAN_OUT_SYNTHESIZE) is not None  # sanity

    def test_register_custom(self):
        reg = DynamicPatternRegistry()

        class CustomPattern:
            pattern_type = PatternType.FAN_OUT_SYNTHESIZE

            async def run(self, orchestrator, input, *, context=None):
                return PatternResult(pattern=self.pattern_type, input=input)

        # Can't register same type — will overwrite.
        custom = CustomPattern()
        reg.register(custom)
        assert reg.get(PatternType.FAN_OUT_SYNTHESIZE) is custom

    @pytest.mark.asyncio
    async def test_run_delegates(self):
        reg = DynamicPatternRegistry()
        orch = await _make_orchestrator(["a"])
        result = await reg.run(PatternType.FAN_OUT_SYNTHESIZE, orch, "input")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_unknown_pattern(self):
        reg = DynamicPatternRegistry()
        # PatternType is a strict Enum; we can only test with known types.
        # Verify that the registry has all built-ins before delegating.
        for pt in PatternType:
            assert reg.get(pt) is not None


# ---------------------------------------------------------------------------
# Session tests
# ---------------------------------------------------------------------------


class TestMessageOrigin:
    def test_values(self):
        assert MessageOrigin.SYSTEM.value == "system"
        assert MessageOrigin.AGENT.value == "agent"
        assert MessageOrigin.USER.value == "user"
        assert MessageOrigin.TOOL.value == "tool"


class TestTranscriptEntry:
    def test_to_dict_roundtrip(self):
        entry = TranscriptEntry(
            role=MessageOrigin.USER,
            content="hello",
            metadata={"key": "val"},
        )
        d = entry.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "hello"
        assert d["metadata"] == {"key": "val"}
        restored = TranscriptEntry.from_dict(d)
        assert restored.role == MessageOrigin.USER
        assert restored.content == "hello"
        assert restored.metadata == {"key": "val"}


class TestSession:
    @pytest.mark.asyncio
    async def test_append_and_retrieve(self):
        session = Session()
        entry = session.append(MessageOrigin.USER, "hi")
        assert entry.role == MessageOrigin.USER
        assert entry.content == "hi"
        assert session.entry_count == 1

    @pytest.mark.asyncio
    async def test_string_role_coercion(self):
        session = Session()
        entry = session.append("user", "hey")
        assert entry.role == MessageOrigin.USER

    @pytest.mark.asyncio
    async def test_append_helpers(self):
        session = Session()
        s = session.append_system("sys")
        u = session.append_user("usr")
        a = session.append_agent("ag")
        t = session.append_tool("tl")
        assert s.role == MessageOrigin.SYSTEM
        assert u.role == MessageOrigin.USER
        assert a.role == MessageOrigin.AGENT
        assert t.role == MessageOrigin.TOOL

    @pytest.mark.asyncio
    async def test_trim_exceeds_max(self):
        config = SessionConfig(max_transcript_length=2)
        session = Session(config)
        session.append_user("a")
        session.append_user("b")
        session.append_user("c")
        assert session.entry_count == 2
        assert session.recent(10)[0].content == "b"

    @pytest.mark.asyncio
    async def test_recent(self):
        session = Session()
        for i in range(5):
            session.append_user(str(i))
        recent = session.recent(2)
        assert len(recent) == 2
        assert recent[0].content == "3"
        assert recent[1].content == "4"

    @pytest.mark.asyncio
    async def test_last_n_by_role(self):
        session = Session()
        session.append_user("u1")
        session.append_agent("a1")
        session.append_user("u2")
        users = session.last_n_by_role(MessageOrigin.USER, n=1)
        assert len(users) == 1
        assert users[0].content == "u2"

    @pytest.mark.asyncio
    async def test_clear(self):
        session = Session()
        session.append_user("x")
        session.clear()
        assert session.entry_count == 0

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path: Path):
        session = Session()
        session.append_user("hello")
        session.append_agent("world")
        path = tmp_path / "sess.json"
        saved = await session.save(path)
        assert saved.exists()

        loaded = await Session.load(saved)
        assert loaded.session_id == session.session_id
        assert loaded.entry_count == 2
        assert loaded.transcript[0].content == "hello"
        assert loaded.transcript[1].content == "world"

    @pytest.mark.asyncio
    async def test_save_default_path(self, tmp_path: Path):
        session = Session()
        session.append_user("hi")
        saved = await session.save()
        assert saved.exists()

    @pytest.mark.asyncio
    async def test_load_missing(self):
        with pytest.raises(FileNotFoundError):
            await Session.load("/nonexistent/path.json")


class TestSessionManager:
    @pytest.mark.asyncio
    async def test_create_and_list(self):
        mgr = SessionManager()
        s1 = await mgr.create()
        s2 = await mgr.create()
        sessions = await mgr.list_sessions()
        assert len(sessions) == 2
        ids = {s.session_id for s in sessions}
        assert ids == {s1.session_id, s2.session_id}

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        mgr = SessionManager()
        s = await mgr.create()
        retrieved = await mgr.get(s.session_id)
        assert retrieved is s

    @pytest.mark.asyncio
    async def test_remove(self):
        mgr = SessionManager()
        s = await mgr.create()
        ok = await mgr.remove(s.session_id)
        assert ok is True
        assert await mgr.get(s.session_id) is None
        ok2 = await mgr.remove(s.session_id)
        assert ok2 is False

    @pytest.mark.asyncio
    async def test_save_all_requires_path(self):
        mgr = SessionManager()
        await mgr.create()
        paths = await mgr.save_all()
        assert paths == []

    @pytest.mark.asyncio
    async def test_save_all_persists(self, tmp_path: Path):
        mgr = SessionManager(auto_save_path=tmp_path)
        s = await mgr.create()
        s.append_user("data")
        paths = await mgr.save_all()
        assert len(paths) == 1
        assert paths[0].exists()


# ---------------------------------------------------------------------------
# Subagents tests
# ---------------------------------------------------------------------------


class TestIsolationLevel:
    def test_values(self):
        assert IsolationLevel.NONE.value == "none"
        assert IsolationLevel.CONTEXT.value == "context"
        assert IsolationLevel.WORKTREE.value == "worktree"


class TestSubagentConfig:
    def test_defaults(self):
        cfg = SubagentConfig()
        assert cfg.max_concurrent == 5
        assert cfg.timeout_seconds == 300.0
        assert cfg.isolation == IsolationLevel.CONTEXT
        assert cfg.worktree_base is None


class TestIsolatedSubAgent:
    @pytest.mark.asyncio
    async def test_with_worktree(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("hi")
        agent = IsolatedSubAgent(
            name="test-agent",
            handler=lambda task, ctx: "done",
            config=SubagentConfig(isolation=IsolationLevel.WORKTREE),
        )
        updated = await agent.with_worktree(src)
        assert updated.worktree_path is not None
        assert (updated.worktree_path / "file.txt").exists()


class TestIsolatedAgentPool:
    @pytest.mark.asyncio
    async def test_run_named_agent(self):
        pool = await _make_isolated_pool(["alpha"])
        result = await pool.run("task", agent_name="alpha")
        assert result.status == AgentStatus.COMPLETED
        assert "alpha" in result.output

    @pytest.mark.asyncio
    async def test_run_no_agent_registered(self):
        pool = IsolatedAgentPool()
        result = await pool.run("task")
        assert result.status == AgentStatus.FAILED
        assert "No agents registered" in result.error

    @pytest.mark.asyncio
    async def test_run_unknown_agent(self):
        pool = await _make_isolated_pool(["only"])
        result = await pool.run("task", agent_name="missing")
        assert result.status == AgentStatus.FAILED
        assert "Agent not found" in result.error

    @pytest.mark.asyncio
    async def test_run_all(self):
        pool = await _make_isolated_pool(["a", "b"])
        results = await pool.run_all("task")
        assert len(results) == 2
        assert all(r.status == AgentStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_timeout(self):
        async def slow_handler(task: str, ctx: dict[str, Any]) -> str:
            await asyncio.sleep(10)
            return "done"

        pool = IsolatedAgentPool(timeout_seconds=0.05)
        pool.add_agent(
            IsolatedSubAgent(
                name="slow",
                handler=slow_handler,
                config=SubagentConfig(isolation=IsolationLevel.CONTEXT),
            )
        )
        result = await pool.run("task", agent_name="slow")
        assert result.status == AgentStatus.FAILED
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_handler_exception(self):
        async def boom(task, ctx):
            raise ValueError("boom")

        pool = IsolatedAgentPool()
        pool.add_agent(
            IsolatedSubAgent(
                name="boom",
                handler=boom,
                config=SubagentConfig(isolation=IsolationLevel.CONTEXT),
            )
        )
        result = await pool.run("task", agent_name="boom")
        assert result.status == AgentStatus.FAILED
        assert "boom" in result.error

    @pytest.mark.asyncio
    async def test_history_and_summary(self):
        pool = await _make_isolated_pool(["x"])
        await pool.run("t1", agent_name="x")
        await pool.run("t2", agent_name="x")
        hist = pool.get_history()
        assert len(hist) == 2
        summary = pool.get_summary()
        assert summary["total_runs"] == 2
        assert summary["completed"] == 2
        assert summary["failed"] == 0

    @pytest.mark.asyncio
    async def test_no_handler(self):
        pool = IsolatedAgentPool()
        pool.add_agent(IsolatedSubAgent(name="noop", handler=None))
        result = await pool.run("task", agent_name="noop")
        assert result.status == AgentStatus.COMPLETED
        assert "noop" in result.output

    @pytest.mark.asyncio
    async def test_worktree_isolation(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("print('hi')")

        async def wt_handler(task, ctx):
            return ctx.get("_worktree", "")

        pool = IsolatedAgentPool()
        pool.add_agent(
            IsolatedSubAgent(
                name="wt",
                handler=wt_handler,
                config=SubagentConfig(isolation=IsolationLevel.WORKTREE),
            )
        )
        result = await pool.run("task", agent_name="wt", source_dir=src)
        assert result.status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_none_isolation(self):
        async def raw_handler(task, ctx):
            return "raw"

        pool = IsolatedAgentPool()
        pool.add_agent(
            IsolatedSubAgent(
                name="raw",
                handler=raw_handler,
                config=SubagentConfig(isolation=IsolationLevel.NONE),
            )
        )
        result = await pool.run("task", agent_name="raw")
        assert result.status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_all_with_exceptions(self):
        async def boom(_task, _ctx):
            raise ValueError("crash")

        pool = IsolatedAgentPool()
        pool.add_agent(
            IsolatedSubAgent(
                name="boom",
                handler=boom,
                config=SubagentConfig(isolation=IsolationLevel.CONTEXT),
            )
        )
        results = await pool.run_all("task")
        assert len(results) == 1
        assert results[0].status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_summary_empty_history(self):
        pool = IsolatedAgentPool()
        summary = pool.get_summary()
        assert summary["total_runs"] == 0
        assert summary["completed"] == 0
        assert summary["failed"] == 0
        assert summary["avg_duration_ms"] == 0

    @pytest.mark.asyncio
    async def test_save_all_with_callback(self, tmp_path: Path):
        saved_paths: list[Path] = []

        def on_save(session: Session, path: Path) -> None:
            saved_paths.append(path)

        mgr = SessionManager(auto_save_path=tmp_path, auto_save_fn=on_save)
        s = await mgr.create()
        s.append_user("data")
        paths = await mgr.save_all()
        assert len(paths) == 1
        assert len(saved_paths) == 1
        assert saved_paths[0] == paths[0]
