# `loopy.skills` — Skill registry + A2A interop

Persistent agent knowledge: skills, ranked matching, and export to
the **A2A Skill primitive** for interop with Google's Agent2Agent
protocol.

## Quickstart

```python
from loopy import Skill, SkillRegistry

reg = SkillRegistry()
reg.add(Skill(
    name="CI Triage",
    description="Diagnose CI failures",
    instructions="1. Check the failing job...",
    triggers=["ci failed", "flaky tests", "broken pipeline"],
))

# v0.7.8: ranked matching
ranked = reg.match_ranked("the ci is failing again", min_score=0.1)
best = reg.match_one("fix flaky tests")
```

## A2A interop (v0.7.10)

Any loopy `Skill` can be advertised as an A2A Skill primitive, and any
A2A Skill can be imported as a loopy Skill:

```python
from loopy import Skill

# Export
card = skill.to_a2a_card(examples=["my CI is broken"])
# => {"id": "ci-triage", "name": "CI Triage", "description": ..., ...}

# Import
back = Skill.from_a2a_card(card)

# Whole registry as A2A "skills: []"
from loopy import SkillRegistry
cards = SkillRegistry().to_a2a_skills()
```

## API

| Symbol | Purpose |
|---|---|
| `Skill` | Persistent agent knowledge (name/description/instructions/triggers) |
| `Skill.from_markdown` | Parse a SKILL.md file |
| `Skill.to_a2a_card` | Serialize to A2A Skill primitive (v0.7.10) |
| `Skill.from_a2a_card` | Reconstruct from A2A Skill primitive (v0.7.10) |
| `SkillRegistry` | Container for skills |
| `SkillRegistry.match_ranked` | Sorted by relevance score (v0.7.8) |
| `SkillRegistry.match_one` | Best match or None (v0.7.8) |
| `SkillRegistry.to_a2a_skills` | Export every skill as A2A primitives (v0.7.10) |