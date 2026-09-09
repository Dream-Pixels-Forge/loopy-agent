"""Extended tests for loopy.evals — serialization, judge gate, edge cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loopy.evals import (
    EvalCase,
    EvalGate,
    EvalGateResult,
    EvalGateType,
    EvalReport,
    EvalResult,
    EvalSuite,
    Evaluator,
    JudgeConfig,
    Verdict,
)

# ── EvalReport serialization ─────────────────────────────────


class TestEvalReportSerialization:
    def test_to_dict_serializes_results(self):
        case = EvalCase(name="c1", input_text="hi", expected_output="hello")
        result = EvalResult(
            case=case,
            actual_output="hello",
            verdict=Verdict.PASS,
            score=1.0,
            reasoning="exact match",
        )
        report = EvalReport(suite_name="suite1", results=[result])
        d = report.to_dict()
        assert d["suite_name"] == "suite1"
        assert len(d["results"]) == 1
        assert d["results"][0]["case"]["name"] == "c1"
        assert d["results"][0]["verdict"] == "pass"

    def test_from_dict_restores_report(self):
        data = {
            "suite_name": "s",
            "results": [
                {
                    "case": {
                        "name": "c1",
                        "input_text": "x",
                        "expected_output": "y",
                        "criteria": [],
                        "tags": [],
                        "threshold": 0.7,
                    },
                    "actual_output": "y",
                    "verdict": "pass",
                    "score": 1.0,
                    "reasoning": "",
                    "criteria_scores": {},
                    "metadata": {},
                }
            ],
        }
        report = EvalReport.from_dict(data)
        assert report.suite_name == "s"
        assert len(report.results) == 1
        assert report.results[0].verdict == Verdict.PASS

    def test_empty_report_to_dict(self):
        report = EvalReport(suite_name="empty")
        d = report.to_dict()
        assert d["results"] == []

    def test_save_and_load_json(self, tmp_path: Path):
        case = EvalCase(name="add", input_text="2+2", expected_output="4")
        result = EvalResult(
            case=case, actual_output="4", verdict=Verdict.PASS, score=1.0
        )
        report = EvalReport(suite_name="math", results=[result])
        path = tmp_path / "report.json"
        report.save(str(path))
        assert path.exists()
        loaded = EvalReport.from_json(path.read_text(encoding="utf-8"))
        assert loaded.suite_name == "math"
        assert loaded.total == 1
        assert loaded.passed == 1

    def test_summary_shape(self):
        report = EvalReport(
            suite_name="s",
            results=[
                EvalResult(
                    case=EvalCase(name="a", input_text="x", expected_output="x"),
                    actual_output="x",
                    verdict=Verdict.PASS,
                    score=1.0,
                ),
                EvalResult(
                    case=EvalCase(name="b", input_text="x", expected_output="y"),
                    actual_output="z",
                    verdict=Verdict.FAIL,
                    score=0.0,
                ),
            ],
        )
        s = report.summary()
        assert s["suite"] == "s"
        assert s["total"] == 2
        assert s["passed"] == 1
        assert s["failed"] == 1
        assert s["pass_rate"] == "50.0%"
        assert s["average_score"] == "0.50"


# ── Evaluator · no judge_fn (simple path) ───────────────────


class TestEvaluatorSimple:
    @pytest.mark.asyncio
    async def test_simple_exact_match_passes(self):
        evaluator = Evaluator()

        async def model_fn(_input: str) -> str:
            return "hello"

        case = EvalCase(name="greeting", input_text="hello", expected_output="hello")
        result = await evaluator._eval_case(case, model_fn)
        assert result.verdict == Verdict.PASS
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_simple_partial_match(self):
        evaluator = Evaluator()

        async def model_fn(_input: str) -> str:
            return "hello world extra"

        case = EvalCase(name="greeting", input_text="hello", expected_output="hello world")
        result = await evaluator._eval_case(case, model_fn)
        assert result.verdict == Verdict.PARTIAL

    @pytest.mark.asyncio
    async def test_simple_mismatch_fails(self):
        evaluator = Evaluator()

        async def model_fn(_input: str) -> str:
            return "nothing"

        case = EvalCase(name="greeting", input_text="hello", expected_output="goodbye")
        result = await evaluator._eval_case(case, model_fn)
        assert result.verdict == Verdict.FAIL
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_simple_no_expected_output_nonempty_passes(self):
        evaluator = Evaluator()

        async def model_fn(_input: str) -> str:
            return "some output"

        case = EvalCase(name="open", input_text="anything", expected_output=None)
        result = await evaluator._eval_case(case, model_fn)
        assert result.verdict == Verdict.PASS
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_simple_no_expected_output_empty_fails(self):
        evaluator = Evaluator()

        async def model_fn(_input: str) -> str:
            return ""

        case = EvalCase(name="open", input_text="anything", expected_output=None)
        result = await evaluator._eval_case(case, model_fn)
        assert result.verdict == Verdict.FAIL
        assert result.score == 0.0


# ── Evaluator · with judge_fn ───────────────────────────────


class TestEvaluatorWithJudge:
    @pytest.mark.asyncio
    async def test_judge_valid_json(self):
        async def fake_judge(prompt):
            return json.dumps({"overall_score": 0.9, "verdict": "pass", "reasoning": "good"})

        async def model_fn(_input):
            return "output"

        evaluator = Evaluator(judge_fn=fake_judge)
        case = EvalCase(name="j1", input_text="x", expected_output="y")
        result = await evaluator._eval_case(case, model_fn)
        assert result.verdict == Verdict.PASS
        assert result.score == 0.9
        assert result.reasoning == "good"

    @pytest.mark.asyncio
    async def test_judge_invalid_json_falls_back(self):
        async def bad_judge(prompt):
            return "not valid json at all"

        async def model_fn(_input):
            return "hello"

        evaluator = Evaluator(judge_fn=bad_judge)
        case = EvalCase(name="j1", input_text="hello", expected_output="hello")
        result = await evaluator._eval_case(case, model_fn)
        # Should fall back to simple eval after JSONDecodeError
        assert result.verdict == Verdict.PASS

    @pytest.mark.asyncio
    async def test_judge_criteria_passed_to_prompt(self):
        captured: list[str] = []

        async def capturing_judge(prompt):
            captured.append(prompt)
            return json.dumps({"overall_score": 0.8, "verdict": "pass"})

        async def model_fn(_input):
            return "hi"

        evaluator = Evaluator(judge_fn=capturing_judge)
        case = EvalCase(
            name="c", input_text="hi", expected_output="hi", criteria=["concise", "correct"]
        )
        await evaluator._eval_case(case, model_fn)
        assert len(captured) == 1
        assert "concise" in captured[0]
        assert "correct" in captured[0]

    @pytest.mark.asyncio
    async def test_run_without_model_fn_raises(self):
        evaluator = Evaluator()
        suite = EvalSuite(name="s", cases=[EvalCase(name="c", input_text="x")])
        with pytest.raises(ValueError, match="No model function"):
            await evaluator.run(suite)


# ── EvalGate ────────────────────────────────────────────────


class TestEvalGate:
    @pytest.mark.asyncio
    async def test_manual_gate_always_passes(self):
        gate = EvalGate(
            gate_type=EvalGateType.MANUAL,
            config=JudgeConfig(threshold=0.8),
        )
        result = await gate.evaluate("input", "output")
        assert result.passed is True
        assert result.score == 1.0
        assert "Manual gate" in result.feedback

    @pytest.mark.asyncio
    async def test_judge_gate_with_simple_fallback(self):
        gate = EvalGate(
            gate_type=EvalGateType.JUDGE,
            config=JudgeConfig(threshold=0.5, criteria=["quality"]),
        )
        result = await gate.evaluate("input text", "some output")
        assert isinstance(result, EvalGateResult)
        assert result.gate_type == EvalGateType.JUDGE

    @pytest.mark.asyncio
    async def test_judge_gate_with_custom_judge_fn(self):
        async def judge_fn(prompt):
            return json.dumps({"score": 0.9, "feedback": "great"})

        gate = EvalGate(
            gate_type=EvalGateType.JUDGE,
            config=JudgeConfig(threshold=0.5, criteria=["quality"]),
            judge_fn=judge_fn,
        )
        result = await gate.evaluate("inp", "out")
        assert result.passed is True
        assert result.score == 0.9
        assert result.feedback == "great"

    @pytest.mark.asyncio
    async def test_judge_gate_parse_failure_falls_back(self):
        async def bad_judge(prompt):
            return "broken"

        gate = EvalGate(
            gate_type=EvalGateType.JUDGE,
            config=JudgeConfig(threshold=0.5),
            judge_fn=bad_judge,
        )
        result = await gate.evaluate("inp", "out")
        assert result.gate_type == EvalGateType.JUDGE


# ── EvalSuite helpers ───────────────────────────────────────


class TestEvalSuiteHelpers:
    def test_construct_with_cases(self):
        cases = [
            EvalCase(name="add", input_text="1+1", expected_output="2"),
            EvalCase(name="mul", input_text="2*3", expected_output="6"),
        ]
        suite = EvalSuite(name="math", cases=cases)
        assert len(suite.cases) == 2
        assert suite.cases[0].name == "add"

    def test_empty_suite(self):
        suite = EvalSuite(name="empty")
        assert len(suite.cases) == 0
        assert suite.cases == []
