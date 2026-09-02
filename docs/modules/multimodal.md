# `loopy.multimodal` — Multi-modal + Realtime (voice)

Image, audio, and video support for agent loops. v0.7.10 adds
`RealtimeSession` for voice-first agents.

## Image messages

```python
from loopy import MultiModalBuilder

msg = (MultiModalBuilder()
    .text("What's in this image?")
    .image("photo.jpg")
    .image("https://example.com/chart.png")
    .build())
```

## Realtime voice session

`RealtimeSession` is an async iterator over normalized realtime
events. The WebSocket transport itself is pluggable — loopy ships no
hard dependency on `websockets`. Users wire in their preferred client.

```python
from loopy import RealtimeSession

class MyOpenAITransport:
    async def send(self, payload): ...
    async def recv(self): ...
    async def close(self): ...

async with RealtimeSession(MyOpenAITransport()) as session:
    await session.send({"type": "session.update", "session": {...}})
    async for event in session:
        if event.type.name == "TRANSCRIPT_DELTA":
            print(event.transcript, end="", flush=True)
```

For a working `websockets`-based transport, install the optional extra:

```bash
pip install loopy-agent[voice]
```

## API

| Symbol | Purpose |
|---|---|
| `MediaContent` | A piece of image/audio/video data |
| `MediaType` | IMAGE / AUDIO / VIDEO / DOCUMENT |
| `MultiModalMessage` | Text + media bundle |
| `MultiModalBuilder` | Fluent builder |
| `RealtimeSession` | Async iterator over realtime events |
| `RealtimeEvent` | Normalized event with `.transcript`, `.audio_bytes` |
| `RealtimeEventType` | SESSION_CREATED / TRANSCRIPT_DELTA / AUDIO_DELTA / TOOL_CALL / ERROR / CLOSED |
| `RealtimeTransport` | Protocol users implement with their WebSocket library |