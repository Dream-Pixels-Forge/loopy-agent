from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.dev")


async def run_dev(script_path: str) -> None:
    """Watch a script and re-run it on changes using watchfiles."""
    try:
        import watchfiles
    except ImportError as err:  # pragma: no cover — tested via mock
        raise ImportError(
            "watchfiles is required for `loopy dev`. Install it with: pip install loopy-agent[dev]"
        ) from err

    path = Path(script_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")

    logger.info("Watching %s for changes...", path)
    async for changes in watchfiles.awatch(path):
        logger.info("Changes detected: %s", changes)
        await _run_script(path)


async def _run_script(path: Path) -> None:
    """Run a Python script as an async module."""
    spec = importlib.util.spec_from_file_location("dev_script", path)
    if spec is None or spec.loader is None:
        logger.error("Cannot load script: %s", path)
        return

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error("Script error: %s", e)


class DevServer:
    """Scaffold for the hot-reload dev server with WebSocket bridge.

    TODO: wire up the WebSocket endpoint for live error streaming to
    the workspace. The actual WS server will be added in a follow-up.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        script_path: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.script_path = script_path

    async def handle_ws(self, path: str, receive: Any, send: Any) -> None:
        """TODO: Implement WebSocket handler for live error output."""
        await send({"type": "error", "message": "not yet implemented"})
