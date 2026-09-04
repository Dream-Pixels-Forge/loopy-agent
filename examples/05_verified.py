"""05 — VerifiedAgent with invariants.

Run with::

    python examples/05_verified.py

No API key required. Drives the agent on 3 inputs and
verifies the output contains "hi" in every case.
"""

import asyncio

from loopy import AgentLoop, LoopConfig
from loopy.verifier import (
    VerifiedAgent,
    VerificationSpec,
    output_must_contain,
)


async def main() -> None:
    async def planner(_):
        return "plan"

    async def actor(_):
        return "hi there"

    agent = AgentLoop(LoopConfig(planner=planner, actor=actor, max_steps=1))

    spec = VerificationSpec(
        invariants=[output_must_contain("hi")],
    )
    verifier = VerifiedAgent(agent=agent, spec=spec)
    report = await verifier.verify(n_cases=3)
    print(
        f"verifier: passed={report.passed} cases={report.cases_run} "
        f"failures={report.failures}"
    )


if __name__ == "__main__":
    asyncio.run(main())
