"""Tests for loopy.streaming — Real-time token streaming."""

import pytest
import asyncio
from loopy.streaming import StreamEvent, StreamChunk, StreamBuffer, Streamer


class TestStreamEvent:
    def test_event_values(self):
        assert StreamEvent.TOKEN.value == "token"
        assert StreamEvent.DONE.value == "done"
        assert StreamEvent.ERROR.value == "error"


class TestStreamChunk:
    def test_chunk_creation(self):
        chunk = StreamChunk(event=StreamEvent.TOKEN, data="hello")
        assert chunk.event == StreamEvent.TOKEN
        assert chunk.data == "hello"

    def test_chunk_to_dict(self):
        chunk = StreamChunk(event=StreamEvent.TOKEN, data="hello", index=5)
        d = chunk.to_dict()
        assert d["event"] == "token"
        assert d["data"] == "hello"
        assert d["index"] == 5

    def test_chunk_to_sse(self):
        chunk = StreamChunk(event=StreamEvent.TOKEN, data="hello")
        sse = chunk.to_sse()
        assert "event: token" in sse
        assert "data:" in sse


class TestStreamBuffer:
    def test_buffer_creation(self):
        buf = StreamBuffer(flush_threshold=5)
        assert buf.total_tokens == 0

    def test_buffer_add(self):
        buf = StreamBuffer(flush_threshold=3)
        assert buf.add("a") is None
        assert buf.add("b") is None
        result = buf.add("c")
        assert result == "abc"
        assert buf.total_tokens == 3

    def test_buffer_flush(self):
        buf = StreamBuffer()
        buf.add("hello")
        buf.add(" ")
        buf.add("world")
        result = buf.flush()
        assert result == "hello world"
        assert buf.total_tokens == 3


class TestStreamer:
    def test_streamer_creation(self):
        s = Streamer()
        assert s.index == 0

    @pytest.mark.asyncio
    async def test_stream_collect(self):
        async def gen(prompt: str):
            for token in ["Hello", " ", "World"]:
                yield token

        s = Streamer()
        stream = s.stream(gen, "test")
        result = await s.collect(stream)
        assert result == "Hello World"
