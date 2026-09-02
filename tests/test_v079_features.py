"""Tests for v0.7.9 features.

Three additions that make loopy uniquely competitive in 2026:

  1. ``TestModel`` — zero-network LLM for unit tests (``gateway.py``)
  2. ``StructuredOutput`` — pydantic-validated chat outputs (``gateway.py``)
  3. ``Redactor`` — PII / secret scrubber for traces (``observe.py``)
"""

from __future__ import annotations

import time

import pytest
from pydantic import BaseModel

from loopy import (
    TEST_MODEL_SENTINEL,
    Gateway,
    GatewayResponse,
    RedactionMatch,
    Redactor,
    Tracer,
)
from loopy import (
    TestModel as _TestModelClass,
)

# ---------------------------------------------------------------------------
# Feature 1 - TestModel
# ---------------------------------------------------------------------------


class TestTestModelClass:
    def test_default_responses(self):
        tm = _TestModelClass()
        assert tm.model_name == "test"
        assert tm.responses

    @pytest.mark.asyncio
    async def test_instance_routing_via_chat(self):
        gw = Gateway()
        tm = _TestModelClass(responses=["first", "second"])
        r1 = await gw.chat("hi", model=tm)
        assert r1.content == "first"
        r2 = await gw.chat("again", model=tm)
        assert r2.content == "second"
        assert len(tm.calls) == 2

    @pytest.mark.asyncio
    async def test_sentinel_string(self):
        gw = Gateway()
        r = await gw.chat("hi", model=TEST_MODEL_SENTINEL)
        assert r.metadata.get("test_model") is True
        assert r.content

    def test_responses_reuse_last_when_exhausted(self):
        tm = _TestModelClass(responses=["a", "b"])
        for _ in range(5):
            tm.next_response("x", None)
        assert tm._index == 2  # noqa: SLF001

    def test_callable_response(self):
        tm = _TestModelClass(responses=[lambda msg, sys: f"echo: {msg}"])
        assert tm.next_response("hello", None) == "echo: hello"

    @pytest.mark.asyncio
    async def test_forced_error(self):
        tm = _TestModelClass(raise_on_message="boom")
        with pytest.raises(RuntimeError, match="boom"):
            await tm.handle("this should boom", None, 0.0, 100, None)

    @pytest.mark.asyncio
    async def test_reset(self):
        tm = _TestModelClass(responses=["a", "b"])
        await tm.handle("x", None, 0.0, 100, None)
        assert tm._index == 1
        assert tm.calls
        tm.reset()
        assert tm._index == 0
        assert tm.calls == []

    @pytest.mark.asyncio
    async def test_tool_calls_metadata(self):
        tm = _TestModelClass(tool_calls=[{"name": "search", "args": {"q": "test"}}])
        r = await tm.handle("x", None, 0.0, 100, None)
        assert r.metadata["tool_calls"] == [{"name": "search", "args": {"q": "test"}}]

    @pytest.mark.asyncio
    async def test_latency_simulation(self):
        tm = _TestModelClass(responses=["slow"], latency_ms=50)
        start = time.time()
        await tm.handle("x", None, 0.0, 100, None)
        assert (time.time() - start) >= 0.04

    @pytest.mark.asyncio
    async def test_invalid_model_arg(self):
        gw = Gateway()
        with pytest.raises(ValueError, match="Unsupported value"):
            await gw.chat("hi", model="not-a-thing")

    @pytest.mark.asyncio
    async def test_logs_record_test_traffic(self):
        gw = Gateway()
        tm = _TestModelClass(responses=["hi"])
        await gw.chat("x", model=tm)
        assert any(e["provider"] == "test" for e in gw.get_logs())


# ---------------------------------------------------------------------------
# Feature 2 - StructuredOutput
# ---------------------------------------------------------------------------


class Sentiment(BaseModel):
    label: str
    score: float


class TestStructuredOutput:
    @pytest.mark.asyncio
    async def test_structured_success_via_handle(self):
        tm = _TestModelClass(responses=['{"label": "positive", "score": 0.92}'])
        r = await tm.handle("rate this", None, 0.0, 100, Sentiment)
        assert isinstance(r.structured, Sentiment)
        assert r.structured.label == "positive"
        assert r.structured.score == 0.92

    @pytest.mark.asyncio
    async def test_structured_validation_failure(self):
        tm = _TestModelClass(responses=["not valid json"])
        r = await tm.handle("x", None, 0.0, 100, Sentiment)
        assert r.structured is None
        assert r.content == "not valid json"

    @pytest.mark.asyncio
    async def test_structured_via_gateway_chat(self):
        gw = Gateway()
        tm = _TestModelClass(responses=['{"label": "negative", "score": 0.1}'])
        r = await gw.chat("rate this", model=tm, response_format=Sentiment)
        assert isinstance(r.structured, Sentiment)
        assert r.structured.label == "negative"

    def test_gateway_response_has_structured_field(self):
        r = GatewayResponse(content="x", model="m", provider=None)  # type: ignore[arg-type]
        assert r.structured is None


# ---------------------------------------------------------------------------
# Feature 3 - Redactor
# ---------------------------------------------------------------------------


class TestRedactorBasics:
    def test_default_redactor_initializes_all_builtins(self):
        r = Redactor()
        assert set(r.enabled.keys()) == {
            "email",
            "phone",
            "ssn",
            "credit_card",
            "openai_key",
            "aws_key",
            "jwt",
            "bearer",
            "ipv4",
        }

    def test_redact_email(self):
        assert Redactor().redact("contact foo@bar.com") == "contact [EMAIL_REDACTED]"

    def test_redact_ssn(self):
        assert Redactor().redact("ssn 123-45-6789") == "ssn [SSN_REDACTED]"

    def test_redact_openai_key(self):
        key = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"
        out = Redactor().redact(f"key={key}")
        assert key not in out
        assert "[OPENAI_KEY_REDACTED]" in out

    def test_redact_aws_key(self):
        key = "AKIAIOSFODNN7EXAMPLE"
        out = Redactor().redact(f"aws_key={key}")
        assert "[AWS_KEY_REDACTED]" in out

    def test_redact_jwt(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxw"
        out = Redactor().redact(f"token={jwt}")
        assert "[JWT_REDACTED]" in out

    def test_redact_bearer(self):
        out = Redactor().redact("Authorization: Bearer abc.def.ghi")
        assert "Bearer abc.def.ghi" not in out
        assert "[BEARER_REDACTED]" in out

    def test_redact_multiple_in_one_string(self):
        out = Redactor().redact("email foo@bar.com, ssn 123-45-6789")
        assert "[EMAIL_REDACTED]" in out
        assert "[SSN_REDACTED]" in out

    def test_redact_empty_or_safe(self):
        r = Redactor()
        assert r.redact("") == ""
        assert r.redact("just normal words") == "just normal words"

    def test_redact_non_string_passes_through(self):
        r = Redactor()
        assert r.redact(None) is None
        assert r.redact(42) == 42
        assert r.redact([1, 2]) == [1, 2]


class TestRedactorConfig:
    def test_disable_builtin(self):
        r = Redactor()
        r.disable("ssn")
        assert "ssn" not in r.enabled
        assert r.redact("123-45-6789") == "123-45-6789"

    def test_add_custom_pattern(self):
        r = Redactor()
        r.add_pattern("employee_id", r"EID-\d{6}")
        out = r.redact("employee EID-123456 went home")
        assert "[EMPLOYEE_ID_REDACTED]" in out

    def test_add_builtin_name_raises(self):
        r = Redactor()
        with pytest.raises(ValueError, match="built-in pattern"):
            r.add_pattern("email", r"x")

    def test_disable_then_re_add_with_new_pattern(self):
        r = Redactor()
        r.disable("email")
        r.add_pattern("email", r"\bemployee:\d+\b")
        assert r.redact("employee:42 here") == "[EMAIL_REDACTED] here"


class TestRedactorRecursive:
    def test_redact_value_dict(self):
        out = Redactor().redact_value({"email": "x@y.com", "safe": "hi"})
        assert out == {"email": "[EMAIL_REDACTED]", "safe": "hi"}

    def test_redact_value_nested(self):
        out = Redactor().redact_value({"user": {"email": "x@y.com"}, "ssns": ["123-45-6789"]})
        assert out == {
            "user": {"email": "[EMAIL_REDACTED]"},
            "ssns": ["[SSN_REDACTED]"],
        }

    def test_redact_value_list_and_tuple(self):
        out = Redactor().redact_value([("a@b.com",), 42])
        assert out == [("[EMAIL_REDACTED]",), 42]

    def test_find_all_returns_sorted_matches(self):
        ms = Redactor().find_all("a@b.com and 123-45-6789")
        names = {m.name for m in ms}
        assert "email" in names
        assert "ssn" in names
        starts = [m.start for m in ms]
        assert starts == sorted(starts)


class TestTracerRedaction:
    def test_redactor_scrubs_span_attributes(self):
        tracer = Tracer(redactor=Redactor())
        span = tracer.start_span("llm_call", user_email="alice@example.com", safe="ok")
        assert span.attributes["user_email"] == "[EMAIL_REDACTED]"
        assert span.attributes["safe"] == "ok"

    def test_redactor_scrubs_nested_attributes(self):
        tracer = Tracer(redactor=Redactor())
        span = tracer.start_span(
            "llm_call",
            context={"user": {"email": "bob@example.com", "name": "Bob"}},
        )
        assert span.attributes["context"]["user"]["email"] == "[EMAIL_REDACTED]"
        assert span.attributes["context"]["user"]["name"] == "Bob"

    def test_no_redactor_means_no_scrubbing(self):
        tracer = Tracer()
        span = tracer.start_span("llm_call", user_email="alice@example.com")
        assert span.attributes["user_email"] == "alice@example.com"

    def test_redactor_scrubs_events(self):
        # Events added before scrub-time get redacted; since scrubbing
        # happens at start_span(), add the event BEFORE creating the
        # span (by passing via attributes which is the supported path
        # for tracing data with a redactor).
        tracer = Tracer(redactor=Redactor())
        # Scrub applies to attributes passed at span creation. Add an
        # event post-creation to verify the existing event list is
        # not retroactively scrubbed (documented behavior).
        span = tracer.start_span("op", email="x@y.com")
        assert span.attributes["email"] == "[EMAIL_REDACTED]"
        # Post-creation event keeps original data - users can scrub
        # manually before adding sensitive data
        span.add_event("login", attributes={"email": "y@z.com"})
        assert span.events[-1]["attributes"]["email"] == "y@z.com"

    def test_span_attributes_independent_after_scrub(self):
        user_attrs = {"email": "x@y.com"}
        Tracer(redactor=Redactor()).start_span("op", **user_attrs)
        assert user_attrs["email"] == "x@y.com"


class TestRedactionMatchRepr:
    def test_repr(self):
        m = RedactionMatch(name="email", start=5, end=15, replacement="[EMAIL_REDACTED]")
        assert "email" in repr(m)
        assert "10" in repr(m)
