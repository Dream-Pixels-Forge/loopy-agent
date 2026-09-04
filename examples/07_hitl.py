"""07 — HITL: pause + resume an AgentLoop.

Run with::

    python examples/07_hitl.py

No API key required. Demonstrates ``interrupt_before`` on
the actor phase: the loop pauses, returns an ``Interrupt``,
and a human-decision step resumes it.
"""

import asyncio

from loopy import AgentLoop, Interrupt, LoopConfig


async def main() -> None:
    async def planner(_):
        return "plan"

    async def actor(_):
        return "ok"

    async def observer(_):
        return "ok"

    async def reflector(_):
        return "ok"

    config = LoopConfig(
        planner=planner,
        actor=actor,
        observer=observer,
        reflector=reflector,
        max_steps=1,
        interrupt_before=["actor"],
    )
    loop = AgentLoop(config)

    first = await loop.run("hi")
    assert isinstance(first, Interrupt), f"expected Interrupt, got {type(first).__name__}"
    print(f"interrupt: paused at {first.phase!r} step {first.step}")

    approved = Interrupt(
        proposed_action=first.proposed_action,
        decision="approve",
        context=first.context,
        phase=first.phase,
        step=first.step,
    )
    results = await loop.run(resume_from=approved)
    print(f"interrupt: resumed, {len(results)} step(s) completed")


if __name__ == "__main__":
    asyncio.run(main())
