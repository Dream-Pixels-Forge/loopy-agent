"""Extended tests for loopy.skills — match_ranked, match_one, and edge cases."""

from __future__ import annotations

from loopy.skills import Skill, SkillRegistry


class TestSkillScore:
    def test_no_triggers_returns_zero(self):
        skill = Skill(name="s", description="d", instructions="i")
        assert skill.score("anything") == 0.0
        assert not skill.matches("anything")

    def test_single_word_trigger_exact(self):
        skill = Skill(name="s", description="d", instructions="i", triggers=["ci"])
        # Whole-word match should succeed; substring should not
        assert skill.score("ci failed") > 0.0
        assert skill.matches("ci failed")
        assert not skill.matches("sci-fi movie")  # substring mismatch

    def test_single_word_trigger_case_insensitive(self):
        skill = Skill(name="s", description="d", instructions="i", triggers=["deploy"])
        assert skill.score("DEPLOY the app") > 0.0
        assert skill.matches("DEPLOY the app")

    def test_multi_word_trigger_all_words(self):
        skill = Skill(name="s", description="d", instructions="i", triggers=["build broken"])
        assert skill.score("the build is broken") > 0.0
        assert skill.matches("the build is broken")

    def test_multi_word_trigger_partial_words(self):
        skill = Skill(name="s", description="d", instructions="i", triggers=["build broken"])
        # Partial match gives lower score but still > 0
        score = skill.score("the build process")
        assert 0.0 < score <= 1.0

    def test_multi_word_trigger_partial_words_fallback_branch(self):
        """Partial word match exercises total += 0.5 * (hits/n) branch."""
        skill = Skill(name="s", description="d", instructions="i", triggers=["deploy app"])
        # "deploy" present but "app" missing → partial match score
        score = skill.score("deploy the service")
        assert 0.0 < score < 1.0  # 0.5 * (1/2) = 0.25

    def test_multi_word_trigger_no_match(self):
        skill = Skill(name="s", description="d", instructions="i", triggers=["build broken"])
        assert skill.score("nothing to see") == 0.0
        assert not skill.matches("nothing to see")

    def test_score_normalized_by_trigger_count(self):
        skill = Skill(
            name="s",
            description="d",
            instructions="i",
            triggers=["ci", "build", "test", "deploy"],
        )
        # One trigger matches → 0.5 / 4 = 0.125
        score = skill.score("ci pipeline failed")
        assert 0.0 < score < 0.5

    def test_score_clamped_at_one(self):
        skill = Skill(
            name="s",
            description="d",
            instructions="i",
            triggers=["ci failed", "build broken", "test red"],
        )
        score = skill.score("ci failed and build broken and test red")
        assert score == 1.0  # clamped


class TestSkillFromMarkdown:
    def test_parses_name_and_purpose(self):
        md = "# Deploy Bot\n\n## Purpose\nHandles deployments\n\n## Instructions\nRun deploy script"
        skill = Skill.from_markdown(md)
        assert skill.name == "Deploy Bot"
        assert "deploy" in skill.description.lower()

    def test_parses_triggers(self):
        md = (
            "# CI Skill\n\n"
            "## Purpose\nTriage CI\n\n"
            "## Triggers\n- ci failed\n- tests broken\n\n"
            "## Instructions\nFix it"
        )
        skill = Skill.from_markdown(md)
        assert len(skill.triggers) == 2
        assert "ci failed" in skill.triggers
        assert "tests broken" in skill.triggers

    def test_parses_instructions(self):
        md = (
            "# Debug Skill\n\n"
            "## Purpose\nDebug issues\n\n"
            "## Triggers\n- bug\n\n"
            "## Instructions\nRead the logs carefully"
        )
        skill = Skill.from_markdown(md)
        assert "logs" in skill.instructions.lower()

    def test_fallback_description_from_body(self):
        md = "# Odd Skill\n\nSome body text here.\n\n## Instructions\nDo it"
        skill = Skill.from_markdown(md)
        assert skill.name == "Odd Skill"
        # Fallback description from first non-header body line
        assert "body text" in skill.description.lower()

    def test_empty_content_uses_name_as_fallback(self):
        md = "# My Skill\n\n"
        skill = Skill.from_markdown(md)
        assert skill.name == "My Skill"
        assert skill.description == "Skill: My Skill"

    def test_triggers_before_purpose(self):
        """Section ordering: triggers first, then purpose."""
        md = (
            "# Order Skill\n\n"
            "## Triggers\n- ci failed\n\n"
            "## Purpose\nOrder matters\n\n"
            "## Instructions\nDo it"
        )
        skill = Skill.from_markdown(md)
        assert "ci failed" in skill.triggers
        assert "order" in skill.description.lower()

    def test_instructions_before_purpose(self):
        """Section ordering: instructions first, then purpose."""
        md = (
            "# Reverse Skill\n\n"
            "## Instructions\nFirst instructions\n\n"
            "## Purpose\nReverse order\n\n"
            "## Triggers\n- test"
        )
        skill = Skill.from_markdown(md)
        assert "instructions" in skill.instructions.lower()
        assert "reverse" in skill.description.lower()

    def test_generic_header_between_sections(self):
        """A generic ## header between Purpose and Triggers exercises the
        '## ' branch for non-special sections."""
        md = (
            "# Header Skill\n\n"
            "## Purpose\nA purpose\n\n"
            "## Notes\nSome notes here\n\n"
            "## Triggers\n- trigger1\n\n"
            "## Instructions\nDo it"
        )
        skill = Skill.from_markdown(md)
        assert "purpose" in skill.description.lower()
        assert len(skill.triggers) == 1

    def test_fallback_description_no_purpose_section(self):
        """When no ## Purpose section exists, fallback description
        uses the first non-header body line (line ~130)."""
        md = "# Fallback Skill\n\nSome body text here.\n\n## Instructions\nDo it"
        skill = Skill.from_markdown(md)
        assert "body text" in skill.description.lower()

    def test_triggers_in_middle_section_gathered(self):
        """A ## Triggers section appearing after a generic ## header
        still extracts triggers correctly (triggers → purpose branch)."""
        md = (
            "# Middle Skill\n\n"
            "## Notes\nSome notes\n\n"
            "## Triggers\n- ci broken\n- tests fail\n\n"
            "## Purpose\nMiddle trigger\n\n"
            "## Instructions\nFix it"
        )
        skill = Skill.from_markdown(md)
        assert "ci broken" in skill.triggers
        assert "tests fail" in skill.triggers
        assert "middle" in skill.description.lower()

    def test_load_directory_with_exception_skips_bad_file(self, tmp_path):
        """load_directory logs an error and continues on malformed files."""
        good = tmp_path / "good.md"
        good.write_text("# Good\n\n## Purpose\nGood skill\n\n## Instructions\ni\n")
        bad = tmp_path / "bad.md"
        bad.write_text("")
        registry = SkillRegistry()
        count = registry.load_directory(str(tmp_path))
        assert count >= 1


class TestSkillRegistryExtended:
    def test_match_ranked_returns_sorted(self):
        registry = SkillRegistry()
        registry.add(
            Skill(
                name="ci",
                description="CI stuff",
                instructions="Fix CI",
                triggers=["ci failed"],
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
        results = registry.match_ranked("ci failed and deploy now")
        # ci should rank higher because "ci failed" is an exact multi-word match
        assert len(results) >= 2
        assert results[0][0].name in ("ci", "deploy")

    def test_match_ranked_with_min_score(self):
        registry = SkillRegistry()
        registry.add(
            Skill(
                name="weak",
                description="Weak match",
                instructions="i",
                triggers=["xyz"],
            )
        )
        registry.add(
            Skill(
                name="strong",
                description="Strong match",
                instructions="i",
                triggers=["deploy"],
            )
        )
        results = registry.match_ranked("deploy now", min_score=0.1)
        names = [s.name for s, _ in results]
        assert "strong" in names
        assert "weak" not in names

    def test_match_ranked_with_limit(self):
        registry = SkillRegistry()
        for i in range(5):
            registry.add(
                Skill(
                    name=f"s{i}",
                    description=f"Skill {i}",
                    instructions="i",
                    triggers=[f"trigger{i}"],
                )
            )
        results = registry.match_ranked("trigger0 trigger1 trigger2", limit=2)
        assert len(results) == 2

    def test_match_one_returns_best(self):
        registry = SkillRegistry()
        registry.add(Skill(name="a", description="A", instructions="i", triggers=["deploy"]))
        registry.add(Skill(name="b", description="B", instructions="i", triggers=["ci failed"]))
        result = registry.match_one("deploy the service")
        assert result is not None
        assert result.name == "a"

    def test_match_one_returns_none_when_below_threshold(self):
        registry = SkillRegistry()
        registry.add(
            Skill(name="low", description="Low", instructions="i", triggers=["xyznonexistent"])
        )
        result = registry.match_one("nothing matches", min_score=0.5)
        assert result is None

    def test_load_directory_not_exists(self):
        registry = SkillRegistry()
        count = registry.load_directory("/nonexistent/path/xyz")
        assert count == 0

    def test_load_file(self, tmp_path):
        skill_md = (
            "# File Skill\n\n"
            "## Purpose\nFromFile\n\n"
            "## Triggers\n- file trigger\n\n"
            "## Instructions\nDo file stuff"
        )
        path = tmp_path / "file-skill.md"
        path.write_text(skill_md)
        registry = SkillRegistry()
        skill = registry.load_file(str(path))
        assert skill.name == "File Skill"
        assert "file trigger" in skill.triggers
        assert len(registry.list_all()) == 1

    def test_to_a2a_skills(self):
        registry = SkillRegistry()
        registry.add(Skill(name="s1", description="First", instructions="i", triggers=["t1"]))
        cards = registry.to_a2a_skills()
        assert len(cards) == 1
        assert cards[0]["name"] == "s1"

    def test_to_a2a_skills_empty(self):
        registry = SkillRegistry()
        cards = registry.to_a2a_skills()
        assert cards == []
