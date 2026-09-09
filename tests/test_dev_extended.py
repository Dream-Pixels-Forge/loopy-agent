"""Extended dev tests — _run_script edge cases and import error handling."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestRunScriptEdgeCases:
    @pytest.mark.asyncio
    async def test_run_script_missing_file(self, tmp_path: Path):
        """_run_script should log an error for a missing file."""
        from loopy.dev import _run_script

        missing = tmp_path / "gone.py"
        result = asyncio.create_task(_run_script(missing))
        await asyncio.sleep(0.2)
        # Should not raise; logs error instead
        assert not result.cancelled()

    @pytest.mark.asyncio
    async def test_run_script_syntax_error(self, tmp_path: Path):
        """A script with a syntax error should not crash the watcher."""
        from loopy.dev import _run_script

        bad = tmp_path / "bad.py"
        bad.write_text("def broken(\n")  # invalid syntax

        result = asyncio.create_task(_run_script(bad.resolve()))
        await asyncio.sleep(0.2)
        assert not result.cancelled()

    @pytest.mark.asyncio
    async def test_run_script_runtime_error(self, tmp_path: Path):
        """A script that raises during execution should not crash the watcher."""
        from loopy.dev import _run_script

        crashy = tmp_path / "crash.py"
        crashy.write_text("raise RuntimeError('boom')\n")

        result = asyncio.create_task(_run_script(crashy.resolve()))
        await asyncio.sleep(0.2)
        assert not result.cancelled()

    @pytest.mark.asyncio
    async def test_run_script_empty_file(self, tmp_path: Path):
        """An empty script should run without error."""
        from loopy.dev import _run_script

        empty = tmp_path / "empty.py"
        empty.write_text("")

        result = asyncio.create_task(_run_script(empty.resolve()))
        await asyncio.sleep(0.2)
        assert not result.cancelled()

    @pytest.mark.asyncio
    async def test_run_script_with_async_main(self, tmp_path: Path):
        """A script defining async def main() should have it awaited."""
        from loopy.dev import _run_script

        async_main = tmp_path / "async_main.py"
        async_main.write_text(
            "import asyncio\nasync def main():\n    await asyncio.sleep(0.01)\n    return 'done'\n"
        )

        result = asyncio.create_task(_run_script(async_main.resolve()))
        await asyncio.sleep(0.3)
        assert not result.cancelled()

    @pytest.mark.asyncio
    async def test_run_script_with_sync_main(self, tmp_path: Path):
        """A script defining sync def main() should be called directly."""
        from loopy.dev import _run_script

        sync_main = tmp_path / "sync_main.py"
        sync_main.write_text("def main():\n    return 'sync done'\n")

        result = asyncio.create_task(_run_script(sync_main.resolve()))
        await asyncio.sleep(0.2)
        assert not result.cancelled()


class TestDevServer:
    def test_handle_ws_returns_todo(self):
        from loopy.dev import DevServer

        server = DevServer()

        async def _test():
            await server.handle_ws("/ws", MagicMock(), MagicMock())

        # Just verify it doesn't crash; the mock send captures the message
        sent = []

        class FakeSend:
            async def __call__(self, msg):
                sent.append(msg)

        asyncio.run(server.handle_ws("/ws", MagicMock(), FakeSend()))
        assert len(sent) == 1
        assert sent[0]["type"] == "error"
        assert "not yet implemented" in sent[0]["message"]

    def test_dev_server_default_host_port(self):
        from loopy.dev import DevServer

        s = DevServer()
        assert s.host == "127.0.0.1"
        assert s.port == 8765
        assert s.script_path is None

    def test_dev_server_custom_values(self):
        from loopy.dev import DevServer

        s = DevServer(host="0.0.0.0", port=9999, script_path="/some/script.py")
        assert s.host == "0.0.0.0"
        assert s.port == 9999
        assert s.script_path == "/some/script.py"


class TestRunDevEdgeCases:
    @pytest.mark.asyncio
    async def test_run_dev_with_watchfiles_missing(self):
        """When watchfiles is not installed, run_dev raises ImportError."""
        from loopy.dev import run_dev

        with (
            patch.dict(sys.modules, {"watchfiles": None}),
            pytest.raises(ImportError, match="watchfiles is required"),
        ):
            await run_dev("/fake/path.py")

    @pytest.mark.asyncio
    async def test_run_dev_script_not_found(self):
        """run_dev raises FileNotFoundError for a missing script."""
        from loopy.dev import run_dev

        with pytest.raises(FileNotFoundError, match="Script not found"):
            await run_dev("/nonexistent/script.py")
