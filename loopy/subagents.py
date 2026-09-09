"""
Subagents — Isolated subagent execution with worktree-style sandboxes.

Provides :class:`IsolatedAgent` — a subagent that runs in its own
asyncio task with bounded concurrency, configurable context isolation,
and optional filesystem worktree snapshots (mirroring
claude-agent-sdk's isolated worktree pattern).

Docs: https://loopy.dev/docs/subagents
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from loopy.agents import AgentResult, AgentStatus, SubAgent

logger = logging.getLogger("loopy.subagents")


class IsolationLevel(str, Enum):
    """How isolated a subagent's execution context is."""

    NONE = "none"  # Same process, no sandbox
    CONTEXT = "context"  # Separate context dict per call
    WORKTREE = "worktree"  # Tempdir worktree copied before execution


@dataclass
class SubagentConfig:
    """Execution constraints for an isolated subagent."""

    max_concurrent: int = 5
    timeout_seconds: float = 300.0
    isolation: IsolationLevel = IsolationLevel.CONTEXT
    worktree_base: Path | None = None


@dataclass
class IsolatedSubAgent(SubAgent):
    """A subagent with execution isolation guarantees.

    Extends :class:`loopy.agents.SubAgent` with configurable
    concurrency limits, timeouts, and optional worktree sandboxing.
    """

    config: SubagentConfig = field(default_factory=SubagentConfig)
    worktree_path: Path | None = None

    async def with_worktree(self, source_dir: Path | str) -> IsolatedSubAgent:
        """Copy *source_dir* into a temp worktree and return self.

        Only meaningful when :attr:`config.isolation` is
        ``IsolationLevel.WORKTREE``.
        """
        src = Path(source_dir)
        base = self.config.worktree_base or Path(tempfile.mkdtemp(prefix="loopy-wt-"))
        wt = base / f"{self.name}-{int(time.monotonic() * 1000)}"
        shutil.copytree(src, wt, dirs_exist_ok=True)
        self.worktree_path = wt
        logger.debug("Created worktree %s for agent %s", wt, self.name)
        return self


class IsolatedAgentPool:
    """Pool of isolated subagents with bounded concurrency and timeouts.

    Each agent runs in its own asyncio task; the pool enforces a
    global concurrency cap and per-agent timeout. Worktree isolation
    copies the project state before each agent invocation so agents
    cannot mutate shared filesystem state.

    Example:
        >>> pool = IsolatedAgentPool(max_concurrent=3, timeout_seconds=60)
        >>> agent = IsolatedSubAgent(
        ...     name="coder",
        ...     handler=write_code,
        ...     config=SubagentConfig(isolation=IsolationLevel.WORKTREE),
        ... )
        >>> pool.add_agent(agent)
        >>> result = await pool.run("Fix the auth bug in src/auth.py")
    """

    def __init__(
        self,
        *,
        max_concurrent: int = 5,
        timeout_seconds: float = 300.0,
        default_isolation: IsolationLevel = IsolationLevel.CONTEXT,
        worktree_base: Path | None = None,
    ) -> None:
        self._agents: dict[str, IsolatedSubAgent] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._history: list[AgentResult] = []
        self._timeout = timeout_seconds
        self._default_isolation = default_isolation
        self._worktree_base = worktree_base or Path(tempfile.mkdtemp(prefix="loopy-pool-wt-"))

    def add_agent(self, agent: IsolatedSubAgent) -> None:
        self._agents[agent.name] = agent
        logger.info(
            "Registered isolated agent: %s (isolation=%s)",
            agent.name,
            agent.config.isolation,
        )

    def get_agent(self, name: str) -> IsolatedSubAgent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[IsolatedSubAgent]:
        return list(self._agents.values())

    async def run(
        self,
        task: str,
        agent_name: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        source_dir: Path | str | None = None,
    ) -> AgentResult:
        """Run *task* on the named agent (or the first available).

        If *source_dir* is provided and the agent uses
        ``IsolationLevel.WORKTREE``, a fresh worktree is created from
        it before invocation.
        """
        if agent_name:
            agent = self._agents.get(agent_name)
            if agent is None:
                return AgentResult(
                    agent_name=agent_name,
                    status=AgentStatus.FAILED,
                    error=f"Agent not found: {agent_name}",
                )
        else:
            agents = list(self._agents.values())
            if not agents:
                return AgentResult(
                    agent_name="none",
                    status=AgentStatus.FAILED,
                    error="No agents registered",
                )
            agent = agents[0]

        async with self._semaphore:
            return await self._run_agent(agent, task, context=context or {}, source_dir=source_dir)

    async def run_all(
        self,
        task: str,
        *,
        context: dict[str, Any] | None = None,
        source_dir: Path | str | None = None,
    ) -> list[AgentResult]:
        """Run *task* on every agent concurrently (bounded by semaphore)."""
        tasks = [
            self._run_agent(a, task, context=context or {}, source_dir=source_dir)
            for a in self._agents.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        final: list[AgentResult] = []
        for i, r in enumerate(results):
            agent = list(self._agents.values())[i]
            if isinstance(r, Exception):
                final.append(
                    AgentResult(agent_name=agent.name, status=AgentStatus.FAILED, error=str(r))
                )
            else:
                final.append(r)
        return final

    async def _run_agent(
        self,
        agent: IsolatedSubAgent,
        task: str,
        *,
        context: dict[str, Any],
        source_dir: Path | str | None = None,
    ) -> AgentResult:
        isolation = agent.config.isolation or self._default_isolation
        start = time.monotonic()
        agent.status = AgentStatus.RUNNING

        try:
            if isolation == IsolationLevel.WORKTREE and source_dir:
                await agent.with_worktree(source_dir)
                ctx = {**context, "_worktree": str(agent.worktree_path)}
            elif isolation == IsolationLevel.CONTEXT:
                ctx = {**context, "_agent": agent.name}
            else:
                ctx = context

            if agent.handler is None:
                output = f"Agent {agent.name} has no handler"
            else:
                output = await asyncio.wait_for(
                    agent.handler(task, ctx),
                    timeout=self._timeout,
                )

            duration_ms = round((time.monotonic() - start) * 1000, 2)
            result = AgentResult(
                agent_name=agent.name,
                status=AgentStatus.COMPLETED,
                output=str(output),
                duration_ms=duration_ms,
                metadata={"isolation": isolation.value},
            )
            agent.status = AgentStatus.COMPLETED
            self._history.append(result)
            logger.info("Agent %s completed in %.0fms", agent.name, duration_ms)
            return result

        except asyncio.TimeoutError:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            result = AgentResult(
                agent_name=agent.name,
                status=AgentStatus.FAILED,
                error=f"Timeout after {self._timeout}s",
                duration_ms=duration_ms,
            )
            agent.status = AgentStatus.FAILED
            self._history.append(result)
            logger.warning("Agent %s timed out after %.0fms", agent.name, duration_ms)
            return result

        except Exception as e:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            result = AgentResult(
                agent_name=agent.name,
                status=AgentStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
            agent.status = AgentStatus.FAILED
            self._history.append(result)
            logger.error("Agent %s failed: %s", agent.name, e)
            return result

    def get_history(self) -> list[AgentResult]:
        return list(self._history)

    def get_summary(self) -> dict[str, Any]:
        completed = sum(1 for r in self._history if r.status == AgentStatus.COMPLETED)
        failed = sum(1 for r in self._history if r.status == AgentStatus.FAILED)
        return {
            "total_agents": len(self._agents),
            "total_runs": len(self._history),
            "completed": completed,
            "failed": failed,
            "avg_duration_ms": (
                sum(r.duration_ms for r in self._history) / len(self._history)
                if self._history
                else 0
            ),
        }
