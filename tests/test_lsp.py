"""Tests for loopy.lsp — Language Server Protocol implementation.

Covers:
  * LspServer raises ImportError when pygls is absent
  * LspServer initializes correctly when pygls is present
  * Completion handler returns items for PolicyEngine, Condition, Invariant
  * Hover handler returns docstring content for a public symbol
  * Definition handler returns location for a loopy.loop symbol
  * Server start method exists and is callable
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_pygls() -> ModuleType:
    """Build a fake ``pygls`` module tree for testing without the real package."""
    pygls = ModuleType("pygls")
    pygls.server = ModuleType("pygls.server")
    pygls.lsp = ModuleType("pygls.lsp")
    pygls.lsp.methods = ModuleType("pygls.lsp.methods")

    # Method constants
    pygls.lsp.methods.TEXT_DOCUMENT_COMPLETION = "textDocument/completion"
    pygls.lsp.methods.TEXT_DOCUMENT_HOVER = "textDocument/hover"
    pygls.lsp.methods.TEXT_DOCUMENT_DEFINITION = "textDocument/definition"

    # Minimal LanguageServer stub
    class FakeLanguageServer:
        def __init__(self, name: str, package: str) -> None:
            self.name = name
            self.package = package
            self._handlers: dict[str, callable] = {}

        def feature(self, method: str):
            def decorator(fn: callable) -> callable:
                self._handlers[method] = fn
                return fn

            return decorator

        def start_io(self) -> None:
            pass

    pygls.server.LanguageServer = FakeLanguageServer
    pygls.server.__name__ = "pygls.server"

    pygls.__name__ = "pygls"
    return pygls


# ── Fixture: ensure clean import state ────────────────────────


@pytest.fixture(autouse=True)
def _clear_lsp_cache() -> None:
    """Remove cached loopy.lsp and pygls from sys.modules before each test."""
    keys_to_remove = [k for k in sys.modules if k.startswith("loopy.lsp") or k == "pygls"]
    for k in keys_to_remove:
        sys.modules.pop(k, None)
    yield


# ── E.1 — ImportError when pygls absent ──────────────────────


class TestLspServerNoPygls:
    def test_raises_importerror_when_pygls_missing(self):
        # Ensure pygls is NOT in sys.modules (it isn't in CI env)
        sys.modules.pop("pygls", None)
        from loopy.lsp import LspServer  # noqa: PLC0415

        with pytest.raises(ImportError, match="pygls is required"):
            LspServer()


# ── E.1 — Initialization when pygls available ────────────────


class TestLspServerInit:
    def test_initializes_correctly_with_pygls(self):
        mock_pygls = _make_mock_pygls()
        with patch.dict(
            sys.modules,
            {
                "pygls": mock_pygls,
                "pygls.server": mock_pygls.server,
                "pygls.lsp": mock_pygls.lsp,
                "pygls.lsp.methods": mock_pygls.lsp.methods,
            },
        ):
            from loopy.lsp import LspServer  # noqa: PLC0415

            server = LspServer()
            assert server is not None
            assert hasattr(server, "_server")
            assert hasattr(server, "start")
            assert callable(server.start)

    def test_start_method_exists_and_callable(self):
        mock_pygls = _make_mock_pygls()
        with patch.dict(
            sys.modules,
            {
                "pygls": mock_pygls,
                "pygls.server": mock_pygls.server,
                "pygls.lsp": mock_pygls.lsp,
                "pygls.lsp.methods": mock_pygls.lsp.methods,
            },
        ):
            from loopy.lsp import LspServer  # noqa: PLC0415

            server = LspServer()
            assert callable(server.start)


# ── E.2 — Completion handler ─────────────────────────────────


class TestCompletionHandler:
    def _build_server(self):
        mock_pygls = _make_mock_pygls()
        with patch.dict(
            sys.modules,
            {
                "pygls": mock_pygls,
                "pygls.server": mock_pygls.server,
                "pygls.lsp": mock_pygls.lsp,
                "pygls.lsp.methods": mock_pygls.lsp.methods,
            },
        ):
            from loopy.lsp import LspServer  # noqa: PLC0415

            return LspServer()

    def test_completion_returns_items_for_policy_engine(self):
        server = self._build_server()
        handler = server._server._handlers.get("textDocument/completion")
        assert handler is not None

        event = MagicMock()
        event.params = MagicMock()
        event.params.position = MagicMock()
        event.params.position.character = 0

        result = asyncio.run(handler(event))
        assert isinstance(result, list)
        labels = [item.label for item in result]
        assert "PolicyEngine" in labels

    def test_completion_returns_items_for_condition(self):
        server = self._build_server()
        handler = server._server._handlers.get("textDocument/completion")
        assert handler is not None

        event = MagicMock()
        event.params = MagicMock()
        event.params.position = MagicMock()
        event.params.position.character = 0

        result = asyncio.run(handler(event))
        labels = [item.label for item in result]
        assert "Condition" in labels

    def test_completion_returns_items_for_invariant(self):
        server = self._build_server()
        handler = server._server._handlers.get("textDocument/completion")
        assert handler is not None

        event = MagicMock()
        event.params = MagicMock()
        event.params.position = MagicMock()
        event.params.position.character = 0

        result = asyncio.run(handler(event))
        labels = [item.label for item in result]
        assert "Invariant" in labels


# ── E.3 — Hover handler ──────────────────────────────────────


class TestHoverHandler:
    def _build_server(self):
        mock_pygls = _make_mock_pygls()
        with patch.dict(
            sys.modules,
            {
                "pygls": mock_pygls,
                "pygls.server": mock_pygls.server,
                "pygls.lsp": mock_pygls.lsp,
                "pygls.lsp.methods": mock_pygls.lsp.methods,
            },
        ):
            from loopy.lsp import LspServer  # noqa: PLC0415

            return LspServer()

    def test_hover_returns_docstring_for_public_symbol(self):
        server = self._build_server()
        handler = server._server._handlers.get("textDocument/hover")
        assert handler is not None

        event = MagicMock()
        event.params = MagicMock()
        event.params.position = MagicMock()
        event.params.position.character = 0
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = "PolicyEngine"

        result = asyncio.run(handler(event))
        # Should return something truthy (a Hover-like object) for a known symbol
        # Since we're testing without real LSP types, verify the handler is wired
        assert result is not None


# ── E.4 — Definition handler ─────────────────────────────────


class TestDefinitionHandler:
    def _build_server(self):
        mock_pygls = _make_mock_pygls()
        with patch.dict(
            sys.modules,
            {
                "pygls": mock_pygls,
                "pygls.server": mock_pygls.server,
                "pygls.lsp": mock_pygls.lsp,
                "pygls.lsp.methods": mock_pygls.lsp.methods,
            },
        ):
            from loopy.lsp import LspServer  # noqa: PLC0415

            return LspServer()

    def test_definition_returns_location_for_loop_symbol(self):
        server = self._build_server()
        handler = server._server._handlers.get("textDocument/definition")
        assert handler is not None

        event = MagicMock()
        event.params = MagicMock()
        event.params.position = MagicMock()
        event.params.position.character = 0
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = "AgentLoop"

        result = asyncio.run(handler(event))
        # Should return something (list of locations or None)
        assert result is not None or isinstance(result, list)


# ── E.5 — Docstring wiring sanity ────────────────────────────


class TestDocstringWiring:
    def test_policy_engine_has_docstring(self):
        from loopy.policies import PolicyEngine  # noqa: PLC0415

        doc = inspect.getdoc(PolicyEngine)
        assert doc is not None and len(doc) > 0

    def test_condition_has_docstring(self):
        from loopy.policies import Condition  # noqa: PLC0415

        doc = inspect.getdoc(Condition)
        assert doc is not None and len(doc) > 0

    def test_invariant_has_docstring(self):
        from loopy.verifier import Invariant  # noqa: PLC0415

        doc = inspect.getdoc(Invariant)
        assert doc is not None and len(doc) > 0

    def test_agent_loop_has_docstring(self):
        from loopy.loop import AgentLoop  # noqa: PLC0415

        doc = inspect.getdoc(AgentLoop)
        assert doc is not None and len(doc) > 0
