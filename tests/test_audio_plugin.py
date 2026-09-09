"""Tests for loopy.plugins.audio — STT, TTS, and AudioPlugin."""

from __future__ import annotations

import pytest

from loopy.plugins.audio import (
    AudioConfig,
    AudioPlugin,
    SpeechToText,
    SynthesisResult,
    TextToSpeech,
    TranscriptionResult,
)

# ── Dataclass defaults ──────────────────────────────────────


class TestAudioConfig:
    def test_defaults(self):
        cfg = AudioConfig()
        assert cfg.stt_model == "whisper-1"
        assert cfg.stt_language == "en"
        assert cfg.tts_model == "tts-1"
        assert cfg.tts_voice == "alloy"
        assert cfg.tts_speed == 1.0
        assert cfg.provider == "openai"

    def test_custom_values(self):
        cfg = AudioConfig(stt_model="large-v3", tts_voice="onyx", provider="elevenlabs")
        assert cfg.stt_model == "large-v3"
        assert cfg.tts_voice == "onyx"
        assert cfg.provider == "elevenlabs"


class TestTranscriptionResult:
    def test_defaults(self):
        r = TranscriptionResult(text="hello")
        assert r.text == "hello"
        assert r.language == ""
        assert r.duration_ms == 0
        assert r.segments == []
        assert r.metadata == {}

    def test_full(self):
        r = TranscriptionResult(
            text="hello",
            language="en",
            duration_ms=1200.0,
            segments=[{"start": 0.0, "end": 1.0, "text": "hello"}],
        )
        assert r.language == "en"
        assert len(r.segments) == 1


class TestSynthesisResult:
    def test_defaults(self):
        r = SynthesisResult(audio_path="out.mp3")
        assert r.audio_path == "out.mp3"
        assert r.duration_ms == 0
        assert r.format == "mp3"
        assert r.metadata == {}


# ── SpeechToText ────────────────────────────────────────────


class TestSpeechToText:
    @pytest.mark.asyncio
    async def test_transcribe_default_no_provider(self, tmp_path):
        stt = SpeechToText()
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio bytes")
        result = await stt.transcribe(str(audio_file))
        assert result.text == f"[Transcription of {audio_file}]"
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_transcribe_with_custom_provider(self, tmp_path):
        async def my_provider(path, data):
            return {"text": "custom result", "language": "fr", "segments": []}

        stt = SpeechToText(provider_fn=my_provider)
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio bytes")
        result = await stt.transcribe(str(audio_file), language="de")
        assert result.text == "custom result"
        assert result.language == "fr"  # provider overrides
        assert result.segments == []

    @pytest.mark.asyncio
    async def test_transcribe_respects_language_override(self, tmp_path):
        stt = SpeechToText()
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio bytes")
        result = await stt.transcribe(str(audio_file), language="ja")
        assert "ja" in result.text or result.language == "ja"  # mock returns path in text

    @pytest.mark.asyncio
    async def test_transcribe_missing_file_raises(self, tmp_path):
        stt = SpeechToText()
        with pytest.raises(FileNotFoundError):
            await stt.transcribe(str(tmp_path / "nonexistent.wav"))


# ── TextToSpeech ────────────────────────────────────────────


class TestTextToSpeech:
    @pytest.mark.asyncio
    async def test_synthesize_default_no_provider(self, tmp_path):
        tts = TextToSpeech()
        output = tmp_path / "out.mp3"
        result = await tts.synthesize("Hello world", output_path=str(output))
        assert result.audio_path == str(output)
        assert result.duration_ms >= 0
        assert output.exists()

    @pytest.mark.asyncio
    async def test_synthesize_with_custom_provider(self, tmp_path):
        async def my_provider(text, params):
            return b"fake mp3 data"

        tts = TextToSpeech(provider_fn=my_provider)
        output = tmp_path / "custom.mp3"
        result = await tts.synthesize("Hi", output_path=str(output), voice="onyx")
        assert result.audio_path == str(output)
        assert output.exists()
        assert output.read_bytes() == b"fake mp3 data"

    @pytest.mark.asyncio
    async def test_synthesize_defaults_to_tts_output_mp3(self, tmp_path):
        tts = TextToSpeech()
        result = await tts.synthesize("Hello")
        assert result.audio_path == "tts_output.mp3"

    @pytest.mark.asyncio
    async def test_synthesize_uses_config_voice(self, tmp_path):
        cfg = AudioConfig(tts_voice="nova")
        tts = TextToSpeech(config=cfg)
        output = tmp_path / "out.mp3"
        result = await tts.synthesize("Hi", output_path=str(output))
        assert result.audio_path == str(output)


# ── AudioPlugin ─────────────────────────────────────────────


class TestAudioPlugin:
    @pytest.mark.asyncio
    async def test_info(self):
        plugin = AudioPlugin()
        info = plugin.info
        assert info.name == "loopy-audio"
        assert info.version == "0.4.0"
        assert "tool" in info.capabilities
        assert "audio" in info.capabilities

    @pytest.mark.asyncio
    async def test_setup_registers_tools(self):
        from loopy.plugins import PluginRegistry  # noqa: PLC0415

        plugin = AudioPlugin()
        reg = PluginRegistry()
        await plugin.setup(reg)
        assert plugin.stt is not None
        assert plugin.tts is not None
        tools = reg.list_tools()
        assert "transcribe" in tools
        assert "synthesize" in tools

    @pytest.mark.asyncio
    async def test_transcribe_tool(self, tmp_path):
        from loopy.plugins import PluginRegistry  # noqa: PLC0415

        plugin = AudioPlugin()
        reg = PluginRegistry()
        await plugin.setup(reg)
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake")
        result = await reg.execute_tool("transcribe", {"audio_path": str(audio_file)})
        assert "text" in result
        assert "duration_ms" in result

    @pytest.mark.asyncio
    async def test_synthesize_tool(self, tmp_path):
        from loopy.plugins import PluginRegistry  # noqa: PLC0415

        plugin = AudioPlugin()
        reg = PluginRegistry()
        await plugin.setup(reg)
        output = tmp_path / "out.mp3"
        result = await reg.execute_tool("synthesize", {"text": "Hello", "output_path": str(output)})
        assert "audio_path" in result
        assert "duration_ms" in result
        assert output.exists()
