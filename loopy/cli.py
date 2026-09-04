"""
Loopy CLI — Command-line interface for loopy toolkit.

Usage:
    loopy chat "What is 2+2?" --provider openai
    loopy guard "My SSN is 123-45-6789"
    loopy cache stats
    loopy trace export
    loopy eval run --suite math.json
    loopy agent list
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading

from loopy import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog="loopy",
        description="🔄 Loopy — 21 Essential AI Concepts in one toolkit",
    )
    parser.add_argument("--version", action="version", version=f"loopy {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- chat command ---
    chat_parser = subparsers.add_parser("chat", help="Send a chat message")
    chat_parser.add_argument("message", help="Message to send")
    chat_parser.add_argument("--provider", "-p", help="Provider name (openai, anthropic, ollama)")
    chat_parser.add_argument("--model", "-m", default="gpt-4", help="Model name")
    chat_parser.add_argument("--system", "-s", help="System prompt")
    chat_parser.add_argument("--temperature", "-t", type=float, default=0.7)
    chat_parser.add_argument("--max-tokens", type=int, default=1000)

    # --- guard command ---
    guard_parser = subparsers.add_parser("guard", help="Check text with guardrails")
    guard_parser.add_argument("text", help="Text to check")
    guard_parser.add_argument("--direction", choices=["input", "output"], default="input")
    guard_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # --- cache command ---
    cache_parser = subparsers.add_parser("cache", help="Cache operations")
    cache_sub = cache_parser.add_subparsers(dest="cache_action")
    cache_sub.add_parser("stats", help="Show cache statistics")
    cache_sub.add_parser("clear", help="Clear cache")

    # --- trace command ---
    trace_parser = subparsers.add_parser("trace", help="Tracing operations")
    trace_sub = trace_parser.add_subparsers(dest="trace_action")
    trace_sub.add_parser("export", help="Export traces as JSON")
    trace_sub.add_parser("stats", help="Show trace statistics")

    # --- eval command ---
    eval_parser = subparsers.add_parser("eval", help="Evaluation operations")
    eval_sub = eval_parser.add_subparsers(dest="eval_action")
    run_eval = eval_sub.add_parser("run", help="Run evaluation suite")
    run_eval.add_argument("--suite", required=True, help="Path to eval suite JSON")
    run_eval.add_argument("--model", default="gpt-4", help="Model to evaluate")

    # --- agent command ---
    agent_parser = subparsers.add_parser("agent", help="Multi-agent operations")
    agent_sub = agent_parser.add_subparsers(dest="agent_action")
    agent_sub.add_parser("list", help="List registered agents")

    # --- init command (v1.1) ---
    init_parser = subparsers.add_parser(
        "init",
        help="Scaffold a new loopy-agent project in ./<name>",
    )
    init_parser.add_argument("project_name", help="Project directory name")
    init_parser.add_argument(
        "--no-test",
        action="store_true",
        help="Skip generating tests/test_agent.py",
    )

    # --- serve command (v1.0.0) ---
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start a federated HTTP server exposing the agent",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind (default 8080; use 0 for OS-assigned)",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--agent",
        default=None,
        help="Optional path to a Python module exposing CARD / agent_card",
    )

    # --- info command ---
    subparsers.add_parser("info", help="Show loopy info")

    return parser


def cmd_chat(args: argparse.Namespace) -> None:
    """Handle chat command."""
    from loopy.gateway import Gateway, ModelProvider, ProviderConfig

    async def _chat():
        gateway = Gateway()

        # Auto-configure based on provider
        provider_name = args.provider or "openai"

        if provider_name == "openai":
            gateway.add_provider(
                "openai",
                ProviderConfig(
                    provider=ModelProvider.OPENAI,
                    model=args.model,
                ),
            )
        elif provider_name == "anthropic":
            gateway.add_provider(
                "anthropic",
                ProviderConfig(
                    provider=ModelProvider.ANTHROPIC,
                    model=args.model,
                ),
            )
        elif provider_name == "ollama":
            gateway.add_provider(
                "ollama",
                ProviderConfig(
                    provider=ModelProvider.OLLAMA,
                    model=args.model,
                ),
            )

        try:
            response = await gateway.chat(
                message=args.message,
                provider=provider_name,
                system=args.system,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )

            print(f"\n{'=' * 60}")
            print(f"Provider: {response.provider.value}")
            print(f"Model: {response.model}")
            print(f"Tokens: {response.tokens_used}")
            print(f"Latency: {response.latency_ms:.0f}ms")
            print(f"{'=' * 60}\n")
            print(response.content)

        except Exception as e:
            print(f"Error: {e}")
            print("\nNote: Set your API key as an environment variable:")
            print("  export OPENAI_API_KEY=sk-...")
            print("  export ANTHROPIC_API_KEY=sk-ant-...")
        finally:
            await gateway.close()

    asyncio.run(_chat())


def cmd_guard(args: argparse.Namespace) -> None:
    """Handle guard command."""
    from loopy.guardrails import GuardrailPipeline

    pipeline = GuardrailPipeline()

    if args.direction == "input":
        result = pipeline.filter_input(args.text)
    else:
        result = pipeline.filter_output(args.text)

    if args.json:
        print(
            json.dumps(
                {
                    "action": result.action.value,
                    "original": result.original,
                    "filtered": result.filtered,
                    "reasons": result.reasons,
                },
                indent=2,
            )
        )
    else:
        print(f"\n{'=' * 60}")
        print(f"Direction: {args.direction}")
        print(f"Action: {result.action.value}")
        print(f"{'=' * 60}")

        if result.reasons:
            print(f"\nReasons: {', '.join(result.reasons)}")

        if result.original != result.filtered:
            print(f"\nOriginal:  {result.original}")
            print(f"Filtered:  {result.filtered}")
        else:
            print("\nText passed all checks [OK]")


def cmd_cache(args: argparse.Namespace) -> None:
    """Handle cache command."""
    from loopy.cache import LLMCache

    cache = LLMCache()

    if args.cache_action == "stats":
        stats = cache.stats()
        print(f"\n{'=' * 60}")
        print("Cache Statistics")
        print(f"{'=' * 60}")
        print(f"  Hits:       {stats.hits}")
        print(f"  Misses:     {stats.misses}")
        print(f"  Hit Rate:   {stats.hit_rate:.1%}")
        print(f"  Saved:      {stats.total_saved_tokens} tokens")
        print(f"  Est. Savings: ${stats.estimated_savings:.2f}")

    elif args.cache_action == "clear":
        cache.clear()
        print("Cache cleared ✓")


def cmd_trace(args: argparse.Namespace) -> None:
    """Handle trace command."""
    from loopy.observe import Tracer

    tracer = Tracer()

    if args.trace_action == "export":
        output = tracer.export_json()
        print(output)

    elif args.trace_action == "stats":
        spans = tracer.get_spans()
        print(f"\n{'=' * 60}")
        print("Trace Statistics")
        print(f"{'=' * 60}")
        print(f"  Total Spans: {len(spans)}")


def cmd_eval(args: argparse.Namespace) -> None:
    """Handle eval command."""
    import asyncio
    from pathlib import Path

    from loopy.evals import EvalCase, EvalSuite, Evaluator

    if args.eval_action == "run":
        suite_path = Path(args.suite)
        if not suite_path.exists():
            print(f"Error: Suite file not found: {suite_path}")
            return

        data = json.loads(suite_path.read_text())
        suite = EvalSuite(
            name=data.get("name", "unnamed"),
            cases=[
                EvalCase(
                    name=c["name"],
                    input_text=c["input_text"],
                    expected_output=c.get("expected_output"),
                    criteria=c.get("criteria", []),
                )
                for c in data.get("cases", [])
            ],
        )

        async def model_fn(prompt: str) -> str:
            return f"[Simulated response to: {prompt}]"

        evaluator = Evaluator(model_fn=model_fn)

        async def run_eval():
            report = await evaluator.run(suite)
            print(f"\n{'=' * 60}")
            print(f"Evaluation Report: {suite.name}")
            print(f"{'=' * 60}")
            print(json.dumps(report.summary(), indent=2))

        asyncio.run(run_eval())


def cmd_agent(args: argparse.Namespace) -> None:
    """Handle agent command."""
    from loopy.agents import Orchestrator

    orchestrator = Orchestrator()

    if args.agent_action == "list":
        agents = orchestrator.list_agents()
        print(f"\n{'=' * 60}")
        print("Registered Agents")
        print(f"{'=' * 60}")

        if agents:
            for agent in agents:
                print(f"  • {agent.name}: {agent.description}")
        else:
            print("  No agents registered")
            print("\n  Add agents programmatically:")
            print("    from loopy.agents import Orchestrator, SubAgent")


def cmd_init(args: argparse.Namespace) -> None:
    """v1.1 — scaffold a new loopy-agent project.

    Generates a self-contained directory with a ``pyproject.toml``
    pinning ``loopy-agent[all]``, an ``agent.py`` that uses
    ``TestModel`` (so no API key is required to run it), a
    ``loopy.yml`` config, a ``.gitignore``, a ``README.md``
    pointing at loopy.dev, and a single ``tests/test_agent.py``
    that runs without any network or credentials.

    Negative controls:
      * Refuses to overwrite an existing non-empty directory.
      * Refuses project names containing ``/`` or ``..`` (path
        traversal guard).
      * Refuses absolute path names.
    """
    from pathlib import Path

    name = args.project_name
    if not name:
        raise ValueError("project name must be non-empty (see https://loopy.dev/docs/init#usage)")
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(
            f"project name {name!r} must not contain '/' or '..' "
            "(see https://loopy.dev/docs/init#path-traversal)"
        )
    if Path(name).is_absolute():
        raise ValueError(
            f"project name {name!r} must be relative, not absolute "
            "(see https://loopy.dev/docs/init#path-traversal)"
        )

    project_dir = Path(name)
    if project_dir.exists() and any(project_dir.iterdir()):
        raise FileExistsError(
            f"directory {name!r} already exists and is not empty; "
            "refusing to overwrite (see https://loopy.dev/docs/init#refuse-overwrite)"
        )
    project_dir.mkdir(parents=True, exist_ok=True)

    _write_pyproject(project_dir)
    _write_agent_py(project_dir)
    _write_loopy_yml(project_dir)
    _write_gitignore(project_dir)
    _write_readme(project_dir)
    if not args.no_test:
        (project_dir / "tests").mkdir(exist_ok=True)
        _write_test_agent(project_dir)

    print(
        f"Created {name}/ with:\n"
        f"  - pyproject.toml  (uses loopy-agent[all])\n"
        f"  - agent.py        (TestModel-backed AgentLoop)\n"
        f"  - loopy.yml       (provider: test, max_steps: 3)\n"
        f"  - .gitignore\n"
        f"  - README.md\n"
        + ("  - tests/test_agent.py\n" if not args.no_test else "")
        + f"\nNext:\n  cd {name}\n  pip install -e .[all]\n  python agent.py\n"
        + ("  pytest\n" if not args.no_test else "")
    )


_PYPROJECT_TEMPLATE = """\
[project]
name = "{name}"
version = "0.1.0"
description = "A loopy-agent project scaffolded by `loopy init`."
requires-python = ">=3.10"
dependencies = [
    "loopy-agent[all]>=1.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""


_AGENT_PY_TEMPLATE = '''\
"""Minimal loopy-agent entry point.

Run with::

    python agent.py

No API key required — uses TestModel under the hood.
"""

import asyncio

from loopy import AgentLoop, LoopConfig
from loopy.gateway import TestModel


async def main() -> None:
    config = LoopConfig(
        model=TestModel(),
        max_steps=3,
    )
    loop = AgentLoop(config)
    result = await loop.run("Hello from loopy-agent!")
    if isinstance(result, list):
        last = result[-1]
        print(f"agent output: {last.action}")


if __name__ == "__main__":
    asyncio.run(main())
'''


_LOOPY_YML_TEMPLATE = """\
# v1.1 — minimal loopy-agent config.
# See https://loopy.dev/docs/init#loopy-yml

provider: test
model: TestModel
max_steps: 3
interrupt_before: []
interrupt_after: []
"""


_GITIGNORE_TEMPLATE = """\
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
build/
dist/

# Virtual envs
.venv/
venv/
env/

# Test + coverage
.pytest_cache/
.coverage
htmlcov/
.ruff_cache/

# Editor
.vscode/
.idea/
.DS_Store
"""


_README_TEMPLATE = """\
# {name}

A loopy-agent project scaffolded by `loopy init`.

## Quick start

```bash
pip install -e .[all]
python agent.py
```

## Configure

Edit `loopy.yml` to switch providers or add interrupt gates.
See https://loopy.dev/docs/init for the full reference.

## Test

```bash
pytest
```
"""


_TEST_AGENT_TEMPLATE = '''\
"""Smoke test: the scaffolded agent runs without an API key."""

from __future__ import annotations

import asyncio

import pytest

from agent import main


@pytest.mark.asyncio
async def test_agent_main_runs(capsys: pytest.CaptureFixture[str]) -> None:
    await main()
    captured = capsys.readouterr()
    assert "agent output:" in captured.out
'''


def _write_pyproject(project_dir) -> None:
    (project_dir / "pyproject.toml").write_text(
        _PYPROJECT_TEMPLATE.format(name=project_dir.name),
        encoding="utf-8",
    )


def _write_agent_py(project_dir) -> None:
    (project_dir / "agent.py").write_text(_AGENT_PY_TEMPLATE, encoding="utf-8")


def _write_loopy_yml(project_dir) -> None:
    (project_dir / "loopy.yml").write_text(_LOOPY_YML_TEMPLATE, encoding="utf-8")


def _write_gitignore(project_dir) -> None:
    (project_dir / ".gitignore").write_text(_GITIGNORE_TEMPLATE, encoding="utf-8")


def _write_readme(project_dir) -> None:
    (project_dir / "README.md").write_text(
        _README_TEMPLATE.format(name=project_dir.name),
        encoding="utf-8",
    )


def _write_test_agent(project_dir) -> None:
    (project_dir / "tests" / "test_agent.py").write_text(_TEST_AGENT_TEMPLATE, encoding="utf-8")


def cmd_info(args: argparse.Namespace) -> None:
    """Show loopy info."""
    print(f"""
{"=" * 60}
 Loopy - 21 Essential AI Concepts in One Toolkit
{"=" * 60}

Modules:
  - loop        Agentic Loops (Plan->Act->Observe->Reflect)
  - gateway     AI Gateway (OpenAI/Anthropic/Ollama)
  - guardrails  PII & Jailbreak Protection
  - evals       Judge-based Evaluation
  - cache       Semantic Token Caching
  - observe     Traces & Metrics
  - mcp         Model Context Protocol
  - agents      Multi-Agent Orchestration

Version: {__version__}
""")


def cmd_serve(args: argparse.Namespace) -> None:
    """v1.0.0 — start a federated HTTP server exposing an Agent Card
    and ``POST /tasks`` endpoint.

    If ``--agent`` is provided, the matching Python module is
    loaded and its ``CARD`` (or ``card`` / ``AGENT_CARD`` /
    ``agent_card``) attribute is used as the Agent Card. Otherwise
    a default placeholder card is served.
    """
    # Local imports keep the CLI fast and avoid pulling
    # ``loopy.federate`` when users run other subcommands.
    from loopy.a2a import AgentCapability, AgentCard
    from loopy.federate import FederatedServer, build_agent_card_from_module

    if args.agent:
        card = build_agent_card_from_module(args.agent)
    else:
        card = AgentCard(
            name="loopy-default",
            description="Default loopy agent (no --agent module supplied)",
            version="1.0.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )

    server = FederatedServer(agent_card=card, host=args.host, port=args.port)
    server.start()
    bound = server.port
    print(
        f"loopy federated server listening on http://{args.host}:{bound}\n"
        f"  Agent Card:  http://{args.host}:{bound}/.well-known/agent-card.json\n"
        f"  POST /tasks: http://{args.host}:{bound}/tasks\n"
    )
    try:
        # Block forever; Ctrl+C kills the thread.
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nshutting down...")
    finally:
        server.shutdown()


def main() -> None:
    """Main CLI entry point."""
    # Force UTF-8 output on Windows
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = create_parser()
    args = parser.parse_args()

    commands = {
        "chat": cmd_chat,
        "guard": cmd_guard,
        "cache": cmd_cache,
        "trace": cmd_trace,
        "eval": cmd_eval,
        "agent": cmd_agent,
        "init": cmd_init,  # v1.1
        "serve": cmd_serve,  # v1.0.0
        "info": cmd_info,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
