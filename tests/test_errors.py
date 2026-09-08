"""Tests for loopy.errors — structured error types."""

from __future__ import annotations

from loopy.errors import (
    AgentError,
    HookError,
    PermissionDeniedError,
    ProcessError,
    ResultError,
    ToolNotFoundError,
    process_error,
    result_error,
)


class TestAgentError:
    """Base AgentError behavior."""

    def test_is_exception_subclass(self):
        assert issubclass(AgentError, Exception)

    def test_default_fields_are_none(self):
        err = AgentError("something went wrong")
        assert err.subtype is None
        assert err.terminal_reason is None
        assert err.session_id is None
        assert err.errors == []

    def test_to_dict_basic(self):
        err = AgentError("boom")
        d = err.to_dict()
        assert d["type"] == "AgentError"
        assert d["message"] == "boom"
        assert d["subtype"] is None
        assert d["terminal_reason"] is None
        assert d["session_id"] is None
        assert d["errors"] == []

    def test_to_dict_with_fields(self):
        err = AgentError(
            "boom",
            subtype="crash",
            terminal_reason="invalid_input",
            session_id="sess-123",
            errors=[{"source": "hook", "name": "pre_use"}],
        )
        d = err.to_dict()
        assert d["subtype"] == "crash"
        assert d["terminal_reason"] == "invalid_input"
        assert d["session_id"] == "sess-123"
        assert len(d["errors"]) == 1
        assert d["errors"][0]["source"] == "hook"

    def test_repr_without_optional_fields(self):
        err = AgentError("boom")
        r = repr(err)
        assert "AgentError" in r
        assert "boom" in r
        assert "subtype=" not in r

    def test_repr_with_optional_fields(self):
        err = AgentError("boom", subtype="x", terminal_reason="y", session_id="z")
        r = repr(err)
        assert "subtype='x'" in r
        assert "terminal_reason='y'" in r
        assert "session_id='z'" in r


class TestResultError:
    """ResultError — tool execution failures."""

    def test_basic(self):
        err = ResultError("tool crashed", tool_name="bash", subtype="crash")
        assert err.tool_name == "bash"
        assert err.subtype == "crash"
        assert err.original_exception is None

    def test_with_original_exception(self):
        original = ValueError("bad args")
        err = ResultError(
            "tool failed",
            tool_name="grep",
            original_exception=original,
        )
        assert err.original_exception is original
        assert len(err.errors) == 1
        assert err.errors[0]["source"] == "original_exception"
        assert err.errors[0]["type"] == "ValueError"

    def test_to_dict_includes_tool_name(self):
        err = ResultError("fail", tool_name="edit")
        d = err.to_dict()
        assert d["type"] == "ResultError"
        assert d["message"] == "fail"


class TestProcessError:
    """ProcessError — subprocess failures."""

    def test_basic(self):
        err = ProcessError("cmd exited", 1)
        assert err.exit_code == 1

    def test_with_stderr(self):
        err = ProcessError("bad", 2, stderr="error output")
        assert err.exit_code == 2
        assert len(err.errors) == 1
        assert err.errors[0]["source"] == "stderr"
        assert err.errors[0]["content"] == "error output"

    def test_with_stdout(self):
        err = ProcessError("ok", 0, stdout="hello")
        assert len(err.errors) == 1
        assert err.errors[0]["source"] == "stdout"


class TestToolNotFoundError:
    def test_message_contains_tool_name(self):
        err = ToolNotFoundError("my_tool")
        assert "my_tool" in str(err)
        assert err.subtype == "not_found"

    def test_has_docs_url(self):
        err = ToolNotFoundError("x")
        assert "loopy.dev/docs/tools#errors" in str(err)


class TestPermissionDeniedError:
    def test_message_contains_details(self):
        err = PermissionDeniedError("bash", "not allowed")
        assert "bash" in str(err)
        assert "not allowed" in str(err)
        assert err.subtype == "permission_denied"
        assert err.terminal_reason == "not allowed"

    def test_has_docs_url(self):
        err = PermissionDeniedError("edit", "denylisted")
        assert "loopy.dev/docs/safety#permissions" in str(err)


class TestHookError:
    def test_message_contains_hook_name(self):
        err = HookError("pre_tool", ValueError("bad"))
        assert "pre_tool" in str(err)
        assert err.subtype == "hook_failure"

    def test_error_includes_exception(self):
        err = HookError("check", RuntimeError("oops"))
        assert len(err.errors) == 1
        assert err.errors[0]["source"] == "hook"
        assert err.errors[0]["name"] == "check"
        assert "oops" in err.errors[0]["exception"]


class TestFactories:
    """Convenience factory functions."""

    def test_result_error_factory(self):
        exc = TypeError("bad type")
        err = result_error("calc", exc, terminal=True, session_id="s1")
        assert isinstance(err, ResultError)
        assert err.tool_name == "calc"
        assert err.terminal_reason == "terminal"
        assert err.session_id == "s1"
        assert err.original_exception is exc

    def test_result_error_factory_non_terminal(self):
        exc = TimeoutError("timed out")
        err = result_error("fetch", exc)
        assert err.terminal_reason is None

    def test_process_error_factory(self):
        err = process_error("run.sh", 1, stderr="nope", session_id="s2")
        assert isinstance(err, ProcessError)
        assert err.exit_code == 1
        assert err.session_id == "s2"
        assert len(err.errors) == 1
        assert err.errors[0]["source"] == "stderr"
