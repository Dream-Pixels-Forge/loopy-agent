"""Cache coverage tests — persistence, eviction, TTL, invalidation."""

from __future__ import annotations

import time

from loopy.cache import LLMCache


class TestCachePersistence:
    def test_persist_and_load(self, tmp_path):
        path = tmp_path / "cache.json"
        c1 = LLMCache(ttl=3600, max_size=10, persist_path=str(path))
        c1.set("What is Python?", "A programming language.", model="gpt-4", tokens=50)
        del c1

        c2 = LLMCache(ttl=3600, max_size=10, persist_path=str(path))
        hit = c2.get("What is Python?", model="gpt-4")
        assert hit == "A programming language."

    def test_load_corrupted_file(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json!!!")
        cache = LLMCache(persist_path=str(path))
        assert cache.get("x", model="m") is None

    def test_load_nonexistent_file(self):
        cache = LLMCache(persist_path="/tmp/loopy_nonexistent_cache_test.json")
        assert cache.get("x", model="m") is None


class TestCacheEviction:
    def test_lru_eviction(self):
        import time as _time
        cache = LLMCache(ttl=3600, max_size=2)
        cache.set("a", "response_a", model="m", tokens=10)
        _time.sleep(0.05)
        cache.set("b", "response_b", model="m", tokens=10)
        _time.sleep(0.05)
        # Access "a" to make it most recently used
        cache.get("a", model="m")
        _time.sleep(0.05)
        # Adding "c" should evict "b" (LRU)
        cache.set("c", "response_c", model="m", tokens=10)
        assert cache.get("b", model="m") is None
        assert cache.get("a", model="m") == "response_a"

    def test_evict_empty_cache(self):
        cache = LLMCache(ttl=3600, max_size=1)
        cache._evict()  # should not raise


class TestCacheTTL:
    def test_expired_entry(self):
        cache = LLMCache(ttl=0, max_size=10)
        cache.set("q", "a", model="m", tokens=5)
        time.sleep(0.01)
        result = cache.get("q", model="m")
        assert result is None


class TestCacheInvalidation:
    def test_invalidate_existing(self):
        cache = LLMCache(ttl=3600, max_size=10)
        cache.set("q", "a", model="m", tokens=5)
        assert cache.invalidate("q", model="m") is True
        assert cache.get("q", model="m") is None

    def test_invalidate_nonexistent(self):
        cache = LLMCache(ttl=3600, max_size=10)
        assert cache.invalidate("nope", model="m") is False

    def test_clear(self):
        cache = LLMCache(ttl=3600, max_size=10)
        cache.set("a", "x", model="m", tokens=5)
        cache.set("b", "y", model="m", tokens=5)
        cache.clear()
        assert cache.get("a", model="m") is None
        stats = cache.stats()
        assert stats.hits == 0
