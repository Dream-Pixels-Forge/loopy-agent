"""
Skills — Persistent Agent Knowledge.

Load and manage SKILL.md files for agent knowledge.
Inspired by loop-engineering's skills system.
"""

from __future__ import annotations

import logging
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
        """Check if task matches any trigger."""
        task_lower = task.lower()
        for trigger in self.triggers:
            # Check if trigger words appear in task
            trigger_words = trigger.lower().split()
            if any(word in task_lower for word in trigger_words):
                return True
        return False

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
            logger.warning(f"Skill directory not found: {directory}")
            return 0

        for md_file in dir_path.glob("*.md"):
            try:
                self.load_file(str(md_file))
                loaded += 1
            except Exception as e:
                logger.error(f"Failed to load skill from {md_file}: {e}")

        return loaded
