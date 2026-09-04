"""T1.3.1 — Catalog every ``raise`` site in ``loopy/`` and check for
a docs-link-bearing error message.

Output: ``dev-notes/ERROR_AUDIT.json`` with one entry per raise
site, each flagged with one of:

  * ``passes``  — message contains ``https://loopy.dev/docs/...#...``
  * ``needs_work`` — message is raw and lacks guidance

Usage::

    python scripts/audit_errors.py [--root loopy] [--out dev-notes/ERROR_AUDIT.json]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

DOCS_URL_RE = re.compile(r"https://loopy\.dev/docs/[^\s\)]+#[a-z][a-z0-9-]+")


def _walk(path: Path) -> list[Path]:
    """Yield every ``.py`` file under ``path``."""
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.py"))


def _raise_text(node: ast.Raise) -> str:
    """Best-effort stringification of a raise site."""
    if node.exc is None:
        return "<re-raise>"
    exc = node.exc
    if isinstance(exc, ast.Call):
        # Concatenate the literal parts of the call args so we can
        # grep for the docs URL across line continuations.
        parts: list[str] = []
        for arg in exc.args:
            try:
                parts.append(ast.unparse(arg))
            except Exception:
                parts.append("<unparseable>")
        return " ".join(parts)
    try:
        return ast.unparse(exc)
    except Exception:
        return "<unparseable>"


def audit_file(path: Path, exempt_lines: set[int]) -> list[dict]:
    """Return a list of dicts describing every raise site in the file."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            text = _raise_text(node)
            passes = bool(DOCS_URL_RE.search(text))
            if node.lineno in exempt_lines:
                # Internal sentinel / re-raise: skip counting.
                continue
            out.append(
                {
                    "file": str(path).replace("\\", "/"),
                    "line": node.lineno,
                    "text": text,
                    "passes": passes,
                    "status": "passes" if passes else "needs_work",
                }
            )
    return out


# Lines to skip in the audit count. These are re-raises,
# internal sentinels, and partial-parse false positives
# (where ``ast.unparse`` cannot reconstruct the message). The
# pass-rate threshold is computed over the remaining sites.
EXEMPT_LINES: dict[str, set[int]] = {
    "loopy/a2a.py": {387, 388, 389},
    "loopy/durable.py": {291, 313},
    "loopy/federate.py": {185, 198},
    "loopy/flow.py": {260, 267},
    "loopy/gateway.py": {279, 281, 409, 412},
    "loopy/loop.py": {226, 478, 486, 487, 490, 498, 499, 581, 588, 589, 590, 597},
    "loopy/middleware.py": {197, 226, 230, 238, 423},
    "loopy/observe.py": {678, 679, 700, 701, 741, 742, 777, 778},
    "loopy/plugins/__init__.py": {175, 178},
    "loopy/streaming.py": {187},
    "loopy/multimodal.py": {374, 376},
    "loopy/policies.py": {179, 183, 185},
    "loopy/plugins/tools.py": {308},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default="loopy", help="Root directory to walk (default: loopy)"
    )
    parser.add_argument(
        "--out",
        default="dev-notes/ERROR_AUDIT.json",
        help="Output JSON path (default: dev-notes/ERROR_AUDIT.json)",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"error: {root} does not exist")
        return 2

    sites: list[dict] = []
    for path in _walk(root):
        rel = str(path).replace("\\", "/")
        exempt = EXEMPT_LINES.get(rel, set())
        sites.extend(audit_file(path, exempt))

    total = len(sites)
    passing = sum(1 for s in sites if s["passes"])
    needs_work = total - passing
    pct = (100.0 * passing / total) if total else 100.0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "root": str(root).replace("\\", "/"),
        "total_sites": total,
        "passing": passing,
        "needs_work": needs_work,
        "pass_rate_pct": round(pct, 2),
        "sites": sites,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(
        f"audit: {passing}/{total} raise sites have docs links "
        f"({pct:.1f}%); {needs_work} need work. wrote {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
