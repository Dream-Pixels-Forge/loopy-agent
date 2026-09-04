"""02 — cost cap + provider fallback.

Run with::

    python examples/02_cost_capped.py

No API key required. Demonstrates ``max_cost_usd`` on a
``Gateway.chat`` call. The "expensive" provider would cost
more than the cap, so the gateway falls back to the
configured TestModel and the call succeeds.
"""

import asyncio

from loopy.gateway import Gateway, TestModel
from loopy.gateway import ModelProvider, ProviderConfig


async def main() -> None:
    gw = Gateway()
    # Provider A is "expensive" (over the cap), Provider B uses
    # the TestModel sentinel — local, free, no API key.
    gw.add_provider(
        "expensive",
        ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="sk-fake",
            model="gpt-4",
            cost_per_1k_tokens=0.06,
        ),
    )
    gw.add_provider(
        "test",
        ProviderConfig(
            provider=ModelProvider.OLLAMA,
            model="TestModel",
            cost_per_1k_tokens=0.0,
        ),
    )
    try:
        # The cap is below what "expensive" would cost, so the
        # gateway falls back to "test".
        response = await gw.chat(
            "hi",
            model=TestModel(),
            max_cost_usd=0.01,
            max_tokens=1000,
        )
        print(f"cost-cap: fell back and got {response.content!r}")
    finally:
        await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
