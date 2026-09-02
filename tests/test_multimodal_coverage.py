"""Multi-modal coverage tests — format conversion, builder, file loading."""

from __future__ import annotations

import base64

from loopy.multimodal import (
    MediaContent,
    MediaType,
    MultiModalBuilder,
    MultiModalMessage,
)


class TestMediaContent:
    def test_to_openai_url(self):
        mc = MediaContent.from_url("https://example.com/img.png", MediaType.IMAGE)
        fmt = mc.to_openai()
        assert fmt["type"] == "image_url"
        assert "url" in fmt["image_url"]

    def test_to_openai_base64(self):
        mc = MediaContent(
            type=MediaType.IMAGE,
            mime_type="image/png",
            data=base64.b64encode(b"fake").decode(),
        )
        fmt = mc.to_openai()
        assert "data:image/png;base64," in fmt["image_url"]["url"]

    def test_to_anthropic_url(self):
        mc = MediaContent.from_url("https://example.com/img.png", MediaType.IMAGE)
        fmt = mc.to_anthropic()
        assert fmt["type"] == "image"
        assert fmt["source"]["type"] == "url"

    def test_to_anthropic_base64(self):
        mc = MediaContent(
            type=MediaType.IMAGE,
            mime_type="image/png",
            data=base64.b64encode(b"fake").decode(),
        )
        fmt = mc.to_anthropic()
        assert fmt["source"]["type"] == "base64"


class TestMultiModalMessage:
    def test_to_openai(self):
        mc = MediaContent.from_url("https://example.com/img.png", MediaType.IMAGE)
        msg = MultiModalMessage(text="Look at this", media=[mc])
        openai = msg.to_openai()
        assert len(openai) == 2  # image + text
        assert openai[0]["type"] == "image_url"
        assert openai[1]["type"] == "text"

    def test_to_anthropic(self):
        mc = MediaContent.from_url("https://example.com/img.png", MediaType.IMAGE)
        msg = MultiModalMessage(text="Describe this", media=[mc])
        anthropic = msg.to_anthropic()
        assert len(anthropic) == 2
        assert anthropic[0]["type"] == "image"
        assert anthropic[1]["type"] == "text"

    def test_properties(self):
        msg = MultiModalMessage(text="hi", media=[])
        assert msg.has_media is False
        assert msg.images == []
        assert msg.audio == []


class TestMultiModalBuilder:
    def test_build_text_only(self):
        msg = MultiModalBuilder().text("Hello").build()
        assert msg.text == "Hello"
        assert msg.media == []

    def test_add_image_url(self):
        msg = MultiModalBuilder().text("Describe").image("https://example.com/img.png").build()
        assert len(msg.media) == 1
        assert msg.media[0].type == MediaType.IMAGE

    def test_add_audio_url(self):
        msg = MultiModalBuilder().audio("https://example.com/audio.mp3").build()
        assert msg.media[0].type == MediaType.AUDIO

    def test_add_image_local_file(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n")
        msg = MultiModalBuilder().image(str(img)).build()
        assert msg.media[0].mime_type == "image/png"
        # from_file stores raw base64; to_openai() wraps it
        import base64

        assert base64.b64decode(msg.media[0].data) == b"\x89PNG\r\n"

    def test_add_audio_local_file(self, tmp_path):
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"ID3")
        msg = MultiModalBuilder().audio(str(audio)).build()
        assert msg.media[0].mime_type == "audio/mpeg"

    def test_add_file(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")
        msg = MultiModalBuilder().file(str(f)).build()
        assert msg.media[0].mime_type == "application/pdf"

    def test_chaining(self):
        msg = (
            MultiModalBuilder()
            .text("All media")
            .image("https://a.com/1.png")
            .audio("https://b.com/2.mp3")
            .build()
        )
        assert len(msg.media) == 2
        assert msg.text == "All media"
