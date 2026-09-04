"""00 — minimal AgentLoop.

Run with::

    python examples/00_hello_world.py

No API key required — uses a canned ``planner`` + ``actor``
that return fixed strings (the "TestModel pattern").
"""

import asyncio

from loopy import AgentLoop, LoopConfig


async def main() -> None:
    async def planner(_history):
        return "plan: greet the user"

    async def actor(_plan):
        return "hello from loopy-agent!"

    config = LoopConfig(planner=planner, actor=actor, max_steps=3)
    loop = AgentLoop(config)
    result = await loop.run("hi")
    if isinstance(result, list):
        print(f"agent output: {result[-1].action}")


if __name__ == "__main__":
    asyncio.run(main())
