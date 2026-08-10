"""
Example 4: Orchestrator-Workers Pattern

Demonstrates task routing and decomposition with specialist agents.
"""

import asyncio

from loopy import (
    Orchestrator,
    Router,
    RoutingRule,
    SubAgent,
    TaskDecomposer,
)


# Define specialist agent handlers
async def researcher(task: str, context: dict) -> str:
    """Research agent - gathers information."""
    await asyncio.sleep(0.1)  # Simulate work
    return f"Research findings for: {task[:50]}..."


async def coder(task: str, context: dict) -> str:
    """Coder agent - writes code."""
    await asyncio.sleep(0.2)  # Simulate work
    return f"Code implementation for: {task[:50]}..."


async def tester(task: str, context: dict) -> str:
    """Tester agent - tests code."""
    await asyncio.sleep(0.15)  # Simulate work
    return f"Test results for: {task[:50]}..."


async def writer(task: str, context: dict) -> str:
    """Writer agent - creates documentation."""
    await asyncio.sleep(0.1)  # Simulate work
    return f"Documentation for: {task[:50]}..."


async def main():
    # Create router with patterns
    router = Router()
    
    # Research patterns
    router.add_rule(RoutingRule(
        pattern=r"research|analyze|investigate|find",
        agent_name="researcher",
        priority=1,
        description="Routes research tasks",
    ))
    
    # Coding patterns
    router.add_rule(RoutingRule(
        pattern=r"code|implement|build|create|write",
        agent_name="coder",
        priority=2,
        description="Routes coding tasks",
    ))
    
    # Testing patterns
    router.add_rule(RoutingRule(
        pattern=r"test|verify|validate|check",
        agent_name="tester",
        priority=3,
        description="Routes testing tasks",
    ))
    
    # Documentation patterns
    router.add_rule(RoutingRule(
        pattern=r"document|docs|readme|explain",
        agent_name="writer",
        priority=4,
        description="Routes documentation tasks",
    ))
    
    # Create orchestrator with router
    orchestrator = Orchestrator(router=router)
    
    # Register specialist agents
    orchestrator.add_agent(SubAgent(
        name="researcher",
        description="Gathers information and analyzes data",
        handler=researcher,
    ))
    
    orchestrator.add_agent(SubAgent(
        name="coder",
        description="Writes and implements code",
        handler=coder,
    ))
    
    orchestrator.add_agent(SubAgent(
        name="tester",
        description="Tests code and validates functionality",
        handler=tester,
    ))
    
    orchestrator.add_agent(SubAgent(
        name="writer",
        description="Creates documentation and explanations",
        handler=writer,
    ))
    
    # Example 1: Automatic routing
    print("=== Example 1: Automatic Routing ===")
    
    tasks = [
        "Research Python async patterns",
        "Build a REST API endpoint",
        "Test the authentication module",
        "Document the deployment process",
    ]
    
    for task in tasks:
        agent_name = await orchestrator.route(task)
        print(f"Task: '{task[:40]}...'")
        print(f"  -> Routed to: {agent_name}")
    
    print()
    
    # Example 2: Run single task
    print("=== Example 2: Run Single Task ===")
    
    result = await orchestrator.run("Build a user authentication system")
    print(f"Agent: {result.agent_name}")
    print(f"Status: {result.status.value}")
    print(f"Output: {result.output}")
    print(f"Duration: {result.duration_ms:.0f}ms")
    print()
    
    # Example 3: Run all agents in parallel
    print("=== Example 3: Run All Agents ===")
    
    results = await orchestrator.run_all("Analyze system performance")
    for r in results:
        print(f"Agent: {r.agent_name}, Status: {r.status.value}")
    
    print()
    
    # Example 4: Task decomposition
    print("=== Example 4: Task Decomposition ===")
    
    decomposer = TaskDecomposer()
    subtasks = await decomposer.decompose("Build a REST API with tests and documentation")
    
    print(f"Decomposed into {len(subtasks)} subtasks:")
    for task in subtasks:
        deps = ", ".join(task.dependencies) if task.dependencies else "none"
        print(f"  - {task.id}: {task.description}")
        print(f"    Dependencies: {deps}")
        print(f"    Agent: {task.required_agent}")
    
    # Example 5: Run decomposed task
    print("\n=== Example 5: Run Decomposed Task ===")
    
    results = await orchestrator.run_decomposed("Build a REST API")
    for r in results:
        print(f"Agent: {r.agent_name}, Status: {r.status.value}")
    
    # Print summary
    print("\n=== Orchestrator Summary ===")
    summary = orchestrator.get_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
