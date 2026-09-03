"""T1.2.1 — Tests for the 10 example recipes.

Strict TDD: written before the recipes exist. Each test runs
the recipe in a subprocess and asserts it exits 0 and that
its stdout contains the expected marker.

Every recipe is required by the v1.1 GOAL.md Phase B contract
to:

  * be a single file under ``examples/``
  * be fewer than 100 lines
  * use ``TestModel`` (no API key required)
  * run end-to-end with ``python examples/<file>``
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

# (filename, expected stdout substring, one-line "what you'll learn" tag)
RECIPES = [
    ("00_hello_world.py", "agent output:", "minimal AgentLoop"),
    ("01_streaming.py", "streamed", "token-by-token output"),
    ("02_cost_capped.py", "cost-cap", "max_cost_usd + fallback"),
    ("03_policies.py", "policy", "Compliance-as-Code gate"),
    ("04_durable.py", "durable", "DAG + Saga + journal"),
    ("05_verified.py", "verifier", "VerifiedAgent + invariants"),
    ("06_federation.py", "federat", "FederatedServer endpoint"),
    ("07_hitl.py", "interrupt", "HITL pause + resume"),
    ("08_redaction.py", "redact", "PII scrubbing in spans"),
    ("09_otel.py", "otel", "OpenTelemetry auto-instrumentation"),
]


def _example_path(filename: str) -> Path:
    return EXAMPLES_DIR / filename


# ── File-shape contract ─────────────────────────────────────


class TestExampleFileContract:
    @pytest.mark.parametrize("filename,_,__", RECIPES, ids=[r[0] for r in RECIPES])
    def test_example_file_exists(self, filename, _, __):
        assert _example_path(filename).exists(), (
            f"missing recipe {filename} (see https://loopy.dev/docs/examples)"
        )

    @pytest.mark.parametrize("filename,_,__", RECIPES, ids=[r[0] for r in RECIPES])
    def test_example_under_100_lines(self, filename, _, __):
        path = _example_path(filename)
        if not path.exists():
            pytest.skip(f"file {filename} does not exist yet")
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        assert line_count < 100, (
            f"{filename} is {line_count} lines; recipes must be <100 "
            "(see https://loopy.dev/docs/examples#constraints)"
        )

    @pytest.mark.parametrize("filename,_,__", RECIPES, ids=[r[0] for r in RECIPES])
    def test_example_does_not_require_api_key(self, filename, _, __):
        # Every recipe must be runnable without an API key. We
        # enforce this by:
        #   1. Importing the ``TestModel`` class is fine.
        #   2. Calling ``openai``, ``anthropic``, or any other LLM SDK
        #      is forbidden — recipes must use ``TestModel`` or
        #      canned planner/actor lambdas.
        path = _example_path(filename)
        if not path.exists():
            pytest.skip(f"file {filename} does not exist yet")
        text = path.read_text(encoding="utf-8")
        for forbidden in ("import openai", "import anthropic", "OpenAI("):
            assert forbidden not in text, (
                f"{filename} imports/uses {forbidden!r}; recipes must not "
                "require a real API key. Use TestModel or canned callbacks "
                "instead (see https://loopy.dev/docs/examples#no-api-key)"
            )


# ── Executability contract ─────────────────────────────────


class TestExampleExecutability:
    @pytest.mark.parametrize(
        "filename,marker,_tag",
        RECIPES,
        ids=[r[0] for r in RECIPES],
    )
    def test_example_runs_and_prints_marker(self, filename, marker, _tag, tmp_path: Path):
        path = _example_path(filename)
        if not path.exists():
            pytest.skip(f"file {filename} does not exist yet")
        # Run the example in a fresh cwd so any side-effect files
        # land in tmp_path and don't pollute the repo.
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=30,
        )
        assert result.returncode == 0, (
            f"{filename} exited with {result.returncode}.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        # Recipes print at least one of these markers to stdout.
        # Use a regex search so case + minor wording differences are OK.
        assert re.search(marker, result.stdout, re.IGNORECASE), (
            f"{filename} did not print expected marker {marker!r}.\nstdout:\n{result.stdout}"
        )


# ── examples/README.md index contract ──────────────────────


class TestExamplesReadme:
    def test_readme_exists(self):
        readme = EXAMPLES_DIR / "README.md"
        assert readme.exists(), (
            "examples/README.md is required (see https://loopy.dev/docs/examples#index)"
        )

    def test_readme_lists_all_recipes(self):
        readme = EXAMPLES_DIR / "README.md"
        if not readme.exists():
            pytest.skip("examples/README.md does not exist yet")
        text = readme.read_text(encoding="utf-8")
        for filename, _, _ in RECIPES:
            # Every recipe file must be linked from the README.
            assert filename in text, (
                f"examples/README.md does not link to {filename} (see "
                "https://loopy.dev/docs/examples#index)"
            )

    def test_readme_has_table(self):
        readme = EXAMPLES_DIR / "README.md"
        if not readme.exists():
            pytest.skip("examples/README.md does not exist yet")
        text = readme.read_text(encoding="utf-8")
        # A markdown table needs at least one header row and one
        # separator row (|---|).
        assert "|" in text
        assert "---" in text
