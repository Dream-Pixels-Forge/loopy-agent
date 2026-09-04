"""T1.3.2 — Error-message audit contract test.

Per the v1.1 GOAL.md Phase C contract:

  * Every ``raise`` site in ``loopy/`` must produce a
    docs-link-bearing error message
  * The pass threshold is >= 95% of all raise sites
  * The docs URL pattern: ``https://loopy.dev/docs/...#anchor``

This test pins the threshold and the regex; a separate
"every exception raised in the public API" test verifies
the per-exception message is well-formed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
AUDIT_PATH = REPO_ROOT / "dev-notes" / "ERROR_AUDIT.json"
DOCS_URL_RE = re.compile(r"https://loopy\.dev/docs/[^\s\)]+#[a-z][a-z0-9-]+")

# Sites that are exempt from the docs-link contract: they are
# re-exported from third-party packages where adding a docs
# link would be misleading, OR they are private sentinel
# exceptions used only by tests.
EXEMPT_FILES: set[str] = set()


def _run_audit() -> dict:
    """Run scripts/audit_errors.py and return the parsed JSON."""
    subprocess.run(
        [sys.executable, "scripts/audit_errors.py"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
    )
    return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))


class TestErrorAuditThreshold:
    def test_audit_at_least_95_percent_pass_rate(self):
        """The v1.1 GOAL.md Phase C target: >= 95% of raise sites
        have a docs URL in their message. Marked xfail for v1.1.0;
        the bulk fix is the goal of v1.1.1.
        """
        # Generate a fresh audit to ensure we're testing the
        # current state of the source.
        audit = _run_audit()
        pass_rate = audit["pass_rate_pct"]
        assert pass_rate >= 95.0, (
            f"error-message audit pass rate is {pass_rate}%; "
            f"need >= 95% (see https://loopy.dev/docs/contributing#error-audit). "
            f"{audit['needs_work']} of {audit['total_sites']} sites need work. "
            f"Run `python scripts/audit_errors.py` to see which."
        )

    def test_audit_json_exists_and_is_valid(self):
        """The audit script must produce a parseable JSON report."""
        assert AUDIT_PATH.exists(), f"missing {AUDIT_PATH}; run `python scripts/audit_errors.py`"
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        assert "sites" in data
        assert "total_sites" in data
        assert "passing" in data
        assert "needs_work" in data
        assert "pass_rate_pct" in data

    def test_docs_url_regex_matches_example(self):
        """The regex used by the audit must match canonical loopy.dev
        docs URLs (anchor must be lowercase-kebab)."""
        valid_urls = [
            "https://loopy.dev/docs/init#usage",
            "https://loopy.dev/docs/agent-loop#max-steps",
            "https://loopy.dev/docs/gateway#providers",
            "see https://loopy.dev/docs/init#path-traversal for details",
        ]
        for url in valid_urls:
            assert DOCS_URL_RE.search(url), f"regex missed: {url}"

    def test_docs_url_regex_rejects_invalid(self):
        invalid_urls = [
            "https://example.com/docs/init#usage",  # wrong host
            "https://loopy.dev/init#usage",  # missing /docs/
            "https://loopy.dev/docs/INIT#USAGE",  # uppercase anchor
            "https://loopy.dev/docs/init",  # missing #anchor
        ]
        for url in invalid_urls:
            assert not DOCS_URL_RE.search(url), f"regex falsely matched: {url}"


class TestKeyExceptionMessages:
    """A few well-known exception sites must include a docs link.

    These are the public-API exceptions users hit most often.
    Pinning them here means a future refactor that breaks the
    message format will fail CI immediately.
    """

    def test_loopconfig_max_steps_value_error(self):
        """LoopConfig.__post_init__ refuses max_steps=0 with a docs link."""
        from loopy import LoopConfig

        with pytest.raises(ValueError) as exc:
            LoopConfig(max_steps=0)
        assert DOCS_URL_RE.search(str(exc.value)), (
            f"LoopConfig max_steps=0 error has no docs link: {exc.value!r}"
        )

    def test_loopconfig_max_steps_with_interrupt(self):
        """Configuring interrupts on a zero-step loop is refused."""
        from loopy import LoopConfig

        with pytest.raises(ValueError) as exc:
            LoopConfig(max_steps=0, interrupt_before=["actor"])
        assert DOCS_URL_RE.search(str(exc.value)), (
            f"LoopConfig interrupt+max_steps=0 error has no docs link: {exc.value!r}"
        )

    def test_durable_dag_empty_steps(self):
        from loopy.durable import DAG

        with pytest.raises(ValueError) as exc:
            DAG(name="x", steps=[])
        assert DOCS_URL_RE.search(str(exc.value))

    def test_durable_step_name_path_traversal(self):
        from loopy.durable import Step

        async def _noop(s):
            return s

        with pytest.raises(ValueError) as exc:
            Step("../escape", run=_noop)
        assert DOCS_URL_RE.search(str(exc.value))

    def test_config_load_missing_file(self):
        from loopy.config import load

        with pytest.raises(FileNotFoundError) as exc:
            load("/nonexistent/loopy.yml")
        assert DOCS_URL_RE.search(str(exc.value))

    def test_config_load_invalid_provider(self):
        from loopy.config import LoopyConfig

        # We can't trigger load()'s validation through the file
        # round-trip easily (since the dataclass refuses to be
        # constructed in __post_init__). Test the constructor
        # directly: the public surface is the same ValueError.
        with pytest.raises(ValueError) as exc:
            LoopyConfig(provider="bogus")
        assert DOCS_URL_RE.search(str(exc.value))

    def test_federated_server_invalid_port_type(self):
        """FederatedServer rejects bad port at construction."""
        from loopy.a2a import AgentCapability, AgentCard
        from loopy.federate import FederatedServer

        card = AgentCard(
            name="x",
            description="",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        with pytest.raises((TypeError, ValueError)) as exc:
            FederatedServer(agent_card=card, port="not-a-port")  # type: ignore[arg-type]
        # TypeError for wrong type is acceptable here; just ensure
        # the error string includes the docs URL.
        assert DOCS_URL_RE.search(str(exc.value))

    def test_workflow_resume_malformed_token(self):
        from loopy.durable import Workflow

        with pytest.raises(ValueError) as exc:
            Workflow.resume("not-a-token")  # type: ignore[arg-type]
        assert DOCS_URL_RE.search(str(exc.value))

    def test_loopconfig_invalid_interrupts_with_max_steps(self):
        from loopy import LoopConfig

        with pytest.raises(ValueError) as exc:
            LoopConfig(max_steps=1, interrupt_before=["nope"])
        assert DOCS_URL_RE.search(str(exc.value))
