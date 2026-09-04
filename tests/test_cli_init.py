"""T1.1.2 — Tests for ``loopy init <name>``.

Strict TDD: written before the implementation in
``loopy.cli.cmd_init``. Each test maps to a behavior in the
v1.1 GOAL.md Phase A contract.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from loopy.cli import create_parser
from loopy.config import LoopyConfig, load


@pytest.fixture
def in_tmp_cwd(tmp_path: Path):
    """Change into a fresh temp dir for the duration of one test."""
    original = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(original)


# ── CLI parser ──────────────────────────────────────────────


class TestInitParser:
    def test_init_subcommand_is_registered(self):
        parser = create_parser()
        args = parser.parse_args(["init", "myproj"])
        assert args.command == "init"
        assert args.project_name == "myproj"

    def test_init_no_test_flag(self):
        parser = create_parser()
        args = parser.parse_args(["init", "myproj", "--no-test"])
        assert args.no_test is True

    def test_init_default_no_test_is_false(self):
        parser = create_parser()
        args = parser.parse_args(["init", "myproj"])
        assert args.no_test is False


# ── cmd_init happy path ─────────────────────────────────────


class TestInitHappyPath:
    def test_scaffolds_required_files(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        cmd_init(_ns("myproj"))

        project = in_tmp_cwd / "myproj"
        assert (project / "pyproject.toml").exists()
        assert (project / "agent.py").exists()
        assert (project / "loopy.yml").exists()
        assert (project / ".gitignore").exists()
        assert (project / "README.md").exists()

    def test_scaffolds_test_file_by_default(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        cmd_init(_ns("myproj"))

        assert (in_tmp_cwd / "myproj" / "tests" / "test_agent.py").exists()

    def test_no_test_flag_skips_test_file(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        cmd_init(_ns("myproj", no_test=True))

        assert not (in_tmp_cwd / "myproj" / "tests").exists()

    def test_scaffolded_agent_uses_testmodel(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        cmd_init(_ns("myproj"))

        agent_py = (in_tmp_cwd / "myproj" / "agent.py").read_text()
        assert "TestModel" in agent_py
        assert "loopy" in agent_py.lower()

    def test_scaffolded_pyproject_uses_all_extra(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        cmd_init(_ns("myproj"))

        toml = (in_tmp_cwd / "myproj" / "pyproject.toml").read_text()
        assert "loopy-agent" in toml
        assert "[all]" in toml


# ── Negative controls ──────────────────────────────────────


class TestInitNegativeControls:
    def test_refuses_existing_non_empty_dir(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        (in_tmp_cwd / "myproj").mkdir()
        (in_tmp_cwd / "myproj" / "preexisting.txt").write_text("hi")

        with pytest.raises(FileExistsError):
            cmd_init(_ns("myproj"))

    def test_allows_existing_empty_dir(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        (in_tmp_cwd / "myproj").mkdir()

        cmd_init(_ns("myproj"))

        assert (in_tmp_cwd / "myproj" / "pyproject.toml").exists()

    def test_refuses_path_traversal_name(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        with pytest.raises(ValueError, match="must not contain"):
            cmd_init(_ns("../escape"))

    def test_refuses_path_traversal_with_double_dot_in_middle(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        with pytest.raises(ValueError, match="must not contain"):
            cmd_init(_ns("foo..bar"))

    def test_refuses_absolute_path_name(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        with pytest.raises(ValueError, match="must not contain"):
            cmd_init(_ns("/etc/passwd"))

    def test_refuses_empty_name(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        with pytest.raises(ValueError, match="non-empty"):
            cmd_init(_ns(""))


# ── loopy.yml loader ───────────────────────────────────────


class TestLoopyConfig:
    def test_round_trip(self, in_tmp_cwd):
        from loopy.cli import cmd_init

        cmd_init(_ns("myproj"))

        cfg = load(str(in_tmp_cwd / "myproj" / "loopy.yml"))
        assert isinstance(cfg, LoopyConfig)
        assert cfg.provider == "test"
        assert cfg.max_steps == 3
        assert cfg.interrupt_before == []
        assert cfg.interrupt_after == []

    def test_load_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load(str(tmp_path / "loopy.yml"))

    def test_load_malformed_yml_raises(self, tmp_path: Path):
        bad = tmp_path / "loopy.yml"
        bad.write_text("not: valid: yaml: [")
        with pytest.raises(ValueError, match="malformed"):
            load(str(bad))

    def test_load_rejects_unknown_keys(self, tmp_path: Path):
        bad = tmp_path / "loopy.yml"
        bad.write_text("provider: test\nmystery_key: 1\n")
        with pytest.raises(ValueError, match="unknown keys"):
            load(str(bad))

    def test_load_rejects_invalid_provider(self, tmp_path: Path):
        bad = tmp_path / "loopy.yml"
        bad.write_text("provider: bogus\n")
        with pytest.raises(ValueError, match="not supported"):
            load(str(bad))

    def test_load_rejects_max_steps_zero(self, tmp_path: Path):
        bad = tmp_path / "loopy.yml"
        bad.write_text("max_steps: 0\n")
        with pytest.raises(ValueError, match="max_steps"):
            load(str(bad))


# ── Helpers ────────────────────────────────────────────────


def _ns(project_name: str, *, no_test: bool = False):
    """Build a minimal argparse.Namespace for cmd_init."""
    import argparse

    return argparse.Namespace(project_name=project_name, no_test=no_test)
