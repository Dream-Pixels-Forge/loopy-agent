"""v1.2 — Minimal Language Server Protocol implementation for loopy-agent.

Provides autocomplete, hover docs, and go-to-definition for the
loopy public API symbols.

Usage::

    from loopy.lsp import LspServer
    LspServer().start()

Or from the CLI::

    loopy lsp
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("loopy.lsp")

try:
    from pygls.lsp.methods import (
        TEXT_DOCUMENT_COMPLETION,
        TEXT_DOCUMENT_DEFINITION,
        TEXT_DOCUMENT_HOVER,
    )
    from pygls.server import LanguageServer

    _HAS_PYGLS = True
except ImportError:
    _HAS_PYGLS = False
    LanguageServer = Any  # type: ignore[assignment,misc]


# ── LSP response types (minimal, pygls-agnostic) ─────────────


@dataclass
class CompletionItem:
    """A single completion suggestion."""

    label: str
    kind: int = 1  # SymbolKind.Class
    detail: str | None = None
    documentation: str | None = None


@dataclass
class Hover:
    """Hover response carrying markdown documentation."""

    contents: str


@dataclass
class Location:
    """Definition location: file URI + range."""

    uri: str
    range: dict[str, dict[str, int]]


# ── Symbol discovery ─────────────────────────────────────────


def _discover_loopy_symbols() -> dict[str, Any]:
    """Return a mapping of public symbol name -> actual object.

    Scans ``loopy.loop`` and ``loopy.policies`` plus the top-level
    ``loopy`` namespace for classes and functions with docstrings.
    """
    symbols: dict[str, Any] = {}

    # Scan loopy.loop
    try:
        import loopy.loop as loop_mod  # noqa: PLC0415

        for name in dir(loop_mod):
            if name.startswith("_"):
                continue
            obj = getattr(loop_mod, name)
            if inspect.isclass(obj) or inspect.isfunction(obj):
                symbols[name] = obj
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not scan loopy.loop: %s", exc)

    # Scan loopy.policies
    try:
        from loopy.policies import (  # noqa: PLC0415
            Condition,
            Policy,
            PolicyDecision,
            PolicyEngine,
            PolicyViolation,
        )

        for obj in (PolicyEngine, Condition, Policy, PolicyDecision, PolicyViolation):
            symbols[obj.__name__] = obj
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not scan loopy.policies: %s", exc)

    # Scan loopy.verifier
    try:
        from loopy.verifier import (  # noqa: PLC0415
            Invariant,
            Property,
            VerificationReport,
            VerificationSpec,
            VerifiedAgent,
        )

        for obj in (Invariant, Property, VerificationSpec, VerifiedAgent, VerificationReport):
            symbols[obj.__name__] = obj
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not scan loopy.verifier: %s", exc)

    # Top-level loopy namespace for anything else exported
    try:
        import loopy as loopy_pkg  # noqa: PLC0415

        for name in getattr(loopy_pkg, "__all__", []):
            if name in symbols:
                continue
            obj = getattr(loopy_pkg, name, None)
            if obj is not None and (inspect.isclass(obj) or inspect.isfunction(obj)):
                symbols[name] = obj
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not scan top-level loopy: %s", exc)

    return symbols


def _symbol_location(obj: Any) -> str | None:
    """Return the source file path for a symbol, or None."""
    try:
        source_file = inspect.getfile(obj)
        if source_file and source_file.endswith(".py"):
            return source_file
    except (OSError, TypeError):
        pass
    return None


def _symbol_lineno(obj: Any) -> int | None:
    """Return the source line number for a symbol, or None."""
    try:
        return inspect.getsourcelines(obj)[1]
    except (OSError, TypeError):
        return None


def _build_completion_items(symbols: dict[str, Any]) -> list[CompletionItem]:
    """Build CompletionItem list from discovered loopy symbols."""
    items: list[CompletionItem] = []
    for name, obj in sorted(symbols.items()):
        kind = "class" if inspect.isclass(obj) else "function"
        detail = f"{kind} {name}"
        doc = inspect.getdoc(obj)
        # Truncate long docs for the detail field
        detail_text = doc.split("\n")[0] if doc else None
        items.append(
            CompletionItem(
                label=name,
                kind=1 if inspect.isclass(obj) else 3,
                detail=detail,
                documentation=detail_text,
            )
        )
    return items


def _find_symbol_at_position(symbols: dict[str, Any], word: str) -> tuple[Any | None, str | None]:
    """Try to resolve a word to a symbol and its docstring.

    Matches on exact name or prefix (for partial completions).
    """
    # Exact match first
    if word in symbols:
        obj = symbols[word]
        doc = inspect.getdoc(obj)
        sig = None
        if inspect.isclass(obj) or inspect.isfunction(obj):
            try:
                sig = str(inspect.signature(obj))
            except ValueError:
                sig = None
        return obj, doc, sig

    # Prefix match
    matches = [n for n in symbols if n.startswith(word)]
    if matches:
        obj = symbols[matches[0]]
        doc = inspect.getdoc(obj)
        sig = None
        if inspect.isclass(obj) or inspect.isfunction(obj):
            try:
                sig = str(inspect.signature(obj))
            except ValueError:
                sig = None
        return obj, doc, sig

    return None, None, None


# ── Server ────────────────────────────────────────────────────


class LspServer:
    """Language server wrapping pygls for loopy-agent symbols."""

    def __init__(self) -> None:
        if not _HAS_PYGLS:
            raise ImportError(
                "pygls is required for the language server. "
                "Install it with: pip install loopy-agent[language-server] "
                "(see https://loopy.dev/docs/lsp#install)"
            )
        self._server = LanguageServer(
            name="loopy-agent-lsp",
            package="loopy.lsp",
        )
        self._symbols = _discover_loopy_symbols()
        self._completions = _build_completion_items(self._symbols)
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register LSP protocol handlers."""
        self._server.feature(TEXT_DOCUMENT_COMPLETION)(self._on_completion)
        self._server.feature(TEXT_DOCUMENT_HOVER)(self._on_hover)
        self._server.feature(TEXT_DOCUMENT_DEFINITION)(self._on_definition)

    async def _on_completion(self, event: Any) -> list[CompletionItem]:
        """Provide completions for loopy public API symbols."""
        return self._completions

    async def _on_hover(self, event: Any) -> Hover | None:
        """Provide hover documentation from docstrings."""
        try:
            params = event.params
            word = params.text_document_position.text or ""
        except AttributeError:
            word = ""

        word = word.strip()
        if not word:
            return None

        obj, doc, sig = _find_symbol_at_position(self._symbols, word)
        if obj is None or doc is None:
            return None

        parts = [doc]
        if sig:
            parts.append(f"\n\n```\n{sig}\n```")
        return Hover(contents="\n".join(parts))

    async def _on_definition(self, event: Any) -> list[Location] | None:
        """Go-to-definition for loopy.loop symbols."""
        try:
            params = event.params
            word = params.text_document_position.text or ""
        except AttributeError:
            word = ""

        symbol_name = word.strip()
        if not symbol_name:
            return None

        obj = self._symbols.get(symbol_name)
        if obj is None:
            return None

        source_file = _symbol_location(obj)
        line_no = _symbol_lineno(obj)
        if source_file is None:
            return None

        # Convert absolute path to URI
        uri = "file://" + source_file.replace("\\", "/")
        start_line = line_no - 1 if line_no else 0
        return [
            Location(
                uri=uri,
                range={
                    "start": {"line": start_line, "character": 0},
                    "end": {"line": start_line, "character": 0},
                },
            )
        ]

    def start(self) -> None:
        """Start the language server (stdio mode)."""
        self._server.start_io()


def main() -> None:
    """Entry point for ``loopy lsp``."""
    server = LspServer()
    server.start()


if __name__ == "__main__":
    main()
