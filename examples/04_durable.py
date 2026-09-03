"""04 — durable workflow: DAG + Saga + journal.

Run with::

    python examples/04_durable.py

No API key required. Demonstrates a 3-step DAG that runs to
completion with Saga compensation: if a later step raises,
earlier steps' compensation callables run in reverse.
"""

import asyncio

from loopy.durable import DAG, State, Step, Workflow


async def make_a(s: State) -> State:
    return State(data={**s.data, "a": 1})


async def make_b(s: State) -> State:
    return State(data={**s.data, "b": 2})


async def make_c(s: State) -> State:
    return State(data={**s.data, "c": 3})


async def main() -> None:
    dag = DAG(
        name="etl",
        steps=[
            Step("a", run=make_a),
            Step("b", run=make_b),
            Step("c", run=make_c),
        ],
    )
    final = await Workflow.run(dag, State(data={}))
    print(f"durable: final data = {final.data}")


if __name__ == "__main__":
    asyncio.run(main())
