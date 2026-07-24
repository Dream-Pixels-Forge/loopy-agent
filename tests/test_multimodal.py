"""Tests for loopy.multimodal — Multi-modal content support."""

import pytest
import tempfile
import os
from loopy.multimodal import (
    MediaType, ImageFormat, MediaContent, MultiModalMessage, MultiModalBuilder,
)


class TestMediaType:
    def test_media_types(self):
        assert MediaType.IMAGE.value == "image"
        assert MediaType.AUDIO.value == "audio"
        assert MediaType.VIDEO.value == "video"


class TestMediaContent:
    def test_from_url(self):
        content = MediaContent.from_url("https://example.com/image.png")
        assert content.type == MediaType.IMAGE
        assert content.data == "https://example.com/image.png"

    def test_to_openai_url(self):
        content = MediaContent.from_url("https://example.com/image.png")
        result = content.to_openai()
        assert result["type"] == "image_url"
        assert result["image_url"]["url"] == "https://example.com/image.png"

    def test_to_anthropic_url(self):
        content = MediaContent.from_url("https://example.com/image.png")
        result = content.to_anthropic()
        assert result["type"] == "image"
        assert result["source"]["type"] == "url"

    def test_from_file(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            path = f.name
        try:
            content = MediaContent.from_file(path)
            assert content.type == MediaType.IMAGE
            assert content.mime_type == "image/png"
        finally:
            os.unlink(path)


class TestMultiModalMessage:
    def test_message_creation(self):
        msg = MultiModalMessage(text="Hello")
        assert msg.text == "Hello"
        assert msg.has_media is False

    def test_message_with_images(self):
        img = MediaContent.from_url("https://example.com/img.png")
        msg = MultiModalMessage(text="Describe this", media=[img])
        assert msg.has_media is True
        assert len(msg.images) == 1


class TestMultiModalBuilder:
    def test_builder_text(self):
        msg = (MultiModalBuilder()
            .text("What's this?")
            .build())
        assert msg.text == "What's this?"
        assert msg.has_media is False

    def test_builder_with_url_image(self):
        msg = (MultiModalBuilder()
            .text("Describe")
            .image("https://example.com/img.png")
            .build())
        assert msg.has_media is True
        assert len(msg.images) == 1
