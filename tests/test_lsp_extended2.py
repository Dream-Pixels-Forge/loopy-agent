"""Extended LSP tests — hover/definition edge cases for coverage gaps."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_pygls() -> ModuleType:
    pygls = ModuleType("pygls")
    pygls.server = ModuleType("pygls.server")
    pygls.lsp = ModuleType("pygls.lsp")
    pygls.lsp.methods = ModuleType("pygls.lsp.methods")
    pygls.lsp.methods.TEXT_DOCUMENT_COMPLETION = "textDocument/completion"
    pygls.lsp.methods.TEXT_DOCUMENT_HOVER = "textDocument/hover"
    pygls.lsp.methods.TEXT_DOCUMENT_DEFINITION = "textDocument/definition"

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


@pytest.fixture(autouse=True)
def _clear_lsp_cache() -> None:
    keys_to_remove = [k for k in sys.modules if k.startswith("loopy.lsp") or k == "pygls"]
    for k in keys_to_remove:
        sys.modules.pop(k, None)
    yield


def _build_server():
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


class TestHoverEmptyPrefix:
    """Coverage for lines 88-89, 103-104, 118-119."""

    def test_hover_empty_string_prefix_match(self):
        """An empty text should not match every symbol — it returns None."""
        server = _build_server()
        handler = server._server._handlers.get("textDocument/hover")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = ""
        result = asyncio.run(handler(event))
        assert result is None

    def test_hover_word_not_in_symbols(self):
        """A word that doesn't match any symbol returns None."""
        server = _build_server()
        handler = server._server._handlers.get("textDocument/hover")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = "zzz_not_a_symbol"
        result = asyncio.run(handler(event))
        assert result is None


class TestDefinitionEmptyPrefix:
    """Coverage for lines 131-132, 143-145, 152-153."""

    def test_definition_empty_string(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/definition")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = ""
        result = asyncio.run(handler(event))
        assert result is None

    def test_definition_unknown_symbol(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/definition")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = "nonexistent_xyz"
        result = asyncio.run(handler(event))
        assert result is None

    def test_definition_no_text_document_position(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/definition")
        event = MagicMock()
        event.params = MagicMock()
        del event.params.text_document_position
        result = asyncio.run(handler(event))
        assert result is None


class TestMainAndStart:
    """Coverage for lines 280, 307."""

    def test_main_calls_start(self):
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
            from loopy.lsp import main  # noqa: PLC0415

            start_called = []

            class FakeServer:
                def start(self):
                    start_called.append(True)

            with patch("loopy.lsp.LspServer", FakeServer):
                main()
            assert start_called == [True]

    def test_server_start_calls_start_io(self):
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
            server.start()
            # start_io should have been called
            assert server._server is not None


class TestSymbolHelpersAdditional:
    """Additional coverage for _symbol_location and _symbol_lineno."""

    def test_symbol_location_for_function(self):
        from loopy.lsp import _symbol_location  # noqa: PLC0415

        loc = _symbol_location(_symbol_location)
        assert isinstance(loc, str)
        assert loc.endswith(".py")

    def test_symbol_lineno_for_function(self):
        from loopy.lsp import _symbol_lineno  # noqa: PLC0415

        lineno = _symbol_lineno(_symbol_lineno)
        assert isinstance(lineno, int)
        assert lineno > 0

    def test_find_symbol_at_position_no_match(self):
        from loopy.lsp import _find_symbol_at_position  # noqa: PLC0415

        symbols: dict[str, object] = {}
        obj, doc, sig = _find_symbol_at_position(symbols, "nothing_here")
        assert obj is None
        assert doc is None
        assert sig is None
