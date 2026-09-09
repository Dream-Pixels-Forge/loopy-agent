"""Extended LSP tests — hover/definition edge cases and _find_symbol branches."""

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


class TestHoverEdgeCases:
    def test_hover_returns_none_for_unknown_symbol(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/hover")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = "totally_fake_symbol_xyz"
        result = asyncio.run(handler(event))
        assert result is None

    def test_hover_attribute_error_falls_back_to_empty_word(self):
        """event.params exists but text_document_position is missing."""
        server = _build_server()
        handler = server._server._handlers.get("textDocument/hover")
        event = MagicMock()
        event.params = MagicMock()
        # No text_document_position attribute → triggers except branch
        del event.params.text_document_position
        result = asyncio.run(handler(event))
        assert result is None  # empty word now returns None

    def test_hover_no_params_at_all(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/hover")
        event = MagicMock()
        # No params at all → triggers except AttributeError branch
        del event.params
        result = asyncio.run(handler(event))
        assert result is None  # empty word now returns None

    def test_hover_with_docstring_and_sig(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/hover")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = "PolicyEngine"
        result = asyncio.run(handler(event))
        assert result is not None
        assert "Policy" in result.contents
        assert "audit_sink" in result.contents


class TestDefinitionEdgeCases:
    def test_definition_returns_none_for_unknown_symbol(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/definition")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = "nonexistent_class_abc"
        result = asyncio.run(handler(event))
        assert result is None

    def test_definition_returns_none_for_empty_word(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/definition")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = ""
        result = asyncio.run(handler(event))
        assert result is None

    def test_definition_attribute_error_falls_back(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/definition")
        event = MagicMock()
        event.params = MagicMock()
        del event.params.text_document_position
        result = asyncio.run(handler(event))
        assert result is None

    def test_definition_returns_location_with_file_uri(self):
        server = _build_server()
        handler = server._server._handlers.get("textDocument/definition")
        event = MagicMock()
        event.params = MagicMock()
        event.params.text_document_position = MagicMock()
        event.params.text_document_position.text = "AgentLoop"
        result = asyncio.run(handler(event))
        assert result is not None
        if result:
            loc = result[0]
            assert loc.uri.startswith("file://")
            assert "start" in loc.range
            assert "end" in loc.range


class TestFindSymbolAtPosition:
    def test_exact_match(self):
        from loopy.lsp import _find_symbol_at_position  # noqa: PLC0415

        symbols = {"Foo": type("Foo", (), {"__doc__": "A foo class"})}
        obj, doc, sig = _find_symbol_at_position(symbols, "Foo")
        assert obj is not None
        assert doc == "A foo class"

    def test_prefix_match(self):
        from loopy.lsp import _find_symbol_at_position  # noqa: PLC0415

        symbols = {"FooBar": type("FooBar", (), {"__doc__": "A bar class"})}
        obj, doc, sig = _find_symbol_at_position(symbols, "Foo")
        assert obj is not None
        assert doc == "A bar class"

    def test_no_match_returns_nones(self):
        from loopy.lsp import _find_symbol_at_position  # noqa: PLC0415

        symbols: dict[str, object] = {}
        obj, doc, sig = _find_symbol_at_position(symbols, "nothing")
        assert obj is None
        assert doc is None
        assert sig is None


class TestSymbolHelpers:
    def test_symbol_location_returns_path(self):
        from loopy.lsp import _symbol_location  # noqa: PLC0415

        loc = _symbol_location(_symbol_location)
        assert loc is not None
        assert loc.endswith(".py")

    def test_symbol_lineno_returns_int(self):
        from loopy.lsp import _symbol_lineno  # noqa: PLC0415

        lineno = _symbol_lineno(_symbol_lineno)
        assert isinstance(lineno, int)
        assert lineno > 0


class TestMain:
    def test_main_calls_server_start(self):
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

            # Patch start_io to avoid blocking
            with patch("loopy.lsp.LanguageServer.start_io"):
                main()  # should not raise


class TestCompletionItems:
    def test_completion_items_have_required_fields(self):
        from loopy.lsp import CompletionItem  # noqa: PLC0415

        item = CompletionItem(label="Foo", kind=1, detail="class Foo", documentation="A foo")
        assert item.label == "Foo"
        assert item.kind == 1
        assert item.detail == "class Foo"
        assert item.documentation == "A foo"

    def test_completion_item_defaults(self):
        from loopy.lsp import CompletionItem  # noqa: PLC0415

        item = CompletionItem(label="Bar")
        assert item.kind == 1
        assert item.detail is None
        assert item.documentation is None
