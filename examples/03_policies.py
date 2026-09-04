"""03 — Compliance-as-Code policy gate.

Run with::

    python examples/03_policies.py

No API key required. Demonstrates a ``PolicyEngine`` that
blocks when the retry threshold is exceeded.
"""

import asyncio

from loopy import AgentLoop, LoopConfig
from loopy.policies import (
    Condition,
    Policy,
    PolicyEngine,
    PolicyViolation,
)


async def main() -> None:
    # A "block on first step" policy: the engine reads
    # context["retries"] which is the step index - 1, so
    # retries > 0 is true from step 2 onward.
    engine = PolicyEngine(
        policies=[
            Policy(
                name="always-block",
                conditions=[Condition(kind="max_retries", value=0)],
                severity="block",
            )
        ]
    )

    async def planner(_):
        return "plan"

    async def actor(_):
        return "action"

    config = LoopConfig(
        planner=planner,
        actor=actor,
        max_steps=2,
        policy_engine=engine,
    )
    loop = AgentLoop(config)
    try:
        await loop.run()
        print("policy: should have blocked!")
    except PolicyViolation as exc:
        print(f"policy: blocked by {exc.policy_name}")


if __name__ == "__main__":
    asyncio.run(main())
