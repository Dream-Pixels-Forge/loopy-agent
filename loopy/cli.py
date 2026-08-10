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

from loopy import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog="loopy",
        description="🔄 Loopy — 19 Essential AI Concepts in one toolkit",
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
            gateway.add_provider("openai", ProviderConfig(
                provider=ModelProvider.OPENAI,
                model=args.model,
            ))
        elif provider_name == "anthropic":
            gateway.add_provider("anthropic", ProviderConfig(
                provider=ModelProvider.ANTHROPIC,
                model=args.model,
            ))
        elif provider_name == "ollama":
            gateway.add_provider("ollama", ProviderConfig(
                provider=ModelProvider.OLLAMA,
                model=args.model,
            ))
        
        try:
            response = await gateway.chat(
                message=args.message,
                provider=provider_name,
                system=args.system,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            
            print(f"\n{'='*60}")
            print(f"Provider: {response.provider.value}")
            print(f"Model: {response.model}")
            print(f"Tokens: {response.tokens_used}")
            print(f"Latency: {response.latency_ms:.0f}ms")
            print(f"{'='*60}\n")
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
        print(json.dumps({
            "action": result.action.value,
            "original": result.original,
            "filtered": result.filtered,
            "reasons": result.reasons,
        }, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"Direction: {args.direction}")
        print(f"Action: {result.action.value}")
        print(f"{'='*60}")
        
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
        print(f"\n{'='*60}")
        print("Cache Statistics")
        print(f"{'='*60}")
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
        print(f"\n{'='*60}")
        print("Trace Statistics")
        print(f"{'='*60}")
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
            print(f"\n{'='*60}")
            print(f"Evaluation Report: {suite.name}")
            print(f"{'='*60}")
            print(json.dumps(report.summary(), indent=2))
        
        asyncio.run(run_eval())


def cmd_agent(args: argparse.Namespace) -> None:
    """Handle agent command."""
    from loopy.agents import Orchestrator
    
    orchestrator = Orchestrator()
    
    if args.agent_action == "list":
        agents = orchestrator.list_agents()
        print(f"\n{'='*60}")
        print("Registered Agents")
        print(f"{'='*60}")
        
        if agents:
            for agent in agents:
                print(f"  • {agent.name}: {agent.description}")
        else:
            print("  No agents registered")
            print("\n  Add agents programmatically:")
            print("    from loopy.agents import Orchestrator, SubAgent")


def cmd_info(args: argparse.Namespace) -> None:
    """Show loopy info."""
    print(f"""
{'='*60}
 Loopy - 19 Essential AI Concepts in One Toolkit
{'='*60}

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

Docs: https://github.com/dream-pixels-forge/loopy
{'='*60}
""")


def main() -> None:
    """Main CLI entry point."""
    # Force UTF-8 output on Windows
    import io
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    parser = create_parser()
    args = parser.parse_args()
    
    commands = {
        "chat": cmd_chat,
        "guard": cmd_guard,
        "cache": cmd_cache,
        "trace": cmd_trace,
        "eval": cmd_eval,
        "agent": cmd_agent,
        "info": cmd_info,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
