"""
Structured error types for loopy-agent.

Provides ``AgentError`` and subclasses with ``subtype``,
``terminal_reason``, ``session_id``, and ``errors`` fields
so callers can programmatically classify and recover from
agent failures.

All public error classes carry a docs URL in their message
per the v1.1 error-audit contract (see
https://loopy.dev/docs/contributing#error-audit).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("loopy.errors")


class AgentError(Exception):
    """Base error for all loopy agent errors.

    Extends :exc:`Exception` with structured metadata so callers
    can classify failures programmatically without parsing messages.

    Args:
        message: Human-readable error description.
        subtype: Machine-readable error category (e.g. ``"tool_failure"``).
        terminal_reason: Why this error is terminal (cannot be retried).
        session_id: The session this error occurred in, if any.
        errors: List of nested error dicts for compound failures.

    Example:
        >>> raise ResultError("tool crashed", subtype="crash", terminal_reason="invalid_code")
    """

    def __init__(
        self,
        message: str,
        *,
        subtype: str | None = None,
        terminal_reason: str | None = None,
        session_id: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.subtype = subtype
        self.terminal_reason = terminal_reason
        self.session_id = session_id
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/tracing/JSON export.

        Returns:
            Dict with keys: type, message, subtype, terminal_reason,
            session_id, errors.
        """
        return {
            "type": self.__class__.__name__,
            "message": str(self),
            "subtype": self.subtype,
            "terminal_reason": self.terminal_reason,
            "session_id": self.session_id,
            "errors": self.errors,
        }

    def __repr__(self) -> str:
        parts = [f"{self.__class__.__name__}({str(self)!r})"]
        if self.subtype:
            parts.append(f"subtype={self.subtype!r}")
        if self.terminal_reason:
            parts.append(f"terminal_reason={self.terminal_reason!r}")
        if self.session_id:
            parts.append(f"session_id={self.session_id!r}")
        return "<" + " ".join(parts) + ">"


class ResultError(AgentError):
    """Tool execution error with structured details.

    Use for failures that occur during tool execution — invalid
    arguments, runtime exceptions, or timeout.

    Args:
        message: Human-readable description.
        tool_name: Name of the tool that failed, if known.
        subtype: Error category (e.g. ``"validation"``、``"timeout"``).
        terminal_reason: Why this cannot be retried.
        session_id: Session ID if available.
        original_exception: The caught exception, if any.
    """

    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        subtype: str | None = None,
        terminal_reason: str | None = None,
        session_id: str | None = None,
        original_exception: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            subtype=subtype,
            terminal_reason=terminal_reason,
            session_id=session_id,
        )
        self.tool_name = tool_name
        self.original_exception = original_exception
        if original_exception is not None:
            self.errors.append(
                {
                    "source": "original_exception",
                    "type": type(original_exception).__name__,
                    "message": str(original_exception),
                }
            )


class SessionError(AgentError):
    """Session management error.

    Raised when session operations fail — resume, fork, or
    state persistence.
    """


class ProcessError(AgentError):
    """Process/subprocess error with exit code.

    Raised when a subprocess terminates unexpectedly.

    Args:
        message: Human-readable description.
        exit_code: The process exit code.
        stdout: Captured stdout, if available.
        stderr: Captured stderr, if available.
    """

    def __init__(
        self,
        message: str,
        exit_code: int,
        *,
        stdout: str | None = None,
        stderr: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.exit_code = exit_code
        if stdout is not None:
            self.errors.append({"source": "stdout", "content": stdout})
        if stderr is not None:
            self.errors.append({"source": "stderr", "content": stderr})


class ToolNotFoundError(AgentError):
    """Raised when a requested tool does not exist."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool not found: {tool_name} (see https://loopy.dev/docs/tools#errors)")
        self.tool_name = tool_name
        self.subtype = "not_found"


class PermissionDeniedError(AgentError):
    """Raised when a tool call is denied by permission gates."""

    def __init__(self, tool_name: str, reason: str) -> None:
        super().__init__(
            f"Permission denied for tool '{tool_name}': {reason} "
            f"(see https://loopy.dev/docs/safety#permissions)"
        )
        self.tool_name = tool_name
        self.subtype = "permission_denied"
        self.terminal_reason = reason


class HookError(AgentError):
    """Raised when a hook fails during execution."""

    def __init__(self, hook_name: str, error: Exception) -> None:
        super().__init__(
            f"Hook '{hook_name}' raised {type(error).__name__}: {error} "
            f"(see https://loopy.dev/docs/hooks#errors)"
        )
        self.hook_name = hook_name
        self.subtype = "hook_failure"
        self.errors.append({"source": "hook", "name": hook_name, "exception": str(error)})


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def result_error(
    tool_name: str,
    exc: Exception,
    *,
    terminal: bool = False,
    session_id: str | None = None,
) -> ResultError:
    """Create a :class:`ResultError` from a caught exception.

    Convenience factory for the common pattern of catching an
    exception during tool execution and re-raising as a
    structured error.

    Args:
        tool_name: Name of the tool that raised the exception.
        exc: The caught exception.
        terminal: If True, mark as non-retryable.
        session_id: Optional session identifier.

    Returns:
        A new :class:`ResultError`.
    """
    return ResultError(
        f"Tool '{tool_name}' failed: {exc}",
        tool_name=tool_name,
        subtype=type(exc).__name__.lower(),
        terminal_reason="terminal" if terminal else None,
        session_id=session_id,
        original_exception=exc,
    )


def process_error(
    command: str,
    exit_code: int,
    *,
    stderr: str | None = None,
    session_id: str | None = None,
) -> ProcessError:
    """Create a :class:`ProcessError` from a subprocess result.

    Args:
        command: The command that was executed.
        exit_code: The process exit code.
        stderr: Captured stderr output.
        session_id: Optional session identifier.

    Returns:
        A new :class:`ProcessError`.
    """
    return ProcessError(
        f"Process '{command}' exited with code {exit_code} "
        f"(see https://loopy.dev/docs/tools#errors)",
        exit_code,
        stderr=stderr,
        session_id=session_id,
    )
