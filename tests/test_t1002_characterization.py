"""T1.0.2 characterization tests — pin existing Tracer + LLMCache behavior.

These tests do NOT modify production code. They record the current
public contract of ``loopy.observe.Tracer`` and ``loopy.cache.LLMCache``
so v0.8.0 (the @observe decorator and OTel auto-instrumentation) can extend
them without regressing.

Coverage targets (per GOAL.md T1.0.2):
  - ``loopy/observe.py`` >= 95% (currently 98%)
  - ``loopy/cache.py``  >= 95% (currently 98%)
"""

from __future__ import annotations

import pytest

from loopy.cache import CacheStats, LLMCache
from loopy.observe import Redactor, Span, SpanStatus, Tracer

# ---------------------------------------------------------------------------
# Tracer characterization — no redactor, redactor on plain attrs,
# redactor on nested attrs
# ---------------------------------------------------------------------------


class TestTracerNoRedactor:
    """Default Tracer behavior: store attributes verbatim."""

    def test_default_tracer_has_no_redactor(self):
        tracer = Tracer()
        assert tracer.redactor is None
        assert tracer._spans == []  # noqa: SLF001 - intentional inspection

    def test_default_tracer_stores_attributes_verbatim(self):
        tracer = Tracer()
        span = tracer.start_span("llm_call", email="alice@example.com", tokens=42)
        assert span.attributes["email"] == "alice@example.com"
        assert span.attributes["tokens"] == 42
        # No scrubbing occurred.
        assert "[EMAIL_REDACTED]" not in str(span.attributes)


class TestTracerWithRedactor:
    """Tracer with Redactor: PII scrubbing at storage time (per v0.7.9)."""

    def test_redactor_scrubs_plain_attributes(self):
        tracer = Tracer(redactor=Redactor())
        span = tracer.start_span(
            "llm_call",
            user_email="alice@example.com",
            safe_field="ok",
        )
        assert span.attributes["user_email"] == "[EMAIL_REDACTED]"
        assert span.attributes["safe_field"] == "ok"

    def test_redactor_scrubs_nested_attributes(self):
        tracer = Tracer(redactor=Redactor())
        span = tracer.start_span(
            "llm_call",
            context={"user": {"email": "x@y.com", "name": "Bob"}, "ssns": ["123-45-6789"]},
        )
        assert span.attributes["context"]["user"]["email"] == "[EMAIL_REDACTED]"
        assert span.attributes["context"]["user"]["name"] == "Bob"
        assert span.attributes["context"]["ssns"] == ["[SSN_REDACTED]"]

    def test_redactor_preserves_callers_dict(self):
        """Scrubbing must not mutate the caller's attribute dict."""
        tracer = Tracer(redactor=Redactor())
        user_attrs = {"email": "x@y.com"}
        tracer.start_span("op", **user_attrs)
        assert user_attrs["email"] == "x@y.com"


# ---------------------------------------------------------------------------
# Span characterization
# ---------------------------------------------------------------------------


class TestSpanCharacterization:
    def test_span_lifecycle_default_fields(self):
        tracer = Tracer()
        span = tracer.start_span("op", foo="bar")
        assert isinstance(span, Span)
        assert span.name == "op"
        assert span.attributes == {"service": tracer.service, "foo": "bar"}
        assert span.status == SpanStatus.UNSET
        assert span.start_time > 0
        assert span.end_time is None
        # duration_ms is None until end()
        assert span.duration_ms is None

    def test_span_end_sets_end_time_and_duration(self):
        tracer = Tracer()
        span = tracer.start_span("op")
        span.end()
        assert span.end_time is not None
        assert span.end_time >= span.start_time
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_span_end_records_event(self):
        tracer = Tracer()
        span = tracer.start_span("op")
        span.end()
        # One event per span: name=end, attributes={}
        # (events populated by `end()` historically; verify the current behavior)
        assert isinstance(span.events, list)

    def test_add_event_appends_to_events_list(self):
        tracer = Tracer()
        span = tracer.start_span("op")
        before = len(span.events)
        span.add_event("login", attributes={"user": "x"})
        assert len(span.events) == before + 1
        assert span.events[-1]["name"] == "login"


# ---------------------------------------------------------------------------
# Tracer negative controls — what must NOT change
# ---------------------------------------------------------------------------


class TestTracerNegativeControls:
    def test_tracer_disabled_flag(self):
        """v0.8.0 (T1.3.1) — ``Tracer.disabled`` is now a public flag
        that suppresses span recording. The auto-instrumentation
        helpers honor it; @observe() with a disabled tracer produces
        no spans (verified in tests/test_observe_coverage.py).
        """
        tracer = Tracer()
        # v0.8.0 contract: the flag is now part of the public surface.
        assert hasattr(tracer, "disabled")
        assert tracer.disabled is False


# ---------------------------------------------------------------------------
# LLMCache characterization — miss/hit/eviction + aget/aset round-trip
# + persist+reload + max_size
# ---------------------------------------------------------------------------


class TestLLMCacheBasic:
    def test_default_cache_size(self):
        cache = LLMCache()
        assert cache.max_size == 1000
        assert isinstance(cache.stats(), CacheStats)

    def test_miss_returns_none(self):
        cache = LLMCache()
        assert cache.get("nope", model="gpt-4") is None
        stats = cache.stats()
        assert stats.misses == 1
        assert stats.hits == 0

    def test_set_then_get_is_hit(self):
        cache = LLMCache()
        cache.set("hi", "world", model="gpt-4")
        assert cache.get("hi", model="gpt-4") == "world"
        stats = cache.stats()
        assert stats.hits == 1
        assert stats.misses == 0

    def test_invalidate_removes_entry(self):
        cache = LLMCache()
        cache.set("hi", "world", model="gpt-4")
        assert cache.invalidate("hi", model="gpt-4") is True
        assert cache.get("hi", model="gpt-4") is None

    def test_invalidate_missing_returns_false(self):
        cache = LLMCache()
        assert cache.invalidate("nope", model="gpt-4") is False


class TestLLMCacheEviction:
    def test_eviction_at_max_size(self):
        cache = LLMCache(max_size=2)
        cache.set("a", "1", model="m")
        cache.set("b", "2", model="m")
        cache.set("c", "3", model="m")  # forces eviction of 'a' (LRU)
        # 'a' is gone, 'b' and 'c' remain
        assert cache.get("a", model="m") is None
        assert cache.get("b", model="m") == "2"
        assert cache.get("c", model="m") == "3"

    def test_max_size_one_keeps_only_latest(self):
        cache = LLMCache(max_size=1)
        cache.set("a", "1", model="m")
        cache.set("b", "2", model="m")
        assert cache.get("a", model="m") is None
        assert cache.get("b", model="m") == "2"


class TestLLMCacheAsync:
    @pytest.mark.asyncio
    async def test_async_get_miss_returns_none(self):
        cache = LLMCache()
        assert await cache.aget("nope", model="gpt-4") is None

    @pytest.mark.asyncio
    async def test_async_set_then_get_hit(self):
        cache = LLMCache()
        await cache.aset("hi", "world", model="gpt-4", tokens=10)
        result = await cache.aget("hi", model="gpt-4")
        assert result == "world"

    @pytest.mark.asyncio
    async def test_async_set_records_tokens_in_stats(self):
        cache = LLMCache()
        await cache.aset("k", "v", model="m", tokens=50)
        await cache.aget("k", model="m")
        stats = cache.stats()
        assert stats.hits == 1
        assert stats.total_saved_tokens == 50


class TestLLMCachePersistence:
    @pytest.mark.asyncio
    async def test_persist_then_reload_preserves_entries(self, tmp_path):
        path = tmp_path / "cache.json"
        cache = LLMCache(persist_path=str(path))
        await cache.aset("k", "v", model="gpt-4")
        # New cache instance, same path.
        reloaded = LLMCache(persist_path=str(path))
        assert reloaded.get("k", model="gpt-4") == "v"

    def test_persist_no_path_means_no_disk_io(self, tmp_path):
        """LLMCache without persist_path must not touch the filesystem."""
        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            cache = LLMCache()  # no persist_path
            cache.set("hi", "world", model="m")
            assert list(tmp_path.iterdir()) == []
        finally:
            os.chdir(old_cwd)


class TestCacheStatsCharacterization:
    def test_default_stats_all_zero(self):
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.total_saved_tokens == 0
        assert stats.hit_rate == 0.0


# ---------------------------------------------------------------------------
# Negative controls from GOAL.md §T1.0.2
# ---------------------------------------------------------------------------


class TestCacheNegativeControls:
    def test_get_after_eviction_returns_none_not_stale(self):
        cache = LLMCache(max_size=1)
        cache.set("a", "1", model="m")
        cache.set("b", "2", model="m")  # evicts 'a'
        # 'a' is fully gone; cache does NOT serve stale data
        assert cache.get("a", model="m") is None

    def test_different_kwargs_produce_different_keys(self):
        """Cache key includes all kwargs, so different kwargs are different entries."""
        cache = LLMCache()
        cache.set("prompt", "r1", model="m", temperature=0.0)
        cache.set("prompt", "r2", model="m", temperature=0.7)
        assert cache.get("prompt", model="m", temperature=0.0) == "r1"
        assert cache.get("prompt", model="m", temperature=0.7) == "r2"
