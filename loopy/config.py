"""v1.1 — ``loopy.yml`` configuration loader.

A small dataclass-backed config for the ``loopy init`` scaffold
and any future ``loopy dev`` / ``loopy serve`` features. Plain
YAML, no exotic deps (we already ship ``pyyaml`` via pydantic).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("loopy.config")


@dataclass
class LoopyConfig:
    """Parsed contents of a ``loopy.yml`` file.

    Defaults match the scaffold produced by ``loopy init``: a
    TestModel-backed agent with no interrupt gates and no
    remote connections, so the file works without any API
    key out of the box.
    """

    provider: str = "test"
    model: str = "TestModel"
    max_steps: int = 3
    interrupt_before: list[str] = field(default_factory=list)
    interrupt_after: list[str] = field(default_factory=list)
    policy_engine_path: str | None = None
    state_manager_path: str | None = None
    redactor_config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError(
                f"max_steps must be >= 1, got {self.max_steps} (see "
                "https://loopy.dev/docs/agent-loop#max-steps)"
            )
        if self.provider not in {"test", "openai", "anthropic", "ollama"}:
            raise ValueError(
                f"provider {self.provider!r} is not supported (allowed: "
                "test, openai, anthropic, ollama; see "
                "https://loopy.dev/docs/gateway#providers)"
            )


def load(path: str | Path) -> LoopyConfig:
    """Load and validate a ``loopy.yml`` file.

    Raises:
        FileNotFoundError: ``path`` does not exist.
        ValueError: the file is malformed YAML or violates the
            ``LoopyConfig`` invariants.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"loopy config not found at {file_path} (see https://loopy.dev/docs/init#loopy-yml)"
        )
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"malformed loopy.yml at {file_path}: {exc} (see https://loopy.dev/docs/init#loopy-yml)"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(
            f"loopy.yml at {file_path} must be a mapping, got "
            f"{type(raw).__name__} (see "
            "https://loopy.dev/docs/init#loopy-yml)"
        )
    try:
        return LoopyConfig(**raw)
    except TypeError as exc:
        raise ValueError(
            f"unknown keys in {file_path}: {exc} (see https://loopy.dev/docs/init#loopy-yml)"
        ) from exc
