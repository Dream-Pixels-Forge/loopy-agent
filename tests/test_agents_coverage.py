"""Tests for loopy.agents — Router, TaskDecomposer, Orchestrator coverage."""

from __future__ import annotations

import asyncio
import logging

import pytest

from loopy.agents import (
    AgentResult,
    AgentStatus,
    Orchestrator,
    Router,
    RoutingRule,
    SubAgent,
    SubTask,
    TaskDecomposer,
)

logger = logging.getLogger("loopy.tests")


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------


class TestRouter:
    def test_no_rules_raises(self):
        from loopy.agents import Router

        router = Router()
        with pytest.raises(ValueError, match="No routing rules"):
            asyncio.run(router.classify("anything"))

    @pytest.mark.asyncio
    async def test_custom_classify_fn(self):
        async def my_classifier(task, rules):
            return "custom-agent"

        router = Router(classify_fn=my_classifier)
        result = await router.classify("anything")
        assert result == "custom-agent"

    @pytest.mark.asyncio
    async def test_pattern_matching(self):
        router = Router()
        router.add_rule(RoutingRule(pattern=r"code|build", agent_name="coder"))
        router.add_rule(RoutingRule(pattern=r"research|search", agent_name="researcher"))

        assert await router.classify("Build an API") == "coder"
        assert await router.classify("Search the web") == "researcher"

    @pytest.mark.asyncio
    async def test_fallback_to_first_rule(self):
        router = Router()
        router.add_rule(RoutingRule(pattern=r"specific", agent_name="special"))
        # No match — should fall back to first rule
        result = await router.classify("something else")
        assert result == "special"


# ---------------------------------------------------------------------------
# TaskDecomposer tests
# ---------------------------------------------------------------------------


class TestTaskDecomposer:
    @pytest.mark.asyncio
    async def test_generic_decomposition(self):
        dec = TaskDecomposer()
        subtasks = await dec.decompose("Do some work")
        assert len(subtasks) >= 2
        ids = [s.id for s in subtasks]
        assert "plan" in ids
        assert "execute" in ids

    @pytest.mark.asyncio
    async def test_custom_classify_fn(self):
        # classify_fn is accepted on init but not yet wired into decompose;
        # verify the default path still works without crashing.
        async def my_classifier(task):
            return []

        dec = TaskDecomposer(classify_fn=my_classifier)
        subtasks = await dec.decompose("any task")
        assert len(subtasks) >= 2  # generic decomposition


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_run_no_agents(self):
        orch = Orchestrator()
        result = await orch.run("task")
        assert result.status == AgentStatus.FAILED
        assert "No agents registered" in result.error

    @pytest.mark.asyncio
    async def test_run_unknown_agent(self):
        orch = Orchestrator()
        orch.add_agent(SubAgent(name="a", handler=lambda t, c: "ok"))
        result = await orch.run("task", agent_name="missing")
        assert result.status == AgentStatus.FAILED
        assert "Agent not found" in result.error

    @pytest.mark.asyncio
    async def test_get_history(self):
        async def ok_handler(t, c):
            return "ok"

        orch = Orchestrator()
        orch.add_agent(SubAgent(name="a", handler=ok_handler))
        await orch.run("task")
        hist = orch.get_history()
        assert len(hist) == 1
        assert hist[0].status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_summary(self):
        async def ok_handler(t, c):
            return "ok"

        orch = Orchestrator()
        orch.add_agent(SubAgent(name="a", handler=ok_handler))
        await orch.run("task1")
        await orch.run("task2")
        summary = orch.get_summary()
        assert summary["total_agents"] == 1
        assert summary["total_runs"] == 2
        assert summary["completed"] == 2
        assert summary["failed"] == 0
        assert summary["avg_duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_run_decomposed(self):
        async def planner_handler(t, c):
            return "plan"

        async def executor_handler(t, c):
            return "done"

        orch = Orchestrator()
        orch.add_agent(SubAgent(name="planner", handler=planner_handler))
        orch.add_agent(SubAgent(name="executor", handler=executor_handler))
        orch.router.add_rule(RoutingRule(pattern=r".*", agent_name="planner"))
        results = await orch.run_decomposed("do something")
        assert len(results) >= 2
        assert all(r.status == AgentStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_run_all(self):
        async def a_handler(t, c):
            return "a"

        async def b_handler(t, c):
            return "b"

        orch = Orchestrator()
        orch.add_agent(SubAgent(name="a", handler=a_handler))
        orch.add_agent(SubAgent(name="b", handler=b_handler))
        results = await orch.run_all("task")
        assert len(results) == 2
        assert all(r.status == AgentStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_list_agents(self):
        orch = Orchestrator()
        orch.add_agent(SubAgent(name="x", handler=lambda t, c: "x"))
        orch.add_agent(SubAgent(name="y", handler=lambda t, c: "y"))
        agents = orch.list_agents()
        assert len(agents) == 2
        names = {a.name for a in agents}
        assert names == {"x", "y"}

    @pytest.mark.asyncio
    async def test_get_agent(self):
        orch = Orchestrator()
        orch.add_agent(SubAgent(name="only", handler=lambda t, c: "ok"))
        assert orch.get_agent("only") is not None
        assert orch.get_agent("missing") is None


class TestSubTask:
    def test_subtask_defaults(self):
        st = SubTask(id="t1", description="do it")
        assert st.id == "t1"
        assert st.dependencies == []
        assert st.required_agent is None
        assert st.status == "pending"

    def test_agent_result_completed(self):
        r = AgentResult(agent_name="a", status=AgentStatus.COMPLETED, output="ok")
        assert r.status == AgentStatus.COMPLETED
        assert r.output == "ok"
        assert r.error is None

    def test_agent_result_failed(self):
        r = AgentResult(agent_name="a", status=AgentStatus.FAILED, error="boom")
        assert r.status == AgentStatus.FAILED
        assert r.error == "boom"
        assert r.output == ""
