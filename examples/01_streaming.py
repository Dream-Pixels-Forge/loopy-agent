"""01 — token-by-token streaming output.

Run with::

    python examples/01_streaming.py

No API key required. Demonstrates ``Streamer`` + ``StreamChunk``
for incremental output from an LLM callable.
"""

import asyncio

from loopy.streaming import Streamer


async def main() -> None:
    # A canned LLM callable that yields one chunk at a time.
    async def fake_llm(prompt: str) -> str:
        for word in prompt.split():
            yield word + " "

    streamer = Streamer()
    print("streamed: ", end="", flush=True)
    async for chunk in streamer.stream(fake_llm, "hello streaming world"):
        print(chunk.data, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
