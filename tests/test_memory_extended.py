"""Extended tests for loopy.plugins.memory — store, tools, edge cases."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from loopy.plugins.memory import Memory, MemoryPlugin, MemoryStore

# ── MemoryStore ─────────────────────────────────────────────


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_add_and_get(self):
        store = MemoryStore()
        mem = Memory(id="m1", content="dark mode", category="prefs", importance=0.9)
        await store.add(mem)
        retrieved = store.get("m1")  # sync
        assert retrieved is not None
        assert retrieved.content == "dark mode"

    @pytest.mark.asyncio
    async def test_add_auto_assigns_id(self):
        store = MemoryStore()
        mem = Memory(id="", content="no id", category="c", importance=0.5)
        await store.add(mem)
        assert mem.id.startswith("mem_")

    def test_get_missing_returns_none(self):
        store = MemoryStore()
        assert store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_delete_existing(self):
        store = MemoryStore()
        mem = Memory(id="del1", content="x", category="c", importance=0.5)
        await store.add(mem)
        assert await store.delete("del1") is True
        assert store.get("del1") is None

    def test_delete_missing_returns_false(self):
        store = MemoryStore()
        assert asyncio.run(store.delete("nope")) is False

    @pytest.mark.asyncio
    async def test_clear_wipes_all(self):
        store = MemoryStore()
        for i in range(3):
            await store.add(Memory(id=f"c{i}", content=f"content {i}", category="c"))
        count = await store.clear()
        assert count == 3
        assert len(store.memories) == 0

    def test_recall_filters_by_category(self):
        store = MemoryStore()
        store.memories = {
            "a": Memory(id="a", content="ci failed", category="ops", importance=0.8),
            "b": Memory(id="b", content="deploy now", category="ops", importance=0.6),
            "c": Memory(id="c", content="design system", category="ui", importance=0.7),
        }
        results = store.recall("deploy", category="ops")
        assert len(results) == 1
        assert results[0].id == "b"

    def test_recall_filters_by_importance(self):
        store = MemoryStore()
        store.memories = {
            "low": Memory(id="low", content="something", category="c", importance=0.1),
            "high": Memory(id="high", content="important", category="c", importance=0.9),
        }
        results = store.recall("important", min_importance=0.5)
        assert len(results) == 1
        assert results[0].id == "high"

    def test_recall_empty_query_returns_empty(self):
        """Empty query has zero keyword overlap → score 0, not returned."""
        store = MemoryStore()
        store.memories = {
            "m1": Memory(id="m1", content="something here", category="c", importance=0.8),
        }
        results = store.recall("")
        assert results == []

    def test_recall_sorted_by_score_x_importance(self):
        store = MemoryStore()
        store.memories = {
            "high_score": Memory(
                id="high_score", content="ci build deploy", category="ops", importance=0.3
            ),
            "med_score": Memory(
                id="med_score", content="build process", category="ops", importance=0.9
            ),
        }
        results = store.recall("build")
        # Both match on "build"; high_score has more hits but lower importance
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_persist_and_reload(self, tmp_path: Path):
        store = MemoryStore(storage_path=tmp_path / "mem.json")
        mem = Memory(id="p1", content="persisted", category="c", importance=0.7)
        await store.add(mem)
        # Reload from disk
        store2 = MemoryStore(storage_path=tmp_path / "mem.json")
        loaded = store2.get("p1")  # sync
        assert loaded is not None
        assert loaded.content == "persisted"

    def test_list_all(self):
        store = MemoryStore()
        store.memories = {
            "a": Memory(id="a", content="x", category="ops"),
            "b": Memory(id="b", content="y", category="ui"),
        }
        all_mem = store.list_all()
        assert len(all_mem) == 2
        ops_only = store.list_all(category="ops")
        assert len(ops_only) == 1
        assert ops_only[0].id == "a"

    def test_get_summary(self):
        store = MemoryStore()
        store.memories = {
            "a": Memory(id="a", content="x", category="ops"),
            "b": Memory(id="b", content="y", category="ui"),
            "c": Memory(id="c", content="z", category="ops"),
        }
        summary = store.get_summary()
        assert summary["total_memories"] == 3
        assert summary["categories"]["ops"] == 2
        assert summary["categories"]["ui"] == 1


# ── MemoryPlugin ────────────────────────────────────────────


class TestMemoryPlugin:
    def test_info_property(self):
        plugin = MemoryPlugin()
        info = plugin.info
        assert info.name == "loopy-memory"
        assert info.version == "0.3.0"

    def test_setup_registers_tools(self):
        plugin = MemoryPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        asyncio.run(plugin.setup(reg))
        names = reg.list_tools()  # returns list[str]
        assert "memory_store" in names
        assert "memory_recall" in names
        assert "memory_list" in names
        assert "memory_clear" in names

    @pytest.mark.asyncio
    async def test_store_memory_tool(self):
        plugin = MemoryPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        await plugin.setup(reg)
        # The handler is registered as a string key; call it directly
        store_handler = reg._tools["memory_store"]
        result = await store_handler(content="preference", category="user")
        assert result["status"] == "stored"
        assert result["id"].startswith("mem_")

    @pytest.mark.asyncio
    async def test_recall_memories_tool(self):
        plugin = MemoryPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        await plugin.setup(reg)
        store_handler = reg._tools["memory_store"]
        await store_handler(content="dark mode", category="prefs")
        recall_handler = reg._tools["memory_recall"]
        results = await recall_handler(query="dark mode")
        assert len(results) >= 1
        assert results[0]["category"] == "prefs"

    @pytest.mark.asyncio
    async def test_list_memories_tool(self):
        plugin = MemoryPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        await plugin.setup(reg)
        store_handler = reg._tools["memory_store"]
        await store_handler(content="x", category="c")
        list_handler = reg._tools["memory_list"]
        results = await list_handler()
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_clear_memories_tool(self):
        plugin = MemoryPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        await plugin.setup(reg)
        store_handler = reg._tools["memory_store"]
        await store_handler(content="temp", category="c")
        clear_handler = reg._tools["memory_clear"]
        result = await clear_handler()
        assert result["status"] == "cleared"
        assert result["removed"] >= 1
