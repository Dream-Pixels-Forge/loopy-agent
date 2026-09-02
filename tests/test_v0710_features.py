"""Tests for v0.7.10 features.

Three additions:
  1. ``Skill.to_a2a_card`` / ``Skill.from_a2a_card`` / ``SkillRegistry.to_a2a_skills``
  2. ``RealtimeSession`` (pluggable transport)
  3. Docs site + ``llms-full.txt`` (smoke-tested via the generator script)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loopy import (
    RealtimeEvent,
    RealtimeEventType,
    RealtimeSession,
    Skill,
    SkillRegistry,
)

# ---------------------------------------------------------------------------
# Feature 1 - Skill A2A interop
# ---------------------------------------------------------------------------


class TestSkillA2AExport:
    def test_to_a2a_card_basic_shape(self):
        skill = Skill(
            name="CI Triage",
            description="Triage CI failures",
            instructions="1. Check the failing job...",
            triggers=["ci failed", "flaky tests"],
        )
        card = skill.to_a2a_card()
        assert card["name"] == "CI Triage"
        assert card["description"] == "Triage CI failures"
        assert card["tags"] == ["ci failed", "flaky tests"]
        assert card["inputModes"] == ["text"]
        assert card["outputModes"] == ["text"]
        # id is slugified
        assert card["id"] == "ci-triage"

    def test_to_a2a_card_explicit_kwargs(self):
        skill = Skill(
            name="x",
            description="x",
            instructions="x",
            triggers=["a"],
        )
        card = skill.to_a2a_card(
            examples=["a", "b"],
            tags=["custom"],
            input_modes=["text", "image"],
            output_modes=["text", "audio"],
        )
        assert card["examples"] == ["a", "b"]
        assert card["tags"] == ["custom"]
        assert card["inputModes"] == ["text", "image"]
        assert card["outputModes"] == ["text", "audio"]

    def test_to_a2a_card_id_slugification(self):
        skill = Skill(name="My Skill_One", description="x", instructions="x")
        card = skill.to_a2a_card()
        assert card["id"] == "my-skill-one"

    def test_to_a2a_card_default_description_fallback(self):
        skill = Skill(name="x", description="", instructions="x")
        card = skill.to_a2a_card()
        assert card["description"] == "Skill: x"

    def test_to_a2a_card_no_triggers(self):
        skill = Skill(name="x", description="d", instructions="x", triggers=[])
        card = skill.to_a2a_card()
        assert card["tags"] == []


class TestSkillA2AImport:
    def test_from_a2a_card_round_trip(self):
        original = Skill(
            name="CI Triage",
            description="Triage CI failures",
            instructions="steps...",
            triggers=["ci failed"],
        )
        card = original.to_a2a_card(examples=["fix CI"])
        back = Skill.from_a2a_card(card)
        assert back.name == "CI Triage"
        assert back.description == "Triage CI failures"
        assert back.triggers == ["ci failed"]
        # Examples preserved in metadata
        assert back.metadata["a2a_examples"] == ["fix CI"]

    def test_from_a2a_card_minimal(self):
        back = Skill.from_a2a_card({"name": "Minimal", "description": "A skill"})
        assert back.name == "Minimal"
        assert back.triggers == []
        assert back.instructions == "A skill"

    def test_from_a2a_card_missing_name_raises(self):
        with pytest.raises(ValueError, match="non-empty 'name'"):
            Skill.from_a2a_card({"description": "x"})

    def test_from_a2a_card_missing_description_raises(self):
        with pytest.raises(ValueError, match="requires a 'description'"):
            Skill.from_a2a_card({"name": "x"})

    def test_from_a2a_card_non_dict_raises(self):
        with pytest.raises(TypeError, match="must be a dict"):
            Skill.from_a2a_card("not a dict")  # type: ignore[arg-type]

    def test_from_a2a_card_preserves_modality_metadata(self):
        card = {
            "name": "X",
            "description": "x",
            "inputModes": ["text", "image"],
            "outputModes": ["text"],
            "id": "x",
        }
        back = Skill.from_a2a_card(card)
        assert back.metadata["a2a_input_modes"] == ["text", "image"]
        assert back.metadata["a2a_output_modes"] == ["text"]
        assert back.metadata["a2a_id"] == "x"


class TestSkillRegistryA2AExport:
    def test_to_a2a_skills_returns_every_skill(self):
        reg = SkillRegistry()
        reg.add(Skill(name="A", description="a", instructions="a", triggers=["a"]))
        reg.add(Skill(name="B", description="b", instructions="b", triggers=["b"]))
        cards = reg.to_a2a_skills()
        assert {c["name"] for c in cards} == {"A", "B"}
        for c in cards:
            assert "id" in c and "tags" in c and "inputModes" in c

    def test_to_a2a_skills_empty_registry(self):
        assert SkillRegistry().to_a2a_skills() == []


# ---------------------------------------------------------------------------
# Feature 2 - RealtimeSession
# ---------------------------------------------------------------------------


class FakeTransport:
    """In-memory transport for testing RealtimeSession."""

    def __init__(self, frames: list[dict[str, object]] | None = None) -> None:
        self.sent: list[dict[str, object]] = []
        self._frames = list(frames or [])
        self.closed = False

    async def send(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)

    async def recv(self) -> dict[str, object] | None:
        if self._frames:
            return self._frames.pop(0)
        return None

    async def close(self) -> None:
        self.closed = True


class TestRealtimeEvent:
    def test_transcript_property(self):
        ev = RealtimeEvent(type=RealtimeEventType.TRANSCRIPT_DELTA, data={"transcript": "hi"})
        assert ev.transcript == "hi"

    def test_audio_property(self):
        ev = RealtimeEvent(type=RealtimeEventType.AUDIO_DELTA, data={"audio": b"\x00\x01"})
        assert ev.audio_bytes == b"\x00\x01"

    def test_default_timestamp_is_recent(self):
        import time

        before = time.time()
        ev = RealtimeEvent(type=RealtimeEventType.SESSION_CREATED)
        after = time.time()
        assert before <= ev.timestamp <= after


class TestRealtimeSession:
    @pytest.mark.asyncio
    async def test_session_consumes_events(self):
        transport = FakeTransport(
            frames=[
                {"type": "session.created"},
                {"type": "transcript.delta", "transcript": "hello"},
                {"type": "transcript.delta", "transcript": " world"},
            ]
        )
        async with RealtimeSession(transport) as session:
            received: list[RealtimeEvent] = []
            async for event in session:
                received.append(event)
                if len(received) >= 3:
                    break
            types = [e.type for e in received]
            assert RealtimeEventType.SESSION_CREATED in types
            assert types.count(RealtimeEventType.TRANSCRIPT_DELTA) == 2
            assert received[1].transcript == "hello"

    @pytest.mark.asyncio
    async def test_session_send(self):
        transport = FakeTransport(frames=[])
        async with RealtimeSession(transport) as session:
            await session.send({"type": "session.update", "session": {}})
            await session.close()
        assert transport.sent == [{"type": "session.update", "session": {}}]

    @pytest.mark.asyncio
    async def test_send_after_close_raises(self):
        transport = FakeTransport()
        async with RealtimeSession(transport) as session:
            pass
        # Now session is closed
        with pytest.raises(RuntimeError, match="closed"):
            await session.send({"type": "x"})

    @pytest.mark.asyncio
    async def test_unknown_event_type_becomes_error(self):
        transport = FakeTransport(frames=[{"type": "brand.new.event", "data": 1}])
        async with RealtimeSession(transport) as session:
            events: list[RealtimeEvent] = []
            async for ev in session:
                events.append(ev)
                break
        assert events[0].type == RealtimeEventType.ERROR
        assert events[0].data["type"] == "brand.new.event"

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        transport = FakeTransport()
        session = RealtimeSession(transport)
        await session.close()
        await session.close()  # should not raise
        assert transport.closed

    @pytest.mark.asyncio
    async def test_emits_closed_event(self):
        transport = FakeTransport()
        async with RealtimeSession(transport):
            pass  # __aexit__ triggers close
        assert transport.closed


# ---------------------------------------------------------------------------
# Feature 3 - Docs / llms-full.txt
# ---------------------------------------------------------------------------


class TestDocsAndLLMS:
    def test_mkdocs_yml_exists(self):
        path = Path("docs/mkdocs.yml")
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "site_name: loopy-agent" in text
        assert "material" in text  # uses mkdocs-material theme

    def test_index_page_exists(self):
        assert Path("docs/index.md").exists()
        assert Path("docs/getting-started.md").exists()
        assert Path("docs/concepts.md").exists()

    def test_module_pages_exist(self):
        for mod in ["loop", "gateway", "multimodal", "skills", "safety", "mcp", "state", "audit"]:
            assert Path(f"docs/modules/{mod}.md").exists(), f"missing docs/modules/{mod}.md"

    def test_research_doc_exists(self):
        assert Path("docs/research/competitive-analysis-2026.md").exists()
        assert Path("docs/research").is_dir()

    def test_agents_md_for_ai_assistants(self):
        assert Path("AGENTS.md").exists()
        text = Path("AGENTS.md").read_text(encoding="utf-8")
        assert "Cursor" in text or "Cline" in text

    def test_skills_directory_for_claude_code(self):
        assert Path("skills").is_dir()
        assert Path("skills/loopy-router.md").exists()

    def test_llms_txt_generator_script(self):
        assert Path("scripts/generate_llms_txt.py").exists()

    def test_llms_txt_was_generated(self):
        assert Path("llms/llms-full.txt").exists()
        size = Path("llms/llms-full.txt").stat().st_size
        # Should be non-trivial - at least 5KB
        assert size > 5000, f"llms/llms-full.txt too small: {size} bytes"

    def test_llms_txt_contains_known_sections(self):
        text = Path("llms/llms-full.txt").read_text(encoding="utf-8")
        assert "loopy-agent" in text
        assert "AgentLoop" in text
        assert "TestModel" in text
        assert "RealtimeSession" in text
        assert "Skill" in text

    def test_llms_generator_runs_clean(self):
        """Re-running the generator should not fail."""
        result = subprocess.run(
            [sys.executable, "scripts/generate_llms_txt.py"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert result.returncode == 0
        # The script prints one line per file with "wrote <path>". Match
        # on the basename so Windows backslashes and POSIX forward
        # slashes both pass.
        assert any(
            "llms-full.txt" in line and line.startswith("wrote ")
            for line in result.stdout.splitlines()
        )


# ---------------------------------------------------------------------------
# Round-trip integration: Skills → A2A Skills → SkillRegistry
# ---------------------------------------------------------------------------


class TestSkillRoundTripIntegration:
    def test_export_through_registry_then_reimport(self):
        """An entire registry can round-trip through A2A Skill primitives."""
        reg = SkillRegistry()
        reg.add(
            Skill(
                name="Triager",
                description="Triage bugs",
                instructions="...",
                triggers=["bug", "broken"],
            )
        )
        reg.add(
            Skill(
                name="Reviewer",
                description="Review PRs",
                instructions="...",
                triggers=["review", "PR"],
            )
        )

        # Export
        cards = reg.to_a2a_skills()
        assert len(cards) == 2

        # Reimport into a new registry
        reg2 = SkillRegistry()
        for card in cards:
            reg2.add(Skill.from_a2a_card(card))

        # Round-trip preserves names and trigger keys
        names = {s.name for s in reg2.list_all()}
        assert names == {"Triager", "Reviewer"}
        assert reg2.match_one("this bug is bad").name == "Triager"
        assert reg2.match_one("please review my PR").name == "Reviewer"

    def test_a2a_card_is_json_serializable(self):
        """Agent Card primitives should round-trip through json.dumps/loads."""
        skill = Skill(
            name="JSON Test",
            description="desc",
            instructions="instr",
            triggers=["x"],
        )
        card = skill.to_a2a_card(examples=["example"])
        encoded = json.dumps(card)
        decoded = json.loads(encoded)
        assert decoded == card
