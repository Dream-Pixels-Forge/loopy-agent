"""
Example 7: Complete Workflow

Combines all loopy features into a complete AI agent workflow.
"""

import asyncio

from loopy import (
    AgentLoop,
    CircuitBreakerMiddleware,
    EvalGate,
    EvalGateType,
    Gateway,
    JudgeConfig,
    LLMCache,
    LoopConfig,
    MiddlewarePipeline,
    Orchestrator,
    RetryMiddleware,
    Router,
    RoutingRule,
    SubAgent,
    TraceExporter,
    Tracer,
)

# ============================================================
# Simulated LLM responses (replace with real API calls)
# ============================================================

async def simulate_llm(prompt: str) -> str:
    """Simulate an LLM response."""
    await asyncio.sleep(0.1)
    return f"LLM response to: {prompt[:50]}..."


# ============================================================
# Agent Loop Callbacks
# ============================================================

async def planner(history: list) -> str:
    """Plan next steps based on history."""
    step = len(history) + 1
    if step == 1:
        return "Research the topic thoroughly"
    elif step == 2:
        return "Analyze findings and identify key insights"
    elif step == 3:
        return "Write a comprehensive summary"
    return "Task complete"


async def actor(plan: str) -> str:
    """Execute the planned action."""
    return await simulate_llm(plan)


async def observer(action: str) -> str:
    """Observe and evaluate the action."""
    return f"Observed progress: {action[:50]}..."


async def reflector(history: list) -> str:
    """Reflect on progress."""
    if len(history) >= 3:
        return "All objectives met!"
    return "Continue to next phase"


# ============================================================
# Specialist Agent Handlers
# ============================================================

async def researcher(task: str, context: dict) -> str:
    """Research agent."""
    return await simulate_llm(f"Research: {task}")


async def analyst(task: str, context: dict) -> str:
    """Analysis agent."""
    return await simulate_llm(f"Analyze: {task}")


async def writer(task: str, context: dict) -> str:
    """Writing agent."""
    return await simulate_llm(f"Write: {task}")


# ============================================================
# Main Workflow
# ============================================================

async def main():
    print("Loopy Complete Workflow Example")
    print("=" * 50)
    print()
    
    # ============================================
    # 1. Setup Infrastructure
    # ============================================
    print("1. Setting up infrastructure...")
    
    # Tracing
    tracer = Tracer(service="loopy-workflow")
    
    # Cache
    cache = LLMCache(ttl=3600, max_size=100)
    
    # Gateway (simulated)
    Gateway()
    
    # ============================================
    # 2. Create Middleware Pipeline
    # ============================================
    print("2. Creating middleware pipeline...")
    
    pipeline = MiddlewarePipeline()
    pipeline.add(RetryMiddleware(max_retries=3, base_delay=0.1))
    pipeline.add(CircuitBreakerMiddleware(failure_threshold=5))
    
    # ============================================
    # 3. Setup Router & Orchestrator
    # ============================================
    print("3. Setting up orchestrator with routing...")
    
    router = Router()
    router.add_rule(RoutingRule(
        pattern=r"research|find|search",
        agent_name="researcher",
        priority=1,
    ))
    router.add_rule(RoutingRule(
        pattern=r"analyze|evaluate|assess",
        agent_name="analyst",
        priority=2,
    ))
    router.add_rule(RoutingRule(
        pattern=r"write|create|draft",
        agent_name="writer",
        priority=3,
    ))
    
    orchestrator = Orchestrator(router=router)
    orchestrator.add_agent(SubAgent(
        name="researcher",
        description="Gathers information",
        handler=researcher,
    ))
    orchestrator.add_agent(SubAgent(
        name="analyst",
        description="Analyzes data",
        handler=analyst,
    ))
    orchestrator.add_agent(SubAgent(
        name="writer",
        description="Creates content",
        handler=writer,
    ))
    
    # ============================================
    # 4. Setup Evaluation Gate
    # ============================================
    print("4. Setting up evaluation gate...")
    
    eval_gate = EvalGate(
        gate_type=EvalGateType.JUDGE,
        config=JudgeConfig(
            criteria=["accuracy", "completeness", "clarity"],
            threshold=0.7,
        ),
    )
    
    # ============================================
    # 5. Run Agent Loop
    # ============================================
    print("5. Running agent loop...")
    print()
    
    with tracer.start("agent_loop") as span:
        span.set_attribute("max_steps", 3)
        
        loop = AgentLoop(LoopConfig(
            planner=planner,
            actor=actor,
            observer=observer,
            reflector=reflector,
            max_steps=3,
        ))
        
        results = await loop.run(initial_context="Research AI best practices")
        
        for result in results:
            print(f"  Step {result.step}: {result.status.value}")
            if result.plan:
                print(f"    Plan: {result.plan}")
        
        span.set_attribute("completed_steps", len(results))
    
    print()
    
    # ============================================
    # 6. Run Orchestrator Tasks
    # ============================================
    print("6. Running orchestrator tasks...")
    
    tasks = [
        "Research current AI trends",
        "Analyze competitive landscape",
        "Write executive summary",
    ]
    
    for task in tasks:
        agent_name = await orchestrator.route(task)
        print(f"  Task: '{task}'")
        print(f"    -> Routed to: {agent_name}")
    
    print()
    
    # ============================================
    # 7. Evaluate Output
    # ============================================
    print("7. Evaluating output quality...")
    
    eval_result = await eval_gate.evaluate(
        input_text="Summarize AI best practices",
        output="AI best practices include responsible development, testing, and monitoring.",
    )
    
    print(f"  Passed: {eval_result.passed}")
    print(f"  Score: {eval_result.score}")
    print(f"  Feedback: {eval_result.feedback}")
    
    print()
    
    # ============================================
    # 8. Export Traces
    # ============================================
    print("8. Exporting traces...")
    
    exporter = TraceExporter(tracer)
    exporter.export_file("workflow_traces.json")
    
    print(f"  Exported {len(tracer.get_spans())} spans")
    
    # ============================================
    # Summary
    # ============================================
    print()
    print("=" * 50)
    print("Workflow Complete!")
    print()
    
    # Print orchestrator summary
    summary = orchestrator.get_summary()
    print("Orchestrator Summary:")
    print(f"  Total agents: {summary['total_agents']}")
    print(f"  Total runs: {summary['total_runs']}")
    print(f"  Completed: {summary['completed']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Avg duration: {summary['avg_duration_ms']:.0f}ms")
    
    # Print cache stats
    stats = cache.stats()
    print("\nCache Stats:")
    print(f"  Hit rate: {stats.hit_rate:.1%}")
    print(f"  Estimated savings: ${stats.estimated_savings:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
