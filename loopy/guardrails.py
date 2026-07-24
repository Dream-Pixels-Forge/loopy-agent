"""
Guardrails — The layer that protects the brand.

Input filtering (PII, jailbreak detection) and output filtering (safe responses).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FilterAction(str, Enum):
    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"
    PASS = "pass"


@dataclass
class FilterResult:
    """Result of a guardrail filter."""
    
    action: FilterAction
    original: str
    filtered: str
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardrailConfig:
    """Configuration for guardrails."""
    
    # PII patterns
    detect_ssn: bool = True
    detect_email: bool = True
    detect_phone: bool = True
    detect_credit_card: bool = True
    detect_ip_address: bool = True
    
    # Jailbreak patterns
    detect_jailbreak: bool = True
    jailbreak_sensitivity: float = 0.7
    
    # Custom patterns
    blocked_patterns: list[str] = field(default_factory=list)
    blocked_keywords: list[str] = field(default_factory=list)
    
    # Custom filters
    custom_filters: list[Callable[[str], Awaitable[FilterResult]]] = field(default_factory=list)


class InputFilter:
    """
    Filters user input for PII, jailbreak attempts, and harmful content.
    
    Example:
        filter = InputFilter()
        result = filter.check("My SSN is 123-45-6789")
        # result.action == FilterAction.REDACT
        # result.filtered == "My SSN is [SSN_REDACTED]"
    """

    # PII Patterns
    PATTERNS = {
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "phone": re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"),
        "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    }

    # Jailbreak patterns (simplified - production would use ML)
    JAILBREAK_PATTERNS = [
        re.compile(r"ignore (?:all |any )?(?:previous |prior |your )?instructions", re.I),
        re.compile(r"you are now (?:a |an )?(?: DAN |jailbroken |unrestricted)", re.I),
        re.compile(r"(?:pretend|act) (?:you (?:are|have) |as if )no (?:rules|restrictions)", re.I),
        re.compile(r"bypass (?:all |any )?(?:safety|content|filter)", re.I),
        re.compile(r"do anything now", re.I),
        re.compile(r"developer mode", re.I),
        re.compile(r"jailbreak", re.I),
        re.compile(r"ignore safety", re.I),
    ]

    def __init__(self, config: GuardrailConfig | None = None):
        self.config = config or GuardrailConfig()

    def check(self, text: str) -> FilterResult:
        """Check input text against all configured filters."""
        reasons = []
        filtered = text
        should_redact = False

        # Check PII
        pii_checks = {
            "ssn": self.config.detect_ssn,
            "email": self.config.detect_email,
            "phone": self.config.detect_phone,
            "credit_card": self.config.detect_credit_card,
            "ip_address": self.config.detect_ip_address,
        }

        for pii_type, enabled in pii_checks.items():
            if enabled and pii_type in self.PATTERNS and self.PATTERNS[pii_type].search(filtered):
                reasons.append(f"detected_{pii_type}")
                should_redact = True
                replacement = f"[{pii_type.upper()}_REDACTED]"
                filtered = self.PATTERNS[pii_type].sub(replacement, filtered)

        # Check jailbreak
        if self.config.detect_jailbreak:
            for pattern in self.JAILBREAK_PATTERNS:
                if pattern.search(text):
                    reasons.append("jailbreak_attempt")
                    return FilterResult(
                        action=FilterAction.BLOCK,
                        original=text,
                        filtered="",
                        reasons=reasons,
                    )

        # Check custom blocked patterns
        for pattern_str in self.config.blocked_patterns:
            if re.search(pattern_str, text, re.I):
                reasons.append(f"blocked_pattern:{pattern_str}")
                return FilterResult(
                    action=FilterAction.BLOCK,
                    original=text,
                    filtered="",
                    reasons=reasons,
                )

        # Check blocked keywords
        text_lower = text.lower()
        for keyword in self.config.blocked_keywords:
            if keyword.lower() in text_lower:
                reasons.append(f"blocked_keyword:{keyword}")
                return FilterResult(
                    action=FilterAction.BLOCK,
                    original=text,
                    filtered="",
                    reasons=reasons,
                )

        if should_redact:
            return FilterResult(
                action=FilterAction.REDACT,
                original=text,
                filtered=filtered,
                reasons=reasons,
            )

        return FilterResult(
            action=FilterAction.PASS,
            original=text,
            filtered=text,
            reasons=[],
        )


class OutputFilter:
    """
    Filters model output for harmful content, data leaks, etc.
    
    Example:
        filter = OutputFilter()
        result = filter.check("The user's email is john@example.com")
        # result.action == FilterAction.REDACT
    """

    def __init__(self, config: GuardrailConfig | None = None):
        self.config = config or GuardrailConfig()
        self._input_filter = InputFilter(config)

    def check(self, text: str) -> FilterResult:
        """Check output text."""
        # Reuse input filter for PII detection in outputs
        return self._input_filter.check(text)


class GuardrailPipeline:
    """
    Full guardrail pipeline with input and output filters.
    
    Example:
        pipeline = GuardrailPipeline()
        
        # Check user input
        input_result = pipeline.filter_input("Tell me about 123-45-6789")
        
        # ... process with LLM ...
        
        # Check model output
        output_result = pipeline.filter_output("Here's the info...")
    """

    def __init__(self, config: GuardrailConfig | None = None):
        self.config = config or GuardrailConfig()
        self.input_filter = InputFilter(self.config)
        self.output_filter = OutputFilter(self.config)
        self._history: list[dict[str, Any]] = []

    def filter_input(self, text: str) -> FilterResult:
        """Filter user input."""
        result = self.input_filter.check(text)
        self._history.append({
            "direction": "input",
            "result": result,
        })
        return result

    def filter_output(self, text: str) -> FilterResult:
        """Filter model output."""
        result = self.output_filter.check(text)
        self._history.append({
            "direction": "output",
            "result": result,
        })
        return result

    def get_history(self) -> list[dict[str, Any]]:
        """Return filter history."""
        return self._history.copy()
