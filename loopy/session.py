"""
Session — Advanced session management with transcript-level resume.

Provides session objects that persist conversation history (transcripts),
track message origins (system/agent/user/tool), and support resumable
execution across process boundaries.

Inspired by claude-agent-sdk's transcript-level session resume.
Docs: https://loopy.dev/docs/session
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.session")


class MessageOrigin(str, Enum):
    """Who generated a message in the transcript."""

    SYSTEM = "system"
    AGENT = "agent"
    USER = "user"
    TOOL = "tool"


@dataclass
class TranscriptEntry:
    """A single message in a session transcript."""

    role: MessageOrigin
    content: str
    timestamp: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "entry_id": self.entry_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TranscriptEntry:
        return cls(
            role=MessageOrigin(d["role"]),
            content=d["content"],
            timestamp=d.get("timestamp", time.monotonic()),
            metadata=d.get("metadata", {}),
            entry_id=d.get("entry_id", uuid.uuid4().hex[:8]),
        )


@dataclass
class SessionConfig:
    """Configuration for a session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    max_transcript_length: int = 500
    persist_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Session:
    """A conversation session with transcript and persistence.

    Sessions accumulate :class:`TranscriptEntry` records. They can be
    persisted to disk and resumed later, restoring the full transcript
    so an agent can continue from exactly where it left off.

    Example:
        >>> session = Session()
        >>> session.append("system", "You are a helpful assistant.")
        >>> session.append("user", "Hello!")
        >>> await session.save("/tmp/session.json")
        >>> resumed = await Session.load("/tmp/session.json")
    """

    def __init__(self, config: SessionConfig | None = None) -> None:
        self.config = config or SessionConfig()
        self._transcript: list[TranscriptEntry] = []
        self._created_at: float = time.monotonic()
        self._last_active: float = self._created_at

    @property
    def session_id(self) -> str:
        return self.config.session_id

    @property
    def transcript(self) -> list[TranscriptEntry]:
        return list(self._transcript)

    @property
    def entry_count(self) -> int:
        return len(self._transcript)

    def append(
        self,
        role: MessageOrigin | str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptEntry:
        """Add a message to the transcript.

        Args:
            role: Message origin — a :class:`MessageOrigin` or its string value.
            content: Message text.
            metadata: Optional per-message metadata.

        Returns:
            The appended :class:`TranscriptEntry`.
        """
        if isinstance(role, str):
            role = MessageOrigin(role)
        entry = TranscriptEntry(role=role, content=content, metadata=metadata or {})
        self._transcript.append(entry)
        self._last_active = time.monotonic()

        # Trim transcript if it exceeds max length.
        if len(self._transcript) > self.config.max_transcript_length:
            excess = len(self._transcript) - self.config.max_transcript_length
            self._transcript = self._transcript[excess:]
            logger.debug(
                "Trimmed %d entries from transcript for session %s",
                excess,
                self.session_id,
            )

        return entry

    def append_system(self, content: str, **kw: Any) -> TranscriptEntry:
        return self.append(MessageOrigin.SYSTEM, content, **kw)

    def append_agent(self, content: str, **kw: Any) -> TranscriptEntry:
        return self.append(MessageOrigin.AGENT, content, **kw)

    def append_user(self, content: str, **kw: Any) -> TranscriptEntry:
        return self.append(MessageOrigin.USER, content, **kw)

    def append_tool(self, content: str, **kw: Any) -> TranscriptEntry:
        return self.append(MessageOrigin.TOOL, content, **kw)

    def clear(self) -> None:
        self._transcript.clear()

    def recent(self, n: int = 20) -> list[TranscriptEntry]:
        return list(self._transcript[-n:])

    def last_n_by_role(self, role: MessageOrigin | str, n: int = 10) -> list[TranscriptEntry]:
        if isinstance(role, str):
            role = MessageOrigin(role)
        return [e for e in reversed(self._transcript) if e.role == role][:n][::-1]

    async def save(self, path: str | Path | None = None) -> Path:
        """Persist the session to disk.

        Args:
            path: Destination path. Defaults to :attr:`config.persist_path`.

        Returns:
            The path the session was saved to.
        """
        dest = Path(path or self.config.persist_path or f"session-{self.session_id}.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": self.session_id,
            "created_at": self._created_at,
            "last_active": self._last_active,
            "config": {
                "max_transcript_length": self.config.max_transcript_length,
                "metadata": self.config.metadata,
            },
            "transcript": [e.to_dict() for e in self._transcript],
        }
        dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.debug(
            "Saved session %s to %s (%d entries)",
            self.session_id,
            dest,
            len(self._transcript),
        )
        return dest

    @classmethod
    async def load(cls, path: str | Path) -> Session:
        """Load a session from disk.

        Args:
            path: Path to a previously saved session file.

        Returns:
            A new :class:`Session` populated with the loaded transcript.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Session file not found: {p}")
        payload = json.loads(p.read_text(encoding="utf-8"))
        config = SessionConfig(
            session_id=payload.get("session_id", uuid.uuid4().hex),
            persist_path=str(p),
            max_transcript_length=payload.get("config", {}).get("max_transcript_length", 500),
            metadata=payload.get("config", {}).get("metadata", {}),
        )
        session = cls(config=config)
        session._created_at = payload.get("created_at", time.monotonic())
        session._last_active = payload.get("last_active", session._created_at)
        for entry_dict in payload.get("transcript", []):
            session._transcript.append(TranscriptEntry.from_dict(entry_dict))
        logger.debug(
            "Loaded session %s from %s (%d entries)",
            session.session_id,
            p,
            len(session._transcript),
        )
        return session


class SessionManager:
    """In-memory store with optional disk persistence for sessions.

    Manages multiple sessions, auto-saves on ``append``, and provides
    resume-by-id for long-running agent workflows.
    """

    def __init__(
        self,
        auto_save_path: str | Path | None = None,
        auto_save_fn: Callable[[Session, Path], Any] | None = None,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._auto_save_path = auto_save_path
        self._auto_save_fn = auto_save_fn

    async def create(self, config: SessionConfig | None = None) -> Session:
        """Create and track a new session."""
        session = Session(config)
        self._sessions[session.session_id] = session
        return session

    async def get(self, session_id: str) -> Session | None:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    async def list_sessions(self) -> list[Session]:
        """List all tracked sessions."""
        return list(self._sessions.values())

    async def remove(self, session_id: str) -> bool:
        """Remove a session. Returns True if it existed."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def save_all(self) -> list[Path]:
        """Persist all sessions to disk (if auto_save_path is set)."""
        if self._auto_save_path is None:
            return []
        saved: list[Path] = []
        for session in self._sessions.values():
            p = await session.save(self._auto_save_path / f"session-{session.session_id}.json")
            saved.append(p)
            if self._auto_save_fn is not None:
                self._auto_save_fn(session, p)
        return saved
