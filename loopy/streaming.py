"""
Streaming — Real-time token-by-token output.

SSE/WebSocket streaming for agent loops.
Critical gap: 2026 agents must stream responses.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("loopy.streaming")


class StreamEvent(str, Enum):
    """Types of stream events."""
    TOKEN = "token"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    ERROR = "error"
    DONE = "done"


@dataclass
class StreamChunk:
    """A single chunk in a stream."""
    event: StreamEvent
    data: Any
    index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.value,
            "data": self.data,
            "index": self.index,
            "metadata": self.metadata,
        }

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        payload = json.dumps(self.to_dict())
        return f"event: {self.event.value}\ndata: {payload}\n\n"


class StreamBuffer:
    """Buffer for accumulating stream tokens."""

    def __init__(self, flush_threshold: int = 10):
        self.tokens: list[str] = []
        self.flush_threshold = flush_threshold
        self.total_tokens = 0

    def add(self, token: str) -> str | None:
        """Add token, return flushed content if threshold met."""
        self.tokens.append(token)
        self.total_tokens += 1

        if len(self.tokens) >= self.flush_threshold:
            return self.flush()
        return None

    def flush(self) -> str:
        """Flush all buffered tokens."""
        content = "".join(self.tokens)
        self.tokens.clear()
        return content

    @property
    def pending(self) -> str:
        return "".join(self.tokens)


class Streamer:
    """
    Stream LLM responses token-by-token.

    Example:
        async def generate(prompt: str):
            async for chunk in Streamer().stream(llm_fn, prompt):
                if chunk.event == StreamEvent.TOKEN:
                    print(chunk.data, end="", flush=True)
    """

    def __init__(self, buffer_size: int = 10):
        self.buffer = StreamBuffer(flush_threshold=buffer_size)
        self.chunks: list[StreamChunk] = []
        self.index = 0

    async def stream(
        self,
        generator: Callable[[str], AsyncIterator[str]],
        prompt: str,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream tokens from an async generator.

        Args:
            generator: Async function that yields tokens
            prompt: Input prompt

        Yields:
            StreamChunk for each token/event
        """
        self.index = 0

        try:
            async for token in generator(prompt):
                chunk = StreamChunk(
                    event=StreamEvent.TOKEN,
                    data=token,
                    index=self.index,
                )
                self.chunks.append(chunk)
                self.index += 1

                # Buffer and flush
                flushed = self.buffer.add(token)
                if flushed:
                    yield StreamChunk(
                        event=StreamEvent.TOKEN,
                        data=flushed,
                        index=self.index,
                        metadata={"flushed": True},
                    )

            # Flush remaining
            remaining = self.buffer.flush()
            if remaining:
                yield StreamChunk(
                    event=StreamEvent.TOKEN,
                    data=remaining,
                    index=self.index,
                    metadata={"final": True},
                )

            # Done event
            yield StreamChunk(
                event=StreamEvent.DONE,
                data="",
                index=self.index,
                metadata={"total_tokens": self.buffer.total_tokens},
            )

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield StreamChunk(
                event=StreamEvent.ERROR,
                data=str(e),
                index=self.index,
            )

    async def collect(self, stream: AsyncIterator[StreamChunk]) -> str:
        """Collect all tokens from a stream into a string."""
        parts: list[str] = []
        async for chunk in stream:
            if chunk.event == StreamEvent.TOKEN:
                parts.append(chunk.data)
            elif chunk.event == StreamEvent.ERROR:
                raise RuntimeError(chunk.data)
        return "".join(parts)

    def to_sse_stream(self, stream: AsyncIterator[StreamChunk]) -> AsyncIterator[str]:
        """Convert stream to SSE format for HTTP streaming."""

        async def _sse():
            async for chunk in stream:
                yield chunk.to_sse()

        return _sse()
