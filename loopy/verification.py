"""
Verification — Maker/Checker Pattern.

Separate implementer and verifier agents for reliable loops.
Inspired by loop-engineering's Maker/Checker split.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("loopy.verification")


class VerificationStatus(str, Enum):
    """Status of verification."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class VerifyResult:
    """Result of verification gate."""

    status: VerificationStatus
    feedback: str = ""
    score: float = 0.0
    output: Any = None
    duration_ms: float = 0

    @property
    def passed(self) -> bool:
        return self.status == VerificationStatus.PASSED


class VerificationGate:
    """
    Maker/Checker split for reliable loops.

    Runs implementer, then verifier (separate model/instructions).
    The agent that wrote the code is a terrible judge of its own work.

    Example:
        gate = VerificationGate(
            implementer=coder_fn,
            verifier=tester_fn,
            test_fn=run_tests,
        )
        result = await gate.run("Fix the bug")
        if result.passed:
            print("Verified!")
    """

    def __init__(
        self,
        implementer: Callable[[str], Awaitable[Any]],
        verifier: Callable[[Any], Awaitable[VerifyResult]],
        test_fn: Callable[[Any], Awaitable[bool]] | None = None,
        threshold: float = 0.5,
    ):
        self.implementer = implementer
        self.verifier = verifier
        self.test_fn = test_fn
        self.threshold = threshold

    async def run(self, task: str) -> VerifyResult:
        """
        Run implementer, then verifier.

        Args:
            task: The task to implement and verify

        Returns:
            VerifyResult with pass/fail and feedback
        """
        start_time = time.time()

        try:
            # 1. Implement
            logger.debug("Implementing: %s...", task[:50])
            output = await self.implementer(task)

            # 2. Run tests (if provided)
            if self.test_fn:
                logger.debug("Running tests...")
                tests_pass = await self.test_fn(output)
                if not tests_pass:
                    return VerifyResult(
                        status=VerificationStatus.FAILED,
                        feedback="Tests failed",
                        score=0.0,
                        output=output,
                        duration_ms=(time.time() - start_time) * 1000,
                    )

            # 3. Verify (different model/instructions)
            logger.debug("Verifying implementation...")
            result = await self.verifier(output)

            # Check threshold
            if result.passed and result.score < self.threshold:
                return VerifyResult(
                    status=VerificationStatus.FAILED,
                    feedback=f"Score {result.score} below threshold {self.threshold}",
                    score=result.score,
                    output=output,
                    duration_ms=(time.time() - start_time) * 1000,
                )

            result.output = output
            result.duration_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            logger.error("Verification error: %s", e)
            return VerifyResult(
                status=VerificationStatus.ERROR,
                feedback=f"Error: {e}",
                score=0.0,
                duration_ms=(time.time() - start_time) * 1000,
            )
