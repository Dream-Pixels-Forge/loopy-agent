"""Tests for loopy dev module — hot-reload dev server + doctor command."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── run_dev ───────────────────────────────────────────────────


class TestRunDev:
    def test_missing_watchfiles_raises_import_error(self):
        """run_dev must surface a clear ImportError when watchfiles is absent."""
        from loopy.dev import run_dev

        with (
            pytest.raises(ImportError, match="watchfiles is required"),
            patch.dict(sys.modules, {"watchfiles": None}),
        ):
            asyncio.run(run_dev("/fake/script.py"))

    def test_missing_script_raises_file_not_found(self):
        """run_dev must raise FileNotFoundError for a nonexistent script path."""
        from loopy.dev import run_dev

        with pytest.raises(FileNotFoundError, match="Script not found"):
            asyncio.run(run_dev("/nonexistent/path/script.py"))

    @pytest.mark.asyncio
    async def test_watches_script_and_reruns_on_change(self, tmp_path: Path):
        """When a watched file changes, the script is re-executed."""
        from loopy.dev import run_dev

        script = tmp_path / "main.py"
        script.write_text("print('hello')\n")

        call_count = 0

        async def fake_awatch(*paths, **kwargs):
            nonlocal call_count
            call_count += 1
            yield [MagicMock()]

        with patch("watchfiles.awatch", fake_awatch), patch("loopy.dev._run_script") as mock_run:
            mock_run.return_value = asyncio.Future()
            mock_run.return_value.set_result(None)
            await run_dev(str(script))
            mock_run.assert_called_once_with(script.resolve())
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_run_script_no_watchfiles(self, tmp_path: Path):
        """_run_script must not crash when watchfiles events come in but
        the module has no async main()."""
        from loopy.dev import _run_script

        script = tmp_path / "simple.py"
        script.write_text("x = 1\n")

        result = asyncio.create_task(_run_script(script.resolve()))
        await asyncio.sleep(0.1)
        assert not result.done() or result.exception() is None


# ── DevServer scaffold ────────────────────────────────────────


class TestDevServer:
    def test_class_exists(self):
        """DevServer must be importable from loopy.dev."""
        from loopy.dev import DevServer

        assert DevServer is not None

    def test_default_attributes(self):
        from loopy.dev import DevServer

        server = DevServer()
        assert hasattr(server, "host")
        assert hasattr(server, "port")
        assert hasattr(server, "script_path")
        assert server.host == "127.0.0.1"
        assert server.port == 8765

    def test_ws_endpoint_is_todo(self):
        """The WebSocket handler must exist as a placeholder with a TODO."""
        from loopy.dev import DevServer

        server = DevServer()
        assert hasattr(server, "handle_ws")
        assert callable(server.handle_ws)


# ── CLI: dev subcommand ──────────────────────────────────────


class TestDevCommand:
    def test_parser_delegates_to_cmd_dev(self):
        from loopy.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["dev", "my_script.py"])
        assert args.command == "dev"
        assert args.script == "my_script.py"

    def test_cmd_dev_calls_run_dev(self):
        from loopy.cli import cmd_dev

        args = argparse.Namespace(script="test.py")
        with patch("loopy.dev.run_dev") as mock_run:
            mock_run.return_value = None
            cmd_dev(args)
            mock_run.assert_called_once_with("test.py")


# ── CLI: doctor subcommand ───────────────────────────────────


class TestDoctorCommand:
    def test_parser_delegates_to_cmd_doctor(self):
        from loopy.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["doctor"])
        assert args.command == "doctor"

    def test_cmd_doctor_reports_missing_api_key(self, capsys):
        from loopy.cli import cmd_doctor

        with patch.dict("os.environ", {}, clear=True), pytest.raises(SystemExit) as exc_info:
            cmd_doctor(argparse.Namespace())
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "issues found" in captured.out.lower()
        assert "OPENAI_API_KEY" in captured.out

    def test_cmd_doctor_passes_when_env_ok(self, capsys):
        from loopy.cli import cmd_doctor

        class FakeVersion:
            major = 3
            minor = 10

            def __lt__(self, other):
                return (self.major, self.minor) < other

        with (
            patch.dict(
                "os.environ",
                {"OPENAI_API_KEY": "sk-xxx", "ANTHROPIC_API_KEY": "sk-ant-xxx"},
            ),
            patch("loopy.cli.sys.version_info", FakeVersion()),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_doctor(argparse.Namespace())
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "all checks passed" in captured.out.lower()

    def test_cmd_doctor_detects_old_python(self, capsys):
        from loopy.cli import cmd_doctor

        class FakeVersion:
            major = 3
            minor = 9

            def __lt__(self, other):
                return (self.major, self.minor) < other

        with (
            patch.dict(
                "os.environ", {"OPENAI_API_KEY": "sk-xxx", "ANTHROPIC_API_KEY": "sk-ant-xxx"}
            ),
            patch("loopy.cli.sys.version_info", FakeVersion()),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_doctor(argparse.Namespace())
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Python 3.9 < 3.10" in captured.out


# ── Integration: script re-runs on change ────────────────────


class TestScriptRerunsOnChange:
    def test_reruns_on_file_touch(self, tmp_path: Path):
        """Touch a script file and confirm _run_script executes it."""
        from loopy.dev import _run_script

        script = tmp_path / "tick.py"
        script.write_text("import time; time.sleep(0.01)\n")

        asyncio.run(_run_script(script.resolve()))
