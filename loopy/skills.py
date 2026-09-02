"""
Skills — Persistent Agent Knowledge.

Load and manage SKILL.md files for agent knowledge.
Inspired by loop-engineering's skills system.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.skills")


def _extract_triggers(section_content: list[str]) -> list[str]:
    """Extract triggers from section content lines."""
    return [
        line.strip().lstrip("- ").strip()
        for line in section_content
        if line.strip().startswith("-")
    ]


@dataclass
class Skill:
    """Persistent agent knowledge."""
    name: str
    description: str
    instructions: str
    triggers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, task: str) -> bool:
        """Check if task matches any trigger.

        Multi-word triggers require ALL words to appear in the task.
        Single-word triggers require a whole-word match (word boundary)
        to avoid false positives from substrings.
        """
        return self.score(task) > 0.0

    def score(self, task: str) -> float:
        """v0.7.8 — Return a relevance score in [0.0, 1.0+].

        Scoring rules:
        - Each multi-word trigger matched contributes +1.0 if every word is
          present in the task, +0.5 if only some words are present.
        - Each single-word trigger matched (whole-word) contributes +0.5.
        - Result is normalized by the number of triggers so a skill with
          many triggers doesn't dominate simply by volume. Final score is
          clamped at 1.0.
        """
        if not self.triggers:
            return 0.0

        task_lower = task.lower()
        total = 0.0

        for trigger in self.triggers:
            trigger_words = trigger.lower().split()
            if len(trigger_words) > 1:
                hits = sum(1 for w in trigger_words if w in task_lower)
                if hits == len(trigger_words):
                    total += 1.0
                elif hits > 0:
                    total += 0.5 * (hits / len(trigger_words))
            else:
                if re.search(r'\b' + re.escape(trigger_words[0]) + r'\b', task_lower):
                    total += 0.5

        return min(total / max(len(self.triggers), 1), 1.0)

    @classmethod
    def from_markdown(cls, content: str) -> Skill:
        """Parse skill from markdown content."""
        lines = content.strip().split("\n")

        # Extract title
        name = "Unnamed Skill"
        description = ""
        instructions = ""
        triggers: list[str] = []

        section = None
        section_content: list[str] = []

        for line in lines:
            if line.startswith("# "):
                name = line[2:].strip()
            elif line.startswith("## Purpose"):
                if section == "triggers":
                    triggers = _extract_triggers(section_content)
                elif section == "instructions":
                    instructions = "\n".join(section_content).strip()
                section = "purpose"
                section_content = []
            elif line.startswith("## Triggers"):
                if section == "purpose":
                    description = "\n".join(section_content).strip()
                elif section == "instructions":
                    instructions = "\n".join(section_content).strip()
                section = "triggers"
                section_content = []
            elif line.startswith("## Instructions"):
                if section == "purpose":
                    description = "\n".join(section_content).strip()
                elif section == "triggers":
                    triggers = _extract_triggers(section_content)
                section = "instructions"
                section_content = []
            elif line.startswith("## "):
                if section == "purpose":
                    description = "\n".join(section_content).strip()
                elif section == "triggers":
                    triggers = _extract_triggers(section_content)
                elif section == "instructions":
                    instructions = "\n".join(section_content).strip()
                section = None
                section_content = []
            elif section is not None:
                section_content.append(line)

        # Save last section
        if section == "purpose":
            description = "\n".join(section_content).strip()
        elif section == "triggers":
            triggers = _extract_triggers(section_content)
        elif section == "instructions":
            instructions = "\n".join(section_content).strip()

        # Fallback description from first paragraph
        if not description:
            for line in lines:
                if line.strip() and not line.startswith("#") and not line.startswith("##"):
                    description = line.strip()
                    break

        return cls(
            name=name,
            description=description or f"Skill: {name}",
            instructions=instructions,
            triggers=triggers,
        )


class SkillRegistry:
    """
    Load and manage skills.

    Example:
        registry = SkillRegistry()
        registry.load_directory("./skills")
        matched = registry.match("Fix CI workflow")
    """

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def add(self, skill: Skill) -> None:
        """Add a skill."""
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        """Get skill by name."""
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        """List all skills."""
        return list(self._skills.values())

    def match(self, task: str) -> list[Skill]:
        """Match skills to a task."""
        return [s for s in self._skills.values() if s.matches(task)]

    def match_ranked(
        self,
        task: str,
        min_score: float = 0.0,
        limit: int | None = None,
    ) -> list[tuple[Skill, float]]:
        """v0.7.8 — Return matched skills ordered by relevance score (desc).

        Args:
            task: Task description to match against.
            min_score: Drop matches below this score (default 0.0).
            limit: Cap on number of returned matches (default unlimited).

        Returns:
            List of ``(Skill, score)`` tuples, highest score first.
        """
        scored: list[tuple[Skill, float]] = []
        for skill in self._skills.values():
            score = skill.score(task)
            if score >= min_score:
                scored.append((skill, score))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        if limit is not None:
            scored = scored[:limit]
        return scored

    def match_one(self, task: str, min_score: float = 0.0) -> Skill | None:
        """v0.7.8 — Return the single best-matching skill, or None.

        Convenience wrapper around :meth:`match_ranked` for the common
        "pick one" case. Returns the highest-scoring skill above
        ``min_score``, or ``None`` if nothing qualifies.
        """
        ranked = self.match_ranked(task, min_score=min_score, limit=1)
        return ranked[0][0] if ranked else None

    def load_file(self, path: str) -> Skill:
        """Load a single skill file."""
        content = Path(path).read_text(encoding="utf-8")
        skill = Skill.from_markdown(content)
        self.add(skill)
        return skill

    def load_directory(self, directory: str) -> int:
        """Load all .md files from a directory."""
        dir_path = Path(directory)
        loaded = 0

        if not dir_path.exists():
            logger.warning("Skill directory not found: %s", directory)
            return 0

        for md_file in dir_path.glob("*.md"):
            try:
                self.load_file(str(md_file))
                loaded += 1
            except Exception as e:
                logger.error("Failed to load skill from %s: %s", md_file, e)

        return loaded
