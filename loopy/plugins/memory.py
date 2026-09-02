"""
Memory Plugin — Long-term agent memory.

Provides persistent memory storage for agents across sessions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loopy.plugins import Plugin, PluginInfo, PluginRegistry

logger = logging.getLogger("loopy.plugins.memory")


@dataclass
class Memory:
    """A single memory entry."""

    id: str
    content: str
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5  # 0.0 to 1.0
    embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "metadata": self.metadata,
            "importance": self.importance,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Memory:
        """Create from dictionary."""
        return cls(**data)


class MemoryStore:
    """
    Persistent memory storage with search capabilities.

    Example:
        store = MemoryStore()

        # Store memories
        await store.add(Memory(
            id="pref_1",
            content="User prefers dark mode",
            category="preferences",
            importance=0.8,
        ))

        # Recall memories
        results = store.recall("user preferences")
    """

    def __init__(self, storage_path: str | Path | None = None):
        self.memories: dict[str, Memory] = {}
        self.storage_path = Path(storage_path) if storage_path else None
        self._counter = 0
        self._dirty = False

        if self.storage_path and self.storage_path.exists():
            self._load()

    async def add(self, memory: Memory) -> None:
        """Add a memory."""
        if not memory.id:
            self._counter += 1
            memory.id = f"mem_{self._counter:08d}"

        self.memories[memory.id] = memory
        self._dirty = True
        await self._save()
        logger.debug("Added memory: %s", memory.id)

    def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID."""
        memory = self.memories.get(memory_id)
        if memory:
            memory.last_accessed = time.time()
            memory.access_count += 1
        return memory

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        if memory_id in self.memories:
            del self.memories[memory_id]
            self._dirty = True
            await self._save()
            return True
        return False

    async def clear(self) -> int:
        """Kill-switch: delete every stored memory (returns count removed).

        Use when memory poisoning is suspected — a full reset beats
        piecemeal deletion.
        """
        count = len(self.memories)
        self.memories.clear()
        self._dirty = True
        await self._save()
        return count

    def recall(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5,
        min_importance: float = 0.0,
    ) -> list[Memory]:
        """
        Recall memories similar to the query.

        Args:
            query: Search query
            category: Filter by category
            top_k: Number of results
            min_importance: Minimum importance score

        Returns:
            List of matching memories
        """
        results = []

        for memory in self.memories.values():
            # Filter by category
            if category and memory.category != category:
                continue

            # Filter by importance
            if memory.importance < min_importance:
                continue

            # Simple keyword matching (could be enhanced with embeddings)
            score = self._score_memory(memory, query)
            if score > 0:
                results.append((memory, score))

        # Sort by score * importance
        results.sort(key=lambda x: -(x[1] * x[0].importance))

        # Update access stats (transient, not persisted)
        memories = [m for m, _ in results[:top_k]]
        for m in memories:
            m.last_accessed = time.time()
            m.access_count += 1

        return memories

    def _score_memory(self, memory: Memory, query: str) -> float:
        """Score a memory against a query."""
        query_words = set(query.lower().split())
        content_words = set(memory.content.lower().split())

        overlap = len(query_words & content_words)
        return overlap / max(len(query_words), 1)

    def list_all(self, category: str | None = None) -> list[Memory]:
        """List all memories, optionally filtered by category."""
        if category:
            return [m for m in self.memories.values() if m.category == category]
        return list(self.memories.values())

    def get_summary(self) -> dict[str, Any]:
        """Get summary of stored memories."""
        categories = {}
        for m in self.memories.values():
            categories[m.category] = categories.get(m.category, 0) + 1

        return {
            "total_memories": len(self.memories),
            "categories": categories,
            "avg_importance": (
                sum(m.importance for m in self.memories.values()) / len(self.memories)
                if self.memories
                else 0
            ),
        }

    async def _save(self) -> None:
        """Save memories to disk only when state has changed."""
        if not self.storage_path or not self._dirty:
            return

        self._dirty = False
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [m.to_dict() for m in self.memories.values()]

        def _write() -> None:
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)

        await asyncio.to_thread(_write)

    def _load(self) -> None:
        """Load memories from disk."""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            with open(self.storage_path) as f:
                data = json.load(f)

            for item in data:
                memory = Memory.from_dict(item)
                self.memories[memory.id] = memory

            logger.info("Loaded %d memories from %s", len(self.memories), self.storage_path)
        except Exception as e:
            logger.error("Failed to load memories: %s", e)


class MemoryPlugin(Plugin):
    """
    Long-term memory plugin for agents.

    Provides persistent memory storage with search capabilities.

    Example:
        plugin = MemoryPlugin(storage_path="./agent_memory.json")
        await registry.load(plugin)

        memory_store = plugin.memory_store

        # Store a memory
        await memory_store.add(Memory(
            id="user_pref_1",
            content="User prefers concise responses",
            category="preferences",
        ))

        # Recall
        memories = memory_store.recall("response style")
    """

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="loopy-memory",
            version="0.3.0",
            description="Long-term memory for loopy agents",
            author="Dream Pixels Forge",
            capabilities=["tool", "storage"],
            requires=[],
        )

    async def setup(self, registry: PluginRegistry) -> None:
        """Initialize the Memory plugin."""
        self.memory_store = MemoryStore()

        # Memory is a privileged store: reads are read-only, but writes are
        # side-effecting and require human approval (injection could
        # otherwise persist poisoned instructions into future sessions).
        registry.register_tool(
            "memory_store",
            self._store_memory,
            requires_approval=True,
            scope="side_effecting",
        )
        registry.register_tool(
            "memory_clear",
            self._clear_memories,
            requires_approval=True,
            scope="side_effecting",
        )
        registry.register_tool("memory_recall", self._recall_memories, scope="read_only")
        registry.register_tool("memory_list", self._list_memories, scope="read_only")

        logger.info("Memory plugin initialized")

    async def _store_memory(
        self,
        content: str,
        category: str = "general",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a new memory."""
        memory = Memory(
            id="",
            content=content,
            category=category,
            importance=importance,
            metadata=metadata or {},
        )
        await self.memory_store.add(memory)
        return {"id": memory.id, "status": "stored"}

    async def _recall_memories(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Recall memories similar to the query."""
        memories = self.memory_store.recall(query, category, top_k)
        return [
            {
                "id": m.id,
                "content": m.content,
                "category": m.category,
                "importance": m.importance,
                "access_count": m.access_count,
            }
            for m in memories
        ]

    async def _list_memories(
        self,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all memories."""
        memories = self.memory_store.list_all(category)
        return [
            {
                "id": m.id,
                "content": m.content,
                "category": m.category,
                "importance": m.importance,
            }
            for m in memories
        ]

    async def _clear_memories(self) -> dict[str, Any]:
        """Kill-switch: wipe all stored memories (approval-gated tool)."""
        count = await self.memory_store.clear()
        return {"status": "cleared", "removed": count}
