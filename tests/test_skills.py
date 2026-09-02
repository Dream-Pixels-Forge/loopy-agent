"""Tests for loopy.skills — Persistent Agent Knowledge."""

import os
import tempfile

from loopy.skills import (
    Skill,
    SkillRegistry,
)


class TestSkill:
    def test_skill_creation(self):
        """Test skill creation."""
        skill = Skill(
            name="ci-triage",
            description="Triage CI failures",
            instructions="Check flaky tests first",
            triggers=["ci failed", "tests failing"],
        )
        assert skill.name == "ci-triage"
        assert len(skill.triggers) == 2

    def test_skill_from_markdown(self):
        """Test skill creation from markdown."""
        md = """# CI Triage

## Purpose
Triage CI failures.

## Triggers
- CI workflow failed
- Tests failing

## Instructions
1. Check if flaky
2. Analyze errors
3. Create fix if safe
"""
        skill = Skill.from_markdown(md)
        assert skill.name == "CI Triage"
        assert "triage" in skill.description.lower() or "ci" in skill.description.lower()
        assert len(skill.triggers) > 0

    def test_skill_matches(self):
        """Test skill trigger matching."""
        skill = Skill(
            name="ci-triage",
            description="Triage CI failures",
            instructions="Check flaky tests first",
            triggers=["ci failed", "tests failing", "build broken"],
        )
        assert skill.matches("CI workflow failed") is True
        assert skill.matches("tests failing on main") is True
        assert skill.matches("unrelated task") is False


class TestSkillRegistry:
    def test_registry_creation(self):
        """Test registry creation."""
        registry = SkillRegistry()
        assert registry is not None

    def test_add_skill(self):
        """Test adding skills."""
        registry = SkillRegistry()
        skill = Skill(
            name="test-skill",
            description="Test",
            instructions="Do stuff",
            triggers=["test"],
        )
        registry.add(skill)
        assert len(registry.list_all()) == 1

    def test_get_skill(self):
        """Test getting skill by name."""
        registry = SkillRegistry()
        skill = Skill(
            name="my-skill",
            description="Test",
            instructions="Do stuff",
            triggers=["test"],
        )
        registry.add(skill)
        found = registry.get("my-skill")
        assert found is not None
        assert found.name == "my-skill"

    def test_match_skills(self):
        """Test matching skills to task."""
        registry = SkillRegistry()
        registry.add(
            Skill(
                name="ci",
                description="CI stuff",
                instructions="Fix CI",
                triggers=["ci failed", "build broken"],
            )
        )
        registry.add(
            Skill(
                name="deploy",
                description="Deploy stuff",
                instructions="Deploy",
                triggers=["deploy", "release"],
            )
        )

        matched = registry.match("CI workflow failed")
        assert len(matched) >= 1
        assert any(s.name == "ci" for s in matched)

    def test_load_from_directory(self):
        """Test loading skills from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create skill file
            skill_md = """# Test Skill

## Purpose
Test purpose.

## Triggers
- test trigger

## Instructions
Test instructions.
"""
            with open(os.path.join(tmpdir, "test-skill.md"), "w") as f:
                f.write(skill_md)

            registry = SkillRegistry()
            loaded = registry.load_directory(tmpdir)
            assert loaded >= 1
            assert len(registry.list_all()) >= 1

    def test_load_from_file(self):
        """Test loading single skill file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("""# My Skill

## Purpose
Important skill.

## Triggers
- trigger one
- trigger two

## Instructions
Do things.
""")
            path = f.name

        try:
            registry = SkillRegistry()
            skill = registry.load_file(path)
            assert skill.name == "My Skill"
            assert len(skill.triggers) == 2
        finally:
            os.unlink(path)
