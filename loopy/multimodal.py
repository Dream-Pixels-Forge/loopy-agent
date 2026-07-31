"""
Multi-modal — Image, audio, video support for agent loops.

Critical gap: 2026 agents must see, hear, and speak.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.multimodal")


class MediaType(str, Enum):
    """Supported media types."""
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


class ImageFormat(str, Enum):
    """Image formats."""
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"
    GIF = "gif"


@dataclass
class MediaContent:
    """A piece of media content."""
    type: MediaType
    data: str  # base64 or URL
    mime_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str) -> MediaContent:
        """Load media from file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Media file not found: {path}")

        suffix = file_path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".mp4": "video/mp4",
            ".pdf": "application/pdf",
        }

        mime_type = mime_map.get(suffix, "application/octet-stream")
        media_type = MediaType.IMAGE if mime_type.startswith("image/") else \
                     MediaType.AUDIO if mime_type.startswith("audio/") else \
                     MediaType.VIDEO if mime_type.startswith("video/") else \
                     MediaType.DOCUMENT

        data = base64.b64encode(file_path.read_bytes()).decode()
        return cls(
            type=media_type,
            data=data,
            mime_type=mime_type,
            metadata={"filename": file_path.name, "size": file_path.stat().st_size},
        )

    @classmethod
    def from_url(cls, url: str, media_type: MediaType = MediaType.IMAGE) -> MediaContent:
        """Create media from URL (no download)."""
        return cls(
            type=media_type,
            data=url,
            metadata={"url": url},
        )

    def to_openai(self) -> dict[str, Any]:
        """Convert to OpenAI vision API format.

        Returns a dict suitable for use in the ``content`` array
        of an OpenAI chat completion request.
        """
        if self.data.startswith(("http://", "https://")):
            return {"type": "image_url", "image_url": {"url": self.data}}
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{self.mime_type};base64,{self.data}"},
        }

    def to_anthropic(self) -> dict[str, Any]:
        """Convert to Anthropic Messages API format.

        Returns a dict suitable for use in the ``content`` array
        of an Anthropic message request.
        """
        if self.data.startswith(("http://", "https://")):
            return {"type": "image", "source": {"type": "url", "url": self.data}}
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": self.mime_type, "data": self.data},
        }


@dataclass
class MultiModalMessage:
    """A message with text and media content."""
    text: str
    media: list[MediaContent] = field(default_factory=list)

    @property
    def has_media(self) -> bool:
        return len(self.media) > 0

    @property
    def images(self) -> list[MediaContent]:
        return [m for m in self.media if m.type == MediaType.IMAGE]

    @property
    def audio(self) -> list[MediaContent]:
        return [m for m in self.media if m.type == MediaType.AUDIO]

    def to_openai(self) -> list[dict[str, Any]]:
        """Convert to OpenAI multi-modal format."""
        content: list[dict[str, Any]] = []

        # Add images first
        for media in self.media:
            if media.type == MediaType.IMAGE:
                content.append(media.to_openai())

        # Add text
        if self.text:
            content.append({"type": "text", "text": self.text})

        return content

    def to_anthropic(self) -> list[dict[str, Any]]:
        """Convert to Anthropic multi-modal format."""
        content: list[dict[str, Any]] = []

        for media in self.media:
            content.append(media.to_anthropic())

        if self.text:
            content.append({"type": "text", "text": self.text})

        return content


class MultiModalBuilder:
    """
    Build multi-modal messages easily.

    Example:
        msg = (MultiModalBuilder()
            .text("What's in this image?")
            .image("photo.jpg")
            .image("https://example.com/chart.png")
            .build())
    """

    def __init__(self):
        self._text = ""
        self._media: list[MediaContent] = []

    def text(self, content: str) -> MultiModalBuilder:
        """Add text content."""
        self._text = content
        return self

    def image(self, source: str) -> MultiModalBuilder:
        """Add image from file or URL."""
        if source.startswith(("http://", "https://")):
            self._media.append(MediaContent.from_url(source, MediaType.IMAGE))
        else:
            self._media.append(MediaContent.from_file(source))
        return self

    def audio(self, source: str) -> MultiModalBuilder:
        """Add audio from file or URL."""
        if source.startswith(("http://", "https://")):
            self._media.append(MediaContent.from_url(source, MediaType.AUDIO))
        else:
            self._media.append(MediaContent.from_file(source))
        return self

    def file(self, path: str) -> MultiModalBuilder:
        """Add any file as media."""
        self._media.append(MediaContent.from_file(path))
        return self

    def build(self) -> MultiModalMessage:
        """Build the multi-modal message."""
        return MultiModalMessage(text=self._text, media=self._media)
