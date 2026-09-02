"""
Audio Plugin — Whisper/TTS integration.

Provides speech-to-text and text-to-speech capabilities.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loopy.plugins import Plugin, PluginInfo, PluginRegistry

logger = logging.getLogger("loopy.plugins.audio")


@dataclass
class AudioConfig:
    """Configuration for audio processing."""

    # STT settings
    stt_model: str = "whisper-1"
    stt_language: str = "en"

    # TTS settings
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_speed: float = 1.0

    # Provider
    provider: str = "openai"  # openai, elevenlabs, local


@dataclass
class TranscriptionResult:
    """Result of speech-to-text transcription."""

    text: str
    language: str = ""
    duration_ms: float = 0
    segments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SynthesisResult:
    """Result of text-to-speech synthesis."""

    audio_path: str
    duration_ms: float = 0
    format: str = "mp3"
    metadata: dict[str, Any] = field(default_factory=dict)


class SpeechToText:
    """
    Speech-to-text transcription.

    Example:
        stt = SpeechToText(api_key="sk-...")
        result = await stt.transcribe("audio.mp3")
        print(result.text)
    """

    def __init__(
        self,
        api_key: str | None = None,
        config: AudioConfig | None = None,
        provider_fn: Callable[[str, bytes], Awaitable[dict[str, Any]]] | None = None,
    ):
        self.api_key = api_key
        self.config = config or AudioConfig()
        self.provider_fn = provider_fn

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to audio file
            language: Optional language override

        Returns:
            TranscriptionResult with transcribed text
        """
        import time

        start_time = time.time()

        # Read audio file
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        if self.provider_fn:
            # Use custom provider
            result = await self.provider_fn(audio_path, audio_data)
            return TranscriptionResult(
                text=result.get("text", ""),
                language=result.get("language", language or self.config.stt_language),
                duration_ms=(time.time() - start_time) * 1000,
                segments=result.get("segments", []),
            )

        # Default: simple mock for testing
        return TranscriptionResult(
            text=f"[Transcription of {audio_path}]",
            language=language or self.config.stt_language,
            duration_ms=(time.time() - start_time) * 1000,
        )


class TextToSpeech:
    """
    Text-to-speech synthesis.

    Example:
        tts = TextToSpeech(api_key="sk-...")
        result = await tts.synthesize("Hello world!", output_path="output.mp3")
        print(result.audio_path)
    """

    def __init__(
        self,
        api_key: str | None = None,
        config: AudioConfig | None = None,
        provider_fn: Callable[[str, dict[str, Any]], Awaitable[bytes]] | None = None,
    ):
        self.api_key = api_key
        self.config = config or AudioConfig()
        self.provider_fn = provider_fn

    async def synthesize(
        self,
        text: str,
        output_path: str | None = None,
        voice: str | None = None,
        speed: float | None = None,
    ) -> SynthesisResult:
        """
        Synthesize speech from text.

        Args:
            text: Text to synthesize
            output_path: Optional output file path
            voice: Optional voice override
            speed: Optional speed override

        Returns:
            SynthesisResult with audio file path
        """
        import time

        start_time = time.time()

        voice = voice or self.config.tts_voice
        speed = speed or self.config.tts_speed
        output_path = output_path or "tts_output.mp3"

        if self.provider_fn:
            # Use custom provider
            audio_data = await self.provider_fn(
                text,
                {
                    "model": self.config.tts_model,
                    "voice": voice,
                    "speed": speed,
                },
            )

            with open(output_path, "wb") as f:
                f.write(audio_data)

            return SynthesisResult(
                audio_path=output_path,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Default: create placeholder file for testing
        with open(output_path, "wb") as f:
            f.write(b"")  # Empty placeholder

        return SynthesisResult(
            audio_path=output_path,
            duration_ms=(time.time() - start_time) * 1000,
        )


class AudioPlugin(Plugin):
    """
    Audio processing plugin for STT/TTS.

    Example:
        plugin = AudioPlugin(api_key="sk-...")
        await registry.load(plugin)

        stt = plugin.stt
        tts = plugin.tts

        # Transcribe
        result = await stt.transcribe("recording.mp3")

        # Synthesize
        result = await tts.synthesize("Hello world!")
    """

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="loopy-audio",
            version="0.4.0",
            description="Speech-to-text and text-to-speech for loopy",
            author="Dream Pixels Forge",
            capabilities=["tool", "audio"],
            requires=[],
        )

    async def setup(self, registry: PluginRegistry) -> None:
        """Initialize the Audio plugin."""
        self.config = AudioConfig()
        self.stt = SpeechToText(config=self.config)
        self.tts = TextToSpeech(config=self.config)

        # Register tools
        registry.register_tool("transcribe", self._transcribe)
        registry.register_tool("synthesize", self._synthesize)

        logger.info("Audio plugin initialized")

    async def _transcribe(self, audio_path: str, language: str | None = None) -> dict[str, Any]:
        """Transcribe audio to text."""
        result = await self.stt.transcribe(audio_path, language)
        return {
            "text": result.text,
            "language": result.language,
            "duration_ms": result.duration_ms,
        }

    async def _synthesize(self, text: str, output_path: str | None = None) -> dict[str, Any]:
        """Synthesize text to speech."""
        result = await self.tts.synthesize(text, output_path)
        return {
            "audio_path": result.audio_path,
            "duration_ms": result.duration_ms,
        }
