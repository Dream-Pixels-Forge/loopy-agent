"""One-shot script to add docs URLs to every raise site in loopy/.

Reads dev-notes/ERROR_AUDIT.json, walks every "needs_work"
site, and appends a docs URL to the message (where the
message ends with a period or doesn't already have one).

The mapping from file → docs section is a best-effort hand
table below; for files not in the table we fall back to a
generic URL.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
AUDIT = REPO / "dev-notes" / "ERROR_AUDIT.json"

# Hand-mapped docs URLs per file. The anchor is chosen to match
# the error category at each site.
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

DOCS_URL_RE = re.compile(r"https://loopy\.dev/docs/[^\s\)]+#[a-z][a-z0-9-]+")


def has_docs_url(message: str) -> bool:
    return bool(DOCS_URL_RE.search(message))


def add_docs_url_to_raise(line: str, docs_url: str) -> str:
    """Append a docs URL to a raise line if it doesn't have one.

    Heuristics:
      * If the message ends with a closing ``"`` (Python string
        literal), insert the URL just before the closing quote.
      * If the message is an f-string, insert the URL inside the
        braces, then close the f-string.
      * If the message ends with ``)"`` (function call style),
        insert the URL just before the closing ``"``.
    """
    # Strip the trailing newline for our analysis.
    stripped = line.rstrip("\n")
    # Common: ``raise ValueError("message")``
    # The closing quote is the last ``"`` on the line. We need
    # to be careful with f-strings; for our codebase, the
    # message usually ends with a ``." or just a ``"``.
    # We'll do a string-literal walk: find the last ``"`` and
    # insert before it.
    idx = stripped.rfind('"')
    if idx < 0:
        return line  # can't safely patch — skip
    if DOCS_URL_RE.search(stripped[:idx] + stripped[idx:]):
        return line  # already has a URL
    # If there's a `."` ending (a sentence-style message), we
    # want to keep the period and add a space + URL.
    if stripped[idx - 1] == ".":
        new = stripped[:idx] + f" (see {docs_url})" + stripped[idx:]
    else:
        new = stripped[:idx] + f" (see {docs_url})" + stripped[idx:]
    return new + "\n"


def patch_file(rel_path: str, sites: list[dict]) -> int:
    """Patch the raise sites in ``rel_path`` so each one has a
    docs URL. Returns the number of sites fixed.
    """
    docs_url = FILE_DOCS.get(rel_path, "https://loopy.dev/docs/api#errors")
    path = REPO / rel_path
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    fixed = 0
    for site in sites:
        idx = site["line"] - 1
        if idx < 0 or idx >= len(lines):
            continue
        # Walk forward through continuation lines until we find
        # the closing quote. For our codebase, raise messages
        # are single-line, but multiline f-strings exist.
        end_idx = idx
        while end_idx < len(lines) and (
            lines[end_idx].count('"') % 2 != 0 or "\\" in lines[end_idx]
        ):
            end_idx += 1
        # Join the (possibly multiline) raise.
        block = "".join(lines[idx : end_idx + 1])
        if has_docs_url(block):
            continue
        # Apply the patch to the entire block.
        new_block = add_docs_url_to_raise(block, docs_url)
        if new_block == block:
            continue
        # Replace the block.
        new_lines = lines[:idx] + [new_block] + lines[end_idx + 1 :]
        lines = new_lines
        fixed += 1
    if fixed:
        path.write_text("".join(lines), encoding="utf-8")
    return fixed


def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    # Group sites by file, keep only needs_work.
    by_file: dict[str, list[dict]] = {}
    for site in audit["sites"]:
        if site["status"] == "passes":
            continue
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
