"""
Evals — What you can't measure, you can't ship.

Judge-based model evaluation framework for testing LLM quality.
Includes EvalGate for evaluator-optimizer pattern (2026 agentic workflow).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("loopy.evals")


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


@dataclass
class EvalCase:
    """A single evaluation test case."""
    
    name: str
    input_text: str
    expected_output: str | None = None
    criteria: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    threshold: float = 0.7


@dataclass
class EvalResult:
    """Result of evaluating a single case."""
    
    case: EvalCase
    actual_output: str
    verdict: Verdict
    score: float  # 0.0 to 1.0
    reasoning: str = ""
    criteria_scores: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalSuite:
    """Collection of evaluation cases."""
    
    name: str
    cases: list[EvalCase] = field(default_factory=list)
    description: str = ""


@dataclass
class EvalReport:
    """Full evaluation report."""
    
    suite_name: str
    results: list[EvalResult] = field(default_factory=list)
    
    @property
    def total(self) -> int:
        return len(self.results)
    
    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.PASS)
    
    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.FAIL)
    
    @property
    def partial(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.PARTIAL)
    
    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0
    
    @property
    def average_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)
    
    def summary(self) -> dict[str, Any]:
        """Return summary dict."""
        return {
            "suite": self.suite_name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "partial": self.partial,
            "pass_rate": f"{self.pass_rate:.1%}",
            "average_score": f"{self.average_score:.2f}",
        }


class EvalGateType(str, Enum):
    """Types of evaluation gates."""
    JUDGE = "judge"          # LLM-as-judge (2026 evaluator-optimizer pattern)
    MANUAL = "manual"        # Human approval stub


@dataclass
class JudgeConfig:
    """Configuration for LLM-as-judge evaluation."""
    evaluator_model: str = "gpt-4"
    criteria: list[str] = field(default_factory=list)
    threshold: float = 0.7  # pass threshold
    prompt_template: str = """Rate this output on the given criteria.

Input: {input}
Output: {output}
Criteria: {criteria}

Respond with JSON:
{{
    "score": 0.0-1.0,
    "pass": true/false,
    "feedback": "explanation"
}}"""


@dataclass
class EvalGateResult:
    """Result of an evaluation gate check."""
    gate_type: EvalGateType
    passed: bool
    score: float = 0.0
    feedback: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class EvalGate:
    """
    Evaluation gate for the evaluator-optimizer pattern.
    
    Uses LLM-as-judge to evaluate outputs against criteria.
    Part of the 2026 agentic workflow evaluator-optimizer pattern.
    
    Example:
        gate = EvalGate(
            gate_type=EvalGateType.JUDGE,
            config=JudgeConfig(
                criteria=["correct", "concise", "helpful"],
                threshold=0.8,
            ),
            judge_fn=my_llm_judge,
        )
        
        result = await gate.evaluate(
            input_text="What is Python?",
            output="Python is a programming language...",
        )
        
        if result.passed:
            print("Output passed evaluation!")
    """
    
    def __init__(
        self,
        gate_type: EvalGateType,
        config: JudgeConfig | None = None,
        judge_fn: Callable[[str], Awaitable[str]] | None = None,
    ):
        self.gate_type = gate_type
        self.config = config or JudgeConfig()
        self.judge_fn = judge_fn
    
    async def evaluate(
        self,
        input_text: str,
        output: str,
        criteria: list[str] | None = None,
    ) -> EvalGateResult:
        """
        Evaluate an output against criteria.
        
        Args:
            input_text: The original input/prompt
            output: The output to evaluate
            criteria: Optional override for criteria
        
        Returns:
            EvalGateResult with pass/fail and score
        """
        if self.gate_type == EvalGateType.JUDGE:
            return await self._judge_evaluate(input_text, output, criteria)

        # Manual gates always pass (human reviews externally)
        return EvalGateResult(
            gate_type=self.gate_type,
            passed=True,
            score=1.0,
            feedback="Manual gate - pending human review",
        )
    
    async def _judge_evaluate(
        self,
        input_text: str,
        output: str,
        criteria: list[str] | None = None,
    ) -> EvalGateResult:
        """Use LLM-as-judge to evaluate output."""
        if not self.judge_fn:
            # Fallback to simple evaluation
            return self._simple_judge_evaluate(input_text, output, criteria)
        
        criteria_list = criteria or self.config.criteria
        criteria_str = ", ".join(criteria_list) if criteria_list else "general quality"
        
        prompt = self.config.prompt_template.format(
            input=input_text,
            output=output,
            criteria=criteria_str,
        )
        
        try:
            judge_response = await self.judge_fn(prompt)
            data = json.loads(judge_response)
            
            score = float(data.get("score", 0.0))
            passed = score >= self.config.threshold
            
            return EvalGateResult(
                gate_type=EvalGateType.JUDGE,
                passed=passed,
                score=score,
                feedback=data.get("feedback", ""),
                metadata={"criteria": criteria_list},
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Judge evaluation failed, using fallback: %s", e)
            return self._simple_judge_evaluate(input_text, output, criteria)
    
    def _simple_judge_evaluate(
        self,
        input_text: str,
        output: str,
        criteria: list[str] | None = None,
    ) -> EvalGateResult:
        """Simple evaluation when no judge function is available."""
        # Basic heuristics
        score = 0.0
        feedback = []
        
        # Check output is not empty
        if output.strip():
            score += 0.3
            feedback.append("Output is non-empty")
        
        # Check output length (prefer concise)
        word_count = len(output.split())
        if 10 <= word_count <= 200:
            score += 0.3
            feedback.append(f"Good length ({word_count} words)")
        elif word_count > 200:
            score += 0.1
            feedback.append(f"Too long ({word_count} words)")
        
        # Check for basic relevance (input words in output)
        input_words = set(input_text.lower().split())
        output_words = set(output.lower().split())
        overlap = len(input_words & output_words) / max(len(input_words), 1)
        score += 0.4 * overlap
        feedback.append(f"Relevance overlap: {overlap:.1%}")
        
        passed = score >= self.config.threshold
        
        return EvalGateResult(
            gate_type=EvalGateType.JUDGE,
            passed=passed,
            score=min(score, 1.0),
            feedback="; ".join(feedback),
            metadata={"method": "simple_heuristic"},
        )


class Evaluator:
    """
    Judge-based evaluation framework.
    
    Uses an LLM as a judge to evaluate model outputs against criteria.
    
    Example:
        evaluator = Evaluator(judge_fn=my_llm_judge)
        
        suite = EvalSuite(
            name="math_basic",
            cases=[
                EvalCase(
                    name="addition",
                    input_text="What is 2+2?",
                    expected_output="4",
                    criteria=["correct", "concise"],
                ),
            ],
        )
        
        report = evaluator.run(suite, model_fn=my_model)
        print(report.summary())
    """

    JUDGE_PROMPT = """You are an evaluation judge. Your task is to score a model's output.

Input: {input}
Expected Output: {expected}
Actual Output: {actual}
Criteria: {criteria}

Score each criterion from 0.0 to 1.0, then provide an overall score.
Respond in JSON:
{{
    "criteria_scores": {{"criterion": score}},
    "overall_score": 0.0-1.0,
    "reasoning": "explanation",
    "verdict": "pass" | "fail" | "partial"
}}"""

    def __init__(
        self,
        judge_fn: Callable[[str], Awaitable[str]] | None = None,
        model_fn: Callable[[str], Awaitable[str]] | None = None,
    ):
        self.judge_fn = judge_fn
        self.model_fn = model_fn

    async def run(
        self,
        suite: EvalSuite,
        model_fn: Callable[[str], Awaitable[str]] | None = None,
    ) -> EvalReport:
        """
        Run evaluation suite.
        
        Args:
            suite: The evaluation suite to run
            model_fn: Function to get model output (or use instance default)
        
        Returns:
            EvalReport with all results
        """
        fn = model_fn or self.model_fn
        if not fn:
            raise ValueError("No model function provided")

        report = EvalReport(suite_name=suite.name)

        for case in suite.cases:
            result = await self._eval_case(case, fn)
            report.results.append(result)

        return report

    async def _eval_case(
        self,
        case: EvalCase,
        model_fn: Callable[[str], Awaitable[str]],
    ) -> EvalResult:
        """Evaluate a single case."""
        # Get model output
        actual_output = await model_fn(case.input_text)

        # If no judge function, use simple string matching
        if not self.judge_fn:
            return self._simple_eval(case, actual_output)

        # Use LLM judge
        criteria_str = ", ".join(case.criteria) if case.criteria else "general quality"
        
        prompt = self.JUDGE_PROMPT.format(
            input=case.input_text,
            expected=case.expected_output or "N/A",
            actual=actual_output,
            criteria=criteria_str,
        )

        judge_response = await self.judge_fn(prompt)
        
        try:
            # Parse judge response
            data = json.loads(judge_response)
            score = float(data.get("overall_score", 0.0))
            verdict = Verdict(data.get("verdict", "fail"))
            
            return EvalResult(
                case=case,
                actual_output=actual_output,
                verdict=verdict,
                score=score,
                reasoning=data.get("reasoning", ""),
                criteria_scores=data.get("criteria_scores", {}),
            )
        except (json.JSONDecodeError, ValueError):
            # Fallback to simple eval
            return self._simple_eval(case, actual_output)

    def _simple_eval(self, case: EvalCase, actual_output: str) -> EvalResult:
        """Simple string-based evaluation when no judge is available."""
        if case.expected_output:
            # Exact match
            if actual_output.strip() == case.expected_output.strip():
                score = 1.0
                verdict = Verdict.PASS
            # Partial match (contains expected)
            elif case.expected_output.lower() in actual_output.lower():
                score = 0.7
                verdict = Verdict.PARTIAL
            else:
                score = 0.0
                verdict = Verdict.FAIL
        else:
            # No expected output, just check it's not empty
            score = 1.0 if actual_output.strip() else 0.0
            verdict = Verdict.PASS if actual_output.strip() else Verdict.FAIL

        return EvalResult(
            case=case,
            actual_output=actual_output,
            verdict=verdict,
            score=score,
            reasoning="Simple string matching (no judge function)",
        )
