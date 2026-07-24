"""
Subagents & Multi-Agent Systems — Delegated reasoning, isolated context.

Orchestrator pattern for spawning and managing subagents.
Includes Router and TaskDecomposer for 2026 orchestrator-workers pattern.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger("loopy.agents")


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Result from a subagent execution."""
    
    agent_name: str
    status: AgentStatus
    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0


@dataclass
class SubAgent:
    """
    A subagent with its own tools and context.
    
    Example:
        agent = SubAgent(
            name="researcher",
            description="Searches the web for information",
            tools=["search", "fetch_url"],
            handler=my_research_handler,
        )
    """
    
    name: str
    description: str = ""
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    handler: Callable[[str, dict[str, Any]], Awaitable[str]] | None = None
    
    # State
    status: AgentStatus = AgentStatus.PENDING
    result: AgentResult | None = None


class SubTask:
    """A subtask created by TaskDecomposer."""
    
    def __init__(
        self,
        id: str,
        description: str,
        dependencies: list[str] | None = None,
        required_agent: str | None = None,
    ):
        self.id = id
        self.description = description
        self.dependencies = dependencies or []
        self.required_agent = required_agent
        self.status: str = "pending"
        self.result: str | None = None


class RoutingRule:
    """Rule for routing tasks to agents."""
    
    def __init__(
        self,
        pattern: str,
        agent_name: str,
        priority: int = 0,
        description: str = "",
    ):
        self.pattern = pattern
        self.agent_name = agent_name
        self.priority = priority
        self.description = description


class Router:
    """
    Task router for orchestrator-workers pattern.
    
    Classifies input and routes to specialist agents.
    Part of the 2026 orchestrator-workers workflow pattern.
    
    Example:
        router = Router()
        router.add_rule(RoutingRule(
            pattern="research|search|find",
            agent_name="researcher",
            priority=1,
        ))
        router.add_rule(RoutingRule(
            pattern="code|implement|build",
            agent_name="coder",
            priority=2,
        ))
        
        agent_name = await router.classify("Research Python async patterns")
        # Returns "researcher"
    """
    
    def __init__(self, classify_fn: Callable[[str, list[RoutingRule]], Awaitable[str]] | None = None):
        self.rules: list[RoutingRule] = []
        self.classify_fn = classify_fn
    
    def add_rule(self, rule: RoutingRule) -> None:
        """Add a routing rule."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: -r.priority)
    
    async def classify(self, task: str) -> str:
        """
        Classify a task and return the appropriate agent name.
        
        Args:
            task: The task description
        
        Returns:
            Agent name to route to
        """
        if self.classify_fn:
            return await self.classify_fn(task, self.rules)
        
        # Default: pattern matching with regex
        import re
        task_lower = task.lower()
        
        for rule in self.rules:
            if re.search(rule.pattern, task_lower, re.IGNORECASE):
                logger.info(f"Routed task to {rule.agent_name} (pattern: {rule.pattern})")
                return rule.agent_name
        
        # Fallback to first agent if no match
        if self.rules:
            return self.rules[0].agent_name
        
        raise ValueError("No routing rules defined and no default agent")


class TaskDecomposer:
    """
    Decomposes complex tasks into subtasks.
    
    Part of the 2026 orchestrator-workers workflow pattern.
    
    Example:
        decomposer = TaskDecomposer(classify_fn=my_classifier)
        
        subtasks = await decomposer.decompose(
            "Build a REST API with tests and documentation"
        )
        
        for task in subtasks:
            print(f"{task.id}: {task.description}")
    """
    
    def __init__(self, classify_fn: Callable[[str], Awaitable[str]] | None = None):
        self.classify_fn = classify_fn
    
    async def decompose(self, task: str) -> list[SubTask]:
        """
        Break a task into subtasks with dependencies.
        
        Args:
            task: The high-level task to decompose
        
        Returns:
            List of SubTask objects with dependencies
        """
        # Simple pattern-based decomposition
        # In production, this would use an LLM
        subtasks = []
        task_lower = task.lower()
        
        # Detect common patterns
        if "api" in task_lower or "rest" in task_lower:
            subtasks.append(SubTask(
                id="design",
                description="Design API endpoints and data models",
                required_agent="architect",
            ))
            subtasks.append(SubTask(
                id="implement",
                description="Implement API endpoints",
                dependencies=["design"],
                required_agent="coder",
            ))
            subtasks.append(SubTask(
                id="test",
                description="Write and run tests",
                dependencies=["implement"],
                required_agent="tester",
            ))
        elif "research" in task_lower or "analyze" in task_lower:
            subtasks.append(SubTask(
                id="gather",
                description="Gather information and sources",
                required_agent="researcher",
            ))
            subtasks.append(SubTask(
                id="analyze",
                description="Analyze findings",
                dependencies=["gather"],
                required_agent="analyst",
            ))
            subtasks.append(SubTask(
                id="synthesize",
                description="Synthesize into report",
                dependencies=["analyze"],
                required_agent="writer",
            ))
        else:
            # Generic decomposition
            subtasks.append(SubTask(
                id="plan",
                description=f"Plan approach for: {task[:50]}...",
                required_agent="planner",
            ))
            subtasks.append(SubTask(
                id="execute",
                description="Execute the plan",
                dependencies=["plan"],
                required_agent="executor",
            ))
        
        return subtasks


class Orchestrator:
    """
    Multi-agent orchestrator.
    
    Manages a pool of subagents and routes tasks to the appropriate one.
    Supports routing and task decomposition for 2026 orchestrator-workers pattern.
    
    Example:
        orchestrator = Orchestrator()
        
        # Register agents
        orchestrator.add_agent(SubAgent(
            name="researcher",
            description="Searches the web",
            handler=research_fn,
        ))
        
        orchestrator.add_agent(SubAgent(
            name="coder",
            description="Writes and tests code",
            tools=["execute_code"],
            handler=coder_fn,
        ))
        
        # Run a task with routing
        result = await orchestrator.run("Build a REST API for user management")
        print(result)
        
        # Or decompose first
        subtasks = await orchestrator.decompose("Build REST API with tests")
        for task in subtasks:
            result = await orchestrator.run(task.description, agent_name=task.required_agent)
    """
    
    def __init__(self, max_concurrent: int = 5, router: Router | None = None):
        self.agents: dict[str, SubAgent] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._history: list[AgentResult] = []
        self.router = router or Router()
        self.decomposer = TaskDecomposer()
    
    def add_agent(self, agent: SubAgent) -> None:
        """Register a subagent."""
        self.agents[agent.name] = agent
        logger.info(f"Added agent: {agent.name}")
    
    def get_agent(self, name: str) -> SubAgent | None:
        """Get an agent by name."""
        return self.agents.get(name)
    
    def list_agents(self) -> list[SubAgent]:
        """List all registered agents."""
        return list(self.agents.values())
    
    async def route(self, task: str) -> str:
        """
        Route a task to the appropriate agent using the router.
        
        Args:
            task: The task description
        
        Returns:
            Agent name to route to
        """
        return await self.router.classify(task)
    
    async def decompose(self, task: str) -> list[SubTask]:
        """
        Decompose a complex task into subtasks.
        
        Args:
            task: The high-level task
        
        Returns:
            List of SubTask objects with dependencies
        """
        return await self.decomposer.decompose(task)
    
    async def run_decomposed(self, task: str, context: dict[str, Any] | None = None) -> list[AgentResult]:
        """
        Decompose and run a task, executing subtasks in dependency order.
        
        Args:
            task: The high-level task to decompose and execute
            context: Optional context to pass to agents
        
        Returns:
            List of results from each subtask
        """
        subtasks = await self.decompose(task)
        results: list[AgentResult] = []
        completed: set[str] = set()
        
        # Execute in dependency order
        max_iterations = len(subtasks) * 2  # Safety limit
        iteration = 0
        
        while len(completed) < len(subtasks) and iteration < max_iterations:
            iteration += 1
            
            for subtask in subtasks:
                if subtask.id in completed:
                    continue
                
                # Check if dependencies are met
                deps_met = all(dep in completed for dep in subtask.dependencies)
                if not deps_met:
                    continue
                
                # Route to appropriate agent
                agent_name = subtask.required_agent or await self.route(subtask.description)
                
                # Run the subtask
                result = await self.run(
                    subtask.description,
                    agent_name=agent_name,
                    context=context,
                )
                
                subtask.status = "completed" if result.status == AgentStatus.COMPLETED else "failed"
                subtask.result = result.output
                completed.add(subtask.id)
                results.append(result)
        
        return results
    
    async def run_all(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> list[AgentResult]:
        """
        Run a task on all agents in parallel.
        
        Returns:
            List of results from each agent
        """
        tasks = [
            self._run_agent(agent, task, context or {})
            for agent in self.agents.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_name = list(self.agents.keys())[i]
                final_results.append(AgentResult(
                    agent_name=agent_name,
                    status=AgentStatus.FAILED,
                    error=str(result),
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    async def _run_agent(
        self,
        agent: SubAgent,
        task: str,
        context: dict[str, Any],
    ) -> AgentResult:
        """Run a single agent."""
        import time
        start_time = time.time()
        
        agent.status = AgentStatus.RUNNING
        
        try:
            if agent.handler:
                output = await agent.handler(task, context)
            else:
                output = f"Agent {agent.name} has no handler"
            
            duration_ms = (time.time() - start_time) * 1000
            
            result = AgentResult(
                agent_name=agent.name,
                status=AgentStatus.COMPLETED,
                output=output,
                duration_ms=duration_ms,
            )
            
            agent.status = AgentStatus.COMPLETED
            agent.result = result
            self._history.append(result)
            
            logger.info(f"Agent {agent.name} completed in {duration_ms:.0f}ms")
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            result = AgentResult(
                agent_name=agent.name,
                status=AgentStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
            
            agent.status = AgentStatus.FAILED
            agent.result = result
            self._history.append(result)
            
            logger.error(f"Agent {agent.name} failed: {e}")
            return result
    
    def get_history(self) -> list[AgentResult]:
        """Get execution history."""
        return self._history.copy()
    
    def get_summary(self) -> dict[str, Any]:
        """Get summary of all agent executions."""
        return {
            "total_agents": len(self.agents),
            "total_runs": len(self._history),
            "completed": sum(1 for r in self._history if r.status == AgentStatus.COMPLETED),
            "failed": sum(1 for r in self._history if r.status == AgentStatus.FAILED),
            "avg_duration_ms": (
                sum(r.duration_ms for r in self._history) / len(self._history)
                if self._history else 0
            ),
        }

    async def run(
        self,
        task: str,
        agent_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """
        Run a task, optionally targeting a specific agent.
        
        If no agent specified, uses the first available agent.
        """
        # Select agent
        if agent_name:
            agent = self.agents.get(agent_name)
            if not agent:
                return AgentResult(
                    agent_name=agent_name or "unknown",
                    status=AgentStatus.FAILED,
                    error=f"Agent not found: {agent_name}",
                )
        else:
            # Use first available agent
            if not self.agents:
                return AgentResult(
                    agent_name="none",
                    status=AgentStatus.FAILED,
                    error="No agents registered",
                )
            agent = next(iter(self.agents.values()))

        # Run with concurrency control
        async with self._semaphore:
            return await self._run_agent(agent, task, context or {})
