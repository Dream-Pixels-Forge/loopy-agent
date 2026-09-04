"""Second-pass patcher for raise sites.

Fixes the cases ``patch_errors.py`` missed:

* Multi-line raise blocks where the closing quote is on a
  line we don't always detect.
* f-strings ending in ``{expr!r}"`` (two quotes, last char
  on the *closing* quote, not the expression).
* Re-raise statements (``raise`` with no expression) — these
  carry no message and should be marked exempt in the audit.

After running this script, re-run ``audit_errors.py`` and the
result should be in the 95%+ range.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
AUDIT = REPO / "dev-notes" / "ERROR_AUDIT.json"

# Per-file docs URL (the section anchor changes based on
# what's wrong). A small lookup table covers the categories
# we care about; the rest fall back to a generic URL.
FILE_DOCS: dict[str, str] = {
    "loopy/a2a.py": "https://loopy.dev/docs/a2a#errors",
    "loopy/agents.py": "https://loopy.dev/docs/agents#errors",
    "loopy/durable.py": "https://loopy.dev/docs/durable#errors",
    "loopy/evals.py": "https://loopy.dev/docs/evals#errors",
    "loopy/federate.py": "https://loopy.dev/docs/federate#errors",
    "loopy/flow.py": "https://loopy.dev/docs/flow#errors",
    "loopy/gateway.py": "https://loopy.dev/docs/gateway#errors",
    "loopy/loop.py": "https://loopy.dev/docs/agent-loop#errors",
    "loopy/middleware.py": "https://loopy.dev/docs/middleware#errors",
    "loopy/multimodal.py": "https://loopy.dev/docs/multimodal#errors",
    "loopy/netutil.py": "https://loopy.dev/docs/security#ssrf-guard",
    "loopy/observe.py": "https://loopy.dev/docs/observability#errors",
    "loopy/plugins/__init__.py": "https://loopy.dev/docs/plugins#errors",
    "loopy/plugins/tools.py": "https://loopy.dev/docs/plugins#tools",
    "loopy/policies.py": "https://loopy.dev/docs/policies#errors",
    "loopy/skills.py": "https://loopy.dev/docs/skills#errors",
    "loopy/streaming.py": "https://loopy.dev/docs/streaming#errors",
    "loopy/verifier.py": "https://loopy.dev/docs/verifier#errors",
}

# Line offsets to skip in the audit (1-indexed). These are
# false positives (re-raise, internal sentinel propagation)
# that should not be counted against the pass rate.
EXEMPT_LINES: dict[str, set[int]] = {
    "loopy/a2a.py": {387, 388},
    "loopy/durable.py": {291},
    "loopy/federate.py": {185},
    "loopy/flow.py": {260},
    "loopy/gateway.py": {409},
    "loopy/loop.py": {478, 490, 581, 588},
    "loopy/middleware.py": {197, 230, 238, 423},
    "loopy/observe.py": {678, 700, 741, 777},
    "loopy/plugins/__init__.py": {175},
    "loopy/streaming.py": {187},
    "loopy/multimodal.py": {374},
    "loopy/policies.py": {179, 185},
}


def _has_docs_url(message: str) -> bool:
    return bool(re.search(r"https://loopy\.dev/docs/[^\s\)]+#[a-z][a-z0-9-]+", message))


def _patch_line(line: str, docs_url: str) -> str:
    """Append a docs URL to a single-line raise message."""
    if _has_docs_url(line):
        return line
    # f-string ending: ``f"...{expr!r}"``
    if line.rstrip().endswith('"') and line.rstrip()[-2] != "\\":
        idx = line.rstrip().rfind('"')
        stripped = line.rstrip()
        if stripped[idx - 1] == ".":
            new = stripped[:idx] + f" (see {docs_url})" + stripped[idx:] + "\n"
        else:
            new = stripped[:idx] + f" (see {docs_url})" + stripped[idx:] + "\n"
        return new
    return line  # couldn't safely patch — leave for manual fix


def patch_file(rel_path: str, sites: list[dict]) -> int:
    """Patch every needs_work raise site in ``rel_path`` to include
    a docs URL. Returns the number of sites fixed."""
    docs_url = FILE_DOCS.get(rel_path, "https://loopy.dev/docs/api#errors")
    path = REPO / rel_path
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    fixed = 0
    for site in sites:
        idx = site["line"] - 1
        if idx < 0 or idx >= len(lines):
            continue
        if "raise " not in lines[idx] and not lines[idx].lstrip().startswith("raise"):
            continue  # not actually a raise line (false positive)
        # Walk forward until we find a line ending in a closing
        # quote. The audit's ``text`` field is the unparsed message
        # — we need to find the actual string in the source.
        end_idx = idx
        while end_idx < len(lines) and (
            not _line_ends_with_quote(lines[end_idx]) or _has_docs_url(_join(lines, idx, end_idx))
        ):
            end_idx += 1
        if end_idx >= len(lines):
            continue
        # Patch the line that ends with the closing quote.
        new_line = _patch_line(lines[end_idx], docs_url)
        if new_line == lines[end_idx]:
            continue
        lines[end_idx] = new_line
        fixed += 1
    if fixed:
        path.write_text("".join(lines), encoding="utf-8")
    return fixed


def _line_ends_with_quote(line: str) -> bool:
    s = line.rstrip()
    if not s.endswith('"'):
        return False
    # Reject escaped trailing quotes
    if s.endswith('\\"'):
        return False
    return True


def _join(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start : end + 1])


def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    # Filter out the false-positive (re-raise / internal sentinel)
    # sites — these carry no message and shouldn't count against
    # the pass rate.
    needs_work = []
    for site in audit["sites"]:
        if site["status"] == "passes":
            continue
        exempt = EXEMPT_LINES.get(site["file"], set())
        if site["line"] in exempt:
            continue
        needs_work.append(site)
    # Group by file.
    by_file: dict[str, list[dict]] = {}
    for site in needs_work:
        by_file.setdefault(site["file"], []).append(site)
    total_fixed = 0
    for rel_path, sites in sorted(by_file.items()):
        n = patch_file(rel_path, sites)
        total_fixed += n
        print(f"{rel_path}: fixed {n} sites")
    print(f"\ntotal fixed: {total_fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
