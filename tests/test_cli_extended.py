"""Extended CLI tests — cmd_init paths, cmd_serve, cmd_lsp, main."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loopy.cli import cmd_init


def _ns(project_name: str, *, no_test: bool = False):
    return argparse.Namespace(project_name=project_name, no_test=no_test)


# ── cmd_init validation ────────────────────────────────────────


class TestCmdInit:
    def test_init_empty_name_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            cmd_init(_ns(""))

    def test_init_name_with_slash_raises(self):
        with pytest.raises(ValueError, match="path-traversal"):
            cmd_init(_ns("foo/bar"))

    def test_init_name_with_backslash_raises(self):
        with pytest.raises(ValueError, match="path-traversal"):
            cmd_init(_ns("foo\\bar"))

    def test_init_name_with_dotdot_raises(self):
        with pytest.raises(ValueError, match="path-traversal"):
            cmd_init(_ns("foo/../bar"))

    def test_init_absolute_path_raises(self):
        with (
            patch("pathlib.Path.is_absolute", return_value=True),
            pytest.raises(ValueError, match="relative"),
        ):
            cmd_init(_ns("safe-name"))

    def test_init_existing_nonempty_dir_raises(self, tmp_path: Path):
        existing = tmp_path / "subdir"
        existing.mkdir()
        (existing / "file.txt").write_text("hello")
        original = Path.cwd()
        os.chdir(tmp_path)
        try:
            with pytest.raises(FileExistsError, match="not empty"):
                cmd_init(_ns("subdir"))
        finally:
            os.chdir(original)

    def test_init_creates_project_structure(self, tmp_path: Path):
        original = Path.cwd()
        os.chdir(tmp_path)
        try:
            cmd_init(_ns("my-project"))
            project_dir = tmp_path / "my-project"
            assert project_dir.exists()
            assert (project_dir / "pyproject.toml").exists()
            assert (project_dir / "agent.py").exists()
            assert (project_dir / "loopy.yml").exists()
            assert (project_dir / ".gitignore").exists()
            assert (project_dir / "README.md").exists()
            assert (project_dir / "tests").exists()
            assert (project_dir / "tests" / "test_agent.py").exists()
        finally:
            os.chdir(original)

    def test_init_skips_tests_when_no_test_flag(self, tmp_path: Path):
        original = Path.cwd()
        os.chdir(tmp_path)
        try:
            cmd_init(_ns("no-test-proj", no_test=True))
            project_dir = tmp_path / "no-test-proj"
            assert not (project_dir / "tests").exists()
        finally:
            os.chdir(original)


# ── cmd_serve ──────────────────────────────────────────────────


class TestCmdServe:
    def test_serve_with_default_card(self, capsys):
        """cmd_serve with no --agent flag starts a server with the default card."""
        from loopy.cli import cmd_serve

        args = argparse.Namespace(agent=None, host="127.0.0.1", port=0)

        with patch("loopy.federate.FederatedServer") as MockServer:
            mock_instance = MagicMock()
            mock_instance.port = 9999
            MockServer.return_value = mock_instance

            def fake_wait(*args):
                raise KeyboardInterrupt()

            with patch("loopy.cli.threading.Event.wait", fake_wait):
                cmd_serve(args)

            MockServer.assert_called_once()
            mock_instance.start.assert_called_once()
            mock_instance.shutdown.assert_called_once()

        captured = capsys.readouterr()
        assert "listening on" in captured.out.lower()
        assert "9999" in captured.out

    def test_serve_with_agent_module(self, tmp_path: Path):
        """cmd_serve with --agent loads the agent module's card."""
        from loopy.cli import cmd_serve

        agent_file = tmp_path / "my_agent.py"
        agent_file.write_text(
            "from loopy.a2a import AgentCard, AgentCapability\n"
            "CARD = AgentCard(\n"
            "    name='my-agent',\n"
            "    description='custom',\n"
            "    version='1.0',\n"
            "    capabilities=[AgentCapability.TEXT_GENERATION],\n"
            "    endpoint='local',\n"
            ")\n"
        )
        args = argparse.Namespace(agent=str(agent_file), host="127.0.0.1", port=0)

        with patch("loopy.federate.FederatedServer") as MockServer:
            mock_instance = MagicMock()
            mock_instance.port = 8888
            MockServer.return_value = mock_instance

            def fake_wait(*args):
                raise KeyboardInterrupt()

            with patch("loopy.cli.threading.Event.wait", fake_wait):
                cmd_serve(args)

            MockServer.assert_called_once()
            call_kwargs = MockServer.call_args
            card = call_kwargs[1]["agent_card"]
            assert card.name == "my-agent"


# ── cmd_lsp ────────────────────────────────────────────────────


class TestCmdLsp:
    def test_lsp_starts_server(self):
        from loopy.cli import cmd_lsp

        with patch("loopy.lsp.LspServer") as MockLsp:
            mock_instance = MagicMock()
            MockLsp.return_value = mock_instance
            cmd_lsp(argparse.Namespace())
            mock_instance.start.assert_called_once()


# ── main entry point ───────────────────────────────────────────


class TestMain:
    def test_main_chat_command(self):
        from loopy.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["chat", "hello", "--provider", "openai"])
        assert args.command == "chat"
        assert args.message == "hello"
        assert args.provider == "openai"

    def test_main_serve_command(self):
        from loopy.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["serve", "--port", "8080"])
        assert args.command == "serve"
        assert args.port == 8080

    def test_main_init_command(self):
        from loopy.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["init", "myproj"])
        assert args.command == "init"
        assert args.project_name == "myproj"

    def test_main_dev_command(self):
        from loopy.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["dev", "script.py"])
        assert args.command == "dev"
        assert args.script == "script.py"
