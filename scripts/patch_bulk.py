"""Bulk patch v5: only touch lines that contain both ``raise`` and
a string literal. Skip docstring closes (a line that is just
``\"\"\"`` or contains a ``\"\"\"``) and skip function-call closes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
AUDIT = REPO / "dev-notes" / "ERROR_AUDIT.json"

FILE_DOCS: dict[str, str] = {
    "loopy/a2a.py": "https://loopy.dev/docs/a2a#errors",
    "loopy/durable.py": "https://loopy.dev/docs/durable#errors",
    "loopy/federate.py": "https://loopy.dev/docs/federate#errors",
    "loopy/flow.py": "https://loopy.dev/docs/flow#errors",
    "loopy/gateway.py": "https://loopy.dev/docs/gateway#errors",
    "loopy/loop.py": "https://loopy.dev/docs/agent-loop#errors",
    "loopy/netutil.py": "https://loopy.dev/docs/security#ssrf-guard",
    "loopy/observe.py": "https://loopy.dev/docs/observability#errors",
    "loopy/plugins/__init__.py": "https://loopy.dev/docs/plugins#errors",
    "loopy/policies.py": "https://loopy.dev/docs/policies#errors",
}

DOCS_URL_RE = re.compile(r"https://loopy\.dev/docs/[^\s\)]+#[a-z][a-z0-9-]+")


def _has_docs(text: str) -> bool:
    return bool(DOCS_URL_RE.search(text))


def _is_docstring_close(line) -> bool:
    """A line is a docstring boundary (and should NOT be patched
    as a raise message) if it contains any ``\"\"\"`` token.

    This catches:
      * a bare closer ``\"\"\"`` (possibly with leading whitespace
        and a trailing comma)
      * a single-line docstring ``\"\"\"text\"\"\"``
      * an opening ``\"\"\"`` (though those are rare as standalone
        lines)

    Accepts str or bytes.
    """
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    if '"""' in line or "'''" in line:
        return True
    return False


def _is_safe_to_patch(line) -> bool:
    """A line is safe to patch if it contains a string literal
    (with both opening and closing quotes on the line) that isn't
    itself a docstring boundary. Accepts str or bytes."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    if _is_docstring_close(line):
        return False
    return (line.count('"') >= 2 or line.count("'") >= 2)


def _line_ends_with_quote(line) -> bool:
    """Return True if the line ends with a closing quote, possibly
    followed by punctuation like ``)`` or ``,``.
    """
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    s = line.rstrip()
    # Strip trailing punctuation: ), ]], ,, etc.
    while s and s[-1] in ")]}":
        s = s[:-1].rstrip()
    if not (s.endswith('"') or s.endswith("'")):
        return False
    if s.endswith('\\"') or s.endswith("\\'"):
        return False
    return True


def _patch_file(rel_path: str, sites: list[dict]) -> int:
    p = REPO / rel_path
    text = p.read_text(encoding="utf-8")
    docs_url = FILE_DOCS.get(rel_path, "https://loopy.dev/docs/api#errors")
    lines = text.splitlines()
    fixed = 0
    for site in sites:
        line = site["line"]
        if line > len(lines):
            continue
        # Walk back to find ``raise``
        start_idx = line - 1
        while start_idx >= 0 and "raise " not in lines[start_idx]:
            start_idx -= 1
        if start_idx < 0:
            continue
        # Skip if the raise line itself is a docstring close
        if _is_docstring_close(lines[start_idx]):
            continue
        # Walk forward to find a line ending with a closing quote
        end_idx = start_idx
        # Search up to 20 lines forward (covers deep f-string expressions)
        while end_idx < len(lines) - 1 and end_idx - start_idx < 20 and not _line_ends_with_quote(lines[end_idx]):
            end_idx += 1
        if end_idx >= len(lines) or not _line_ends_with_quote(lines[end_idx]):
            continue
        # The line at end_idx must contain a string literal that
        # is NOT a docstring close.
        if not _is_safe_to_patch(lines[end_idx]):
            continue
        original = lines[end_idx]
        stripped = original.rstrip()
        last_quote_idx = max(stripped.rfind('"'), stripped.rfind("'"))
        if last_quote_idx < 0:
            continue
        if "loopy.dev/docs/" in stripped[: last_quote_idx + 1]:
            continue
        new_line = (
            stripped[:last_quote_idx]
            + f" (see {docs_url})"
            + stripped[last_quote_idx:]
            + "\n"
        )
        lines[end_idx] = new_line
        fixed += 1
    if fixed:
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fixed


def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    needs_work = [s for s in audit["sites"] if s["status"] == "needs_work"]
    by_file: dict[str, list[dict]] = {}
    for site in needs_work:
        by_file.setdefault(site["file"], []).append(site)
    total_fixed = 0
    for rel_path, sites in sorted(by_file.items()):
        n = _patch_file(rel_path, sites)
        total_fixed += n
        print(f"{rel_path}: fixed {n}/{len(sites)}")
    print(f"\ntotal: {total_fixed}/{len(needs_work)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
