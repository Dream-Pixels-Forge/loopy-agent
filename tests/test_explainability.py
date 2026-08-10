"""Tests for loopy.explainability — Decision audit trail."""

import os
import tempfile

from loopy.explainability import DecisionStep, DecisionTrace, DecisionTracker, DecisionType


class TestDecisionType:
    def test_types(self):
        assert DecisionType.PLAN.value == "plan"
        assert DecisionType.ACTION.value == "action"
        assert DecisionType.TOOL_USE.value == "tool_use"


class TestDecisionStep:
    def test_step_creation(self):
        step = DecisionStep(
            type=DecisionType.PLAN,
            reasoning="Will use search tool",
            input_summary="query",
            output_summary="search results",
        )
        assert step.type == DecisionType.PLAN
        assert step.confidence == 1.0

    def test_step_to_dict(self):
        step = DecisionStep(
            type=DecisionType.ACTION,
            reasoning="Execute code",
            input_summary="",
            output_summary="",
            confidence=0.9,
        )
        d = step.to_dict()
        assert d["type"] == "action"
        assert d["confidence"] == 0.9


class TestDecisionTrace:
    def test_trace_creation(self):
        trace = DecisionTrace(task="Summarize doc")
        assert trace.task == "Summarize doc"
        assert len(trace.steps) == 0

    def test_trace_add_step(self):
        trace = DecisionTrace(task="Test")
        step = DecisionStep(
            type=DecisionType.PLAN,
            reasoning="Step 1",
            input_summary="",
            output_summary="",
        )
        trace.add_step(step)
        assert len(trace.steps) == 1

    def test_trace_summary(self):
        trace = DecisionTrace(task="Test task")
        step = DecisionStep(
            type=DecisionType.PLAN,
            reasoning="Do something",
            input_summary="",
            output_summary="",
        )
        trace.add_step(step)
        trace.final_output = "Result"
        summary = trace.summary
        assert "Test task" in summary
        assert "Do something" in summary


class TestDecisionTracker:
    def test_tracker_creation(self):
        tracker = DecisionTracker()
        assert len(tracker.traces) == 0

    def test_tracker_start(self):
        tracker = DecisionTracker()
        trace = tracker.start("My task")
        assert trace.task == "My task"
        assert len(tracker.traces) == 1

    def test_tracker_add_step(self):
        tracker = DecisionTracker()
        trace = tracker.start("Task")
        step = tracker.add_step(
            trace,
            DecisionType.PLAN,
            "Reasoning here",
            confidence=0.8,
        )
        assert step.reasoning == "Reasoning here"
        assert step.confidence == 0.8

    def test_tracker_finish(self):
        tracker = DecisionTracker()
        trace = tracker.start("Task")
        tracker.finish(trace, "Done!", success=True)
        assert trace.final_output == "Done!"
        assert trace.success is True

    def test_tracker_explain(self):
        tracker = DecisionTracker()
        trace = tracker.start("Explain task")
        tracker.add_step(trace, DecisionType.PLAN, "Plan step")
        tracker.add_step(trace, DecisionType.ACTION, "Action step")
        tracker.finish(trace, "Final result")

        explanation = tracker.explain(trace)
        assert "Plan step" in explanation
        assert "Action step" in explanation
        assert "Final result" in explanation

    def test_tracker_export(self):
        tracker = DecisionTracker()
        trace = tracker.start("Export task")
        tracker.finish(trace, "Result")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "trace.json")
            tracker.export(trace, path)
            assert os.path.exists(path)
