"""Streaming coverage tests — error paths, SSE, buffer flush."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from loopy.streaming import StreamBuffer, StreamChunk, Streamer, StreamEvent


class TestStreamBuffer:
    def test_auto_flush_on_threshold(self):
        buf = StreamBuffer(flush_threshold=3)
        assert buf.add("a") is None
        assert buf.add("b") is None
        result = buf.add("c")
        assert result == "abc"

    def test_pending(self):
        buf = StreamBuffer(flush_threshold=10)
        buf.add("hello")
        assert buf.pending == "hello"

    def test_flush_empty(self):
        buf = StreamBuffer()
        assert buf.flush() == ""

    def test_total_tokens(self):
        buf = StreamBuffer(flush_threshold=100)
        buf.add("a")
        buf.add("b")
        buf.add("c")
        assert buf.total_tokens == 3


class TestStreamer:
    @pytest.mark.asyncio
    async def test_stream_collects(self):
        async def gen(prompt: str) -> AsyncIterator[str]:
            for word in ["Hello", " ", "World"]:
                yield word

        streamer = Streamer(buffer_size=100)
        result = await streamer.collect(streamer.stream(gen, "test"))
        assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_stream_yields_done(self):
        async def gen(prompt: str) -> AsyncIterator[str]:
            yield "x"

        streamer = Streamer(buffer_size=100)
        events = []
        async for chunk in streamer.stream(gen, "test"):
            events.append(chunk.event)

        assert StreamEvent.DONE in events

    @pytest.mark.asyncio
    async def test_stream_error_yields_error_event(self):
        async def bad_gen(prompt: str) -> AsyncIterator[str]:
            raise RuntimeError("gen failed")
            yield  # make it async generator

        streamer = Streamer(buffer_size=100)
        events = []
        async for chunk in streamer.stream(bad_gen, "test"):
            events.append(chunk.event)

        assert StreamEvent.ERROR in events

    @pytest.mark.asyncio
    async def test_collect_raises_on_error(self):
        async def bad_gen(prompt: str) -> AsyncIterator[str]:
            raise RuntimeError("boom")
            yield

        streamer = Streamer(buffer_size=100)
        with pytest.raises(RuntimeError, match="boom"):
            await streamer.collect(streamer.stream(bad_gen, "test"))

    @pytest.mark.asyncio
    async def test_buffered_flush_yields_metadata(self):
        async def gen(prompt: str) -> AsyncIterator[str]:
            for c in "abcde":
                yield c

        streamer = Streamer(buffer_size=3)
        flushed_chunks = []
        async for chunk in streamer.stream(gen, "test"):
            if chunk.metadata.get("flushed") or chunk.metadata.get("final"):
                flushed_chunks.append(chunk)

        assert len(flushed_chunks) >= 1


class TestStreamChunk:
    def test_to_dict(self):
        chunk = StreamChunk(event=StreamEvent.TOKEN, data="hi", index=0)
        d = chunk.to_dict()
        assert d["event"] == "token"
        assert d["data"] == "hi"

    def test_to_sse(self):
        chunk = StreamChunk(event=StreamEvent.TOKEN, data="hi", index=0)
        sse = chunk.to_sse()
        assert sse.startswith("event: token")
        assert "data:" in sse


class TestSSEStream:
    @pytest.mark.asyncio
    async def test_to_sse_stream(self):
        async def gen(prompt: str) -> AsyncIterator[str]:
            yield "x"

        streamer = Streamer(buffer_size=100)
        sse_gen = streamer.to_sse_stream(streamer.stream(gen, "test"))
        chunks = []
        async for sse in sse_gen:
            chunks.append(sse)
        assert len(chunks) > 0
        assert chunks[0].startswith("event:")
