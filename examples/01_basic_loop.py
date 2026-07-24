"""
Example 1: Basic Agentic Loop

Demonstrates the Plan → Act → Observe → Reflect cycle.
"""

import asyncio
from loopy import AgentLoop, LoopConfig, StepStatus


async def planner(history: list) -> str:
    """Plan the next step based on history."""
    step = len(history) + 1
    return f"Step {step}: Execute task"


async def actor(plan: str) -> str:
    """Execute the planned action."""
    return f"Executed: {plan}"


async def observer(action: str) -> str:
    """Observe the results of the action."""
    return f"Observed: {action} - Looks good!"


async def reflector(history: list) -> str:
    """Reflect on progress and decide next steps."""
    if len(history) >= 3:
        return "Task complete!"
    return "Continue to next step"


async def main():
    # Create loop with callbacks
    loop = AgentLoop(LoopConfig(
        planner=planner,
        actor=actor,
        observer=observer,
        reflector=reflector,
        max_steps=5,
    ))
    
    # Run the loop
    results = await loop.run(initial_context="Starting task...")
    
    # Print results
    for result in results:
        print(f"Step {result.step}: {result.status.value}")
        if result.plan:
            print(f"  Plan: {result.plan}")
        if result.action:
            print(f"  Action: {result.action}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
