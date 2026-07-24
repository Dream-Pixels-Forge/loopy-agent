"""
Agentic Loop — Plan → Act → Observe → Reflect

The core execution cycle for autonomous AI agents.
Each iteration: plan next steps, execute actions, observe results, reflect on progress.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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

    async def run(self, initial_context: str = "") -> list[StepResult]:
        """
        Execute the full agentic loop.
        
        Returns:
            List of StepResult for each iteration.
        """
        self.history = []
        
        if initial_context:
            self.history.append(
                StepResult(
                    step=0,
                    status=StepStatus.OBSERVING,
                    observation=initial_context,
                )
            )

        for step_num in range(1, self.config.max_steps + 1):
            result = await self._run_step(step_num)
            self.history.append(result)
            
            if result.status == StepStatus.FAILED and self.config.stop_on_error:
                logger.error(f"Loop stopped at step {step_num}: {result.error}")
                break
            
            # Check custom stop condition
            if self.config.should_stop:
                try:
                    if await self.config.should_stop(self.history):
                        logger.info(f"Stop condition met at step {step_num}")
                        break
                except Exception as e:
                    logger.warning(f"Stop condition check failed: {e}")

            # Default stop: all callbacks are None (no-op loop)
            if not any([self.config.planner, self.config.actor, 
                       self.config.observer, self.config.reflector]):
                logger.info("No callbacks configured, stopping loop")
                break

        return self.history

    async def _run_step(self, step_num: int) -> StepResult:
        """Execute a single iteration of the loop."""
        result = StepResult(step=step_num, status=StepStatus.PLANNING)
        
        try:
            # PLAN
            if self.config.planner:
                result.plan = await self.config.planner(self.history)
                logger.debug(f"Step {step_num} plan: {result.plan[:100]}...")
            
            # ACT
            result.status = StepStatus.ACTING
            if self.config.actor:
                result.action = await self.config.actor(result.plan)
                logger.debug(f"Step {step_num} action: {result.action[:100]}...")
            
            # OBSERVE
            result.status = StepStatus.OBSERVING
            if self.config.observer:
                result.observation = await self.config.observer(result.action)
                logger.debug(f"Step {step_num} observation: {result.observation[:100]}...")
            
            # REFLECT
            result.status = StepStatus.REFLECTING
            if self.config.reflector:
                result.reflection = await self.config.reflector(self.history)
                logger.debug(f"Step {step_num} reflection: {result.reflection[:100]}...")
            
            result.status = StepStatus.COMPLETE
            
        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = str(e)
            logger.error(f"Step {step_num} failed: {e}")
            
            if self.config.stop_on_error:
                raise

        return result
