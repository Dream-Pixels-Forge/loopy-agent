"""
Example 3: Evaluator-Optimizer Pattern

Demonstrates using EvalGate for LLM-as-judge evaluation.
"""

import asyncio

from loopy import EvalGate, EvalGateType, JudgeConfig


# Example: Custom judge function (would call LLM in production)
async def custom_judge(prompt: str) -> str:
    """Simulate an LLM judge evaluating output quality."""
    # In production, this would call OpenAI/Anthropic
    # Here we simulate a response
    if "Python" in prompt:
        return '{"score": 0.9, "pass": true, "feedback": "Excellent explanation"}'
    return '{"score": 0.6, "pass": false, "feedback": "Could be more detailed"}'


async def main():
    # Create evaluation gate with custom judge
    gate = EvalGate(
        gate_type=EvalGateType.JUDGE,
        config=JudgeConfig(
            criteria=["correct", "concise", "helpful"],
            threshold=0.7,
        ),
        judge_fn=custom_judge,
    )
    
    # Test case 1: Good output
    result1 = await gate.evaluate(
        input_text="What is Python?",
        output="Python is a high-level programming language known for its simplicity and readability.",
    )
    
    print("Test 1: Good output")
    print(f"  Passed: {result1.passed}")
    print(f"  Score: {result1.score}")
    print(f"  Feedback: {result1.feedback}")
    print()
    
    # Test case 2: Bad output
    result2 = await gate.evaluate(
        input_text="What is JavaScript?",
        output="JS is a language.",
    )
    
    print("Test 2: Bad output")
    print(f"  Passed: {result2.passed}")
    print(f"  Score: {result2.score}")
    print(f"  Feedback: {result2.feedback}")
    print()
    
    # Example: Command gate (exit code)
    cmd_gate = EvalGate(gate_type=EvalGateType.COMMAND)
    cmd_result = await cmd_gate.evaluate("test", "0")  # exit code 0 = success
    print(f"Command gate (exit 0): passed={cmd_result.passed}")
    
    cmd_result2 = await cmd_gate.evaluate("test", "1")  # exit code 1 = failure
    print(f"Command gate (exit 1): passed={cmd_result2.passed}")
    print()
    
    # Example: Artifact gate (file existence)
    import os
    import tempfile
    
    artifact_gate = EvalGate(gate_type=EvalGateType.ARTIFACT)
    
    # Create temp file
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
    
    try:
        artifact_result = await artifact_gate.evaluate("test", temp_path)
        print(f"Artifact gate (exists): passed={artifact_result.passed}")
    finally:
        os.unlink(temp_path)
    
    artifact_result2 = await artifact_gate.evaluate("test", "/nonexistent/file.txt")
    print(f"Artifact gate (missing): passed={artifact_result2.passed}")


if __name__ == "__main__":
    asyncio.run(main())
