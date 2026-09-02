"""
Inference Economics — Tokens are the unit of cost.

Semantic token caching to reduce LLM inference costs by ~10-30%.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.cache")


@dataclass
class CacheEntry:
    """A cached response."""
    
    key: str
    response: str
    model: str
    tokens_saved: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CacheStats:
    """Cache statistics."""
    
    hits: int = 0
    misses: int = 0
    total_saved_tokens: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    @property
    def estimated_savings(self) -> float:
        """Rough cost estimate assuming $0.03 per 1K tokens."""
        return (self.total_saved_tokens / 1000) * 0.03


class LLMCache:
    """
    Semantic cache for LLM responses.
    
    Caches responses by hashing the prompt + model combination.
    Supports TTL, size limits, and persistence.
    
    Example:
        cache = LLMCache(ttl=3600, max_size=1000)
        
        # Check cache before calling LLM
        cached = cache.get("What is Python?", model="gpt-4")
        if cached:
            response = cached
        else:
            response = await call_llm("What is Python?")
            cache.set("What is Python?", response, model="gpt-4")
        
        stats = cache.stats()
        print(f"Cache hit rate: {stats.hit_rate:.1%}")
    """

    def __init__(
        self,
        ttl: int = 3600,
        max_size: int = 1000,
        persist_path: str | Path | None = None,
    ):
        """
        Args:
            ttl: Time-to-live in seconds
            max_size: Maximum number of entries
            persist_path: Optional path to persist cache to disk
        """
        self.ttl = ttl
        self.max_size = max_size
        self.persist_path = Path(persist_path) if persist_path else None
        
        self._cache: dict[str, CacheEntry] = {}
        self._stats = CacheStats()
        
        # Load persisted cache
        if self.persist_path and self.persist_path.exists():
            self._load()

    def _make_key(self, prompt: str, model: str, **kwargs: Any) -> str:
        """Generate cache key from prompt and model."""
        key_data = {
            "prompt": prompt,
            "model": model,
            **kwargs,
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def get(self, prompt: str, model: str, **kwargs: Any) -> str | None:
        """
        Get cached response if available.
        
        Returns:
            Cached response string or None
        """
        key = self._make_key(prompt, model, **kwargs)
        
        entry = self._cache.get(key)
        if not entry:
            self._stats.misses += 1
            return None
        
        # Check TTL
        if time.time() - entry.created_at > self.ttl:
            del self._cache[key]
            self._stats.misses += 1
            return None
        
        # Update access stats
        entry.last_accessed = time.time()
        entry.access_count += 1
        self._stats.hits += 1
        self._stats.total_saved_tokens += entry.tokens_saved
        
        logger.debug("Cache hit: %s... (accessed %dx)", key[:8], entry.access_count)
        return entry.response

    def set(
        self,
        prompt: str,
        response: str,
        model: str,
        tokens: int = 0,
        **kwargs: Any,
    ) -> None:
        """
        Cache a response.
        
        Args:
            prompt: The input prompt
            response: The model's response
            model: Model identifier
            tokens: Number of tokens in the response (for savings tracking)
        """
        key = self._make_key(prompt, model, **kwargs)
        
        # Evict if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict()
        
        self._cache[key] = CacheEntry(
            key=key,
            response=response,
            model=model,
            tokens_saved=tokens,
        )
        
        logger.debug("Cached response: %s... (%d tokens)", key[:8], tokens)
        
        # Persist if configured
        if self.persist_path:
            self._save()

    def invalidate(self, prompt: str, model: str, **kwargs: Any) -> bool:
        """Remove a specific entry from cache."""
        key = self._make_key(prompt, model, **kwargs)
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def aget(self, prompt: str, model: str, **kwargs: Any) -> str | None:
        """v0.7.8 — Async wrapper around :meth:`get`.

        Identical semantics; provided so async callers can `await` without
        having to drop into a thread executor themselves.
        """
        return self.get(prompt, model, **kwargs)

    async def aset(
        self,
        prompt: str,
        response: str,
        model: str,
        tokens: int = 0,
        **kwargs: Any,
    ) -> None:
        """v0.7.8 — Async wrapper around :meth:`set` with non-blocking I/O.

        Mirrors the v0.7.7 ``MemoryStore`` async-save pattern: the in-memory
        write happens synchronously (cheap), and disk persistence — when
        ``persist_path`` is configured — runs in a worker thread via
        ``asyncio.to_thread`` so a slow filesystem cannot stall the loop.
        """
        key = self._make_key(prompt, model, **kwargs)

        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict()

        self._cache[key] = CacheEntry(
            key=key,
            response=response,
            model=model,
            tokens_saved=tokens,
        )

        if self.persist_path:
            await self._asave()

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._stats = CacheStats()
        logger.info("Cache cleared")

    def stats(self) -> CacheStats:
        """Return cache statistics."""
        return self._stats

    def _evict(self) -> None:
        """Evict the least recently used cache entry.

        Uses *last_accessed* timestamps to find the LRU entry.
        Called automatically when the cache is at capacity.
        """
        if not self._cache:
            return

        # Find LRU entry
        lru_key = min(self._cache, key=lambda k: self._cache[k].last_accessed)
        del self._cache[lru_key]
        logger.debug("Evicted LRU entry: %s...", lru_key[:8])

    def _save(self) -> None:
        """Persist the in-memory cache to disk as JSON.

        Creates parent directories if they don't exist.
        Silently skips if *persist_path* was not configured.
        """
        if not self.persist_path:
            return

        self.persist_path.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for key, entry in self._cache.items():
            data[key] = {
                "response": entry.response,
                "model": entry.model,
                "tokens_saved": entry.tokens_saved,
                "created_at": entry.created_at,
            }

        self.persist_path.write_text(json.dumps(data, indent=2))

    async def _asave(self) -> None:
        """v0.7.8 - Async persistence; runs the blocking write in a worker.

        Snapshots the cache into a plain dict on the event-loop thread
        (cheap), then writes the JSON file via ``asyncio.to_thread`` so a
        slow disk never blocks other coroutines.
        """
        if not self.persist_path:
            return

        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: {
                "response": entry.response,
                "model": entry.model,
                "tokens_saved": entry.tokens_saved,
                "created_at": entry.created_at,
            }
            for key, entry in self._cache.items()
        }

        def _write() -> None:
            self.persist_path.write_text(json.dumps(payload, indent=2))

        await asyncio.to_thread(_write)

    def _load(self) -> None:
        """Restore the in-memory cache from the persisted JSON file.

        Silently skips if no persisted file exists.
        On parse failure, starts with an empty cache and logs a warning.
        """
        if not self.persist_path or not self.persist_path.exists():
            return

        try:
            data = json.loads(self.persist_path.read_text())
            for key, entry_data in data.items():
                self._cache[key] = CacheEntry(
                    key=key,
                    response=entry_data["response"],
                    model=entry_data["model"],
                    tokens_saved=entry_data.get("tokens_saved", 0),
                    created_at=entry_data.get("created_at", time.time()),
                )
            logger.info("Loaded %d entries from cache", len(self._cache))
        except Exception as e:
            logger.warning("Failed to load cache: %s", e)
