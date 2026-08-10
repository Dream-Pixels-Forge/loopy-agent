"""Plugin system coverage tests — loading, extensions, approval, directory discovery."""

from __future__ import annotations

from typing import Any

import pytest

from loopy.plugins import (
    Plugin,
    PluginInfo,
    PluginLoader,
    PluginRegistry,
    redact_arguments,
)

# ── Test plugin ──────────────────────────────────────────────

class FakePlugin(Plugin):
    def __init__(
        self, name: str = "fake", version: str = "1.0.0",
        requires: list[str] | None = None,
    ):
        self._name = name
        self._version = version
        self._requires = requires or []
        self.teardown_called = False

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name=self._name,
            version=self._version,
            description="Fake plugin for tests",
            author="test",
            url="",
            capabilities=["tool"],
            requires=self._requires,
        )

    async def setup(self, registry: PluginRegistry) -> None:
        async def handler(**kwargs: Any) -> str:
            return "fake result"
        registry.register_tool("fake_tool", handler)

    async def teardown(self) -> None:
        self.teardown_called = True


# ── PluginRegistry.load ──────────────────────────────────────

class TestPluginRegistryLoad:
    @pytest.mark.asyncio
    async def test_load_plugin(self):
        reg = PluginRegistry()
        plugin = FakePlugin()
        await reg.load(plugin)
        assert reg.get_plugin("fake") is plugin

    @pytest.mark.asyncio
    async def test_load_duplicate_skips(self):
        reg = PluginRegistry()
        p1 = FakePlugin(name="dup")
        p2 = FakePlugin(name="dup")
        await reg.load(p1)
        await reg.load(p2)  # should skip, not error
        assert reg.get_plugin("dup") is p1

    @pytest.mark.asyncio
    async def test_load_missing_dependency_raises(self):
        reg = PluginRegistry()
        plugin = FakePlugin(name="child", requires=["missing_parent"])
        with pytest.raises(RuntimeError, match="requires missing_parent"):
            await reg.load(plugin)

    @pytest.mark.asyncio
    async def test_load_with_dependency_satisfied(self):
        reg = PluginRegistry()
        parent = FakePlugin(name="parent")
        child = FakePlugin(name="child", requires=["parent"])
        await reg.load(parent)
        await reg.load(child)
        assert reg.get_plugin("child") is child


# ── PluginRegistry.execute_tool approval paths ───────────────

class TestPluginRegistryExecuteTool:
    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        reg = PluginRegistry()
        with pytest.raises(ValueError, match="Tool not found"):
            await reg.execute_tool("nonexistent")
        assert len(reg.denials()) == 1
        assert reg.denials()[0]["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_execute_tool_approval_required_no_approver(self):
        reg = PluginRegistry()

        async def dangerous(**kwargs):
            return "result"

        reg.register_tool("dangerous", dangerous, requires_approval=True)
        with pytest.raises(PermissionError, match="no approver"):
            await reg.execute_tool("dangerous")
        assert any(d["reason"] == "approval_required_no_approver" for d in reg.denials())

    @pytest.mark.asyncio
    async def test_execute_tool_approval_denied(self):
        reg = PluginRegistry()

        async def dangerous(**kwargs):
            return "result"

        reg.register_tool("dangerous", dangerous, requires_approval=True)

        async def deny_all(name, args):
            return False

        with pytest.raises(PermissionError, match="not approved"):
            await reg.execute_tool("dangerous", approver=deny_all)
        assert any(d["reason"] == "approval_denied" for d in reg.denials())

    @pytest.mark.asyncio
    async def test_execute_tool_approval_granted(self):
        reg = PluginRegistry()

        async def safe(**kwargs):
            return "ok"

        reg.register_tool("safe", safe, requires_approval=True)

        async def approve(name, args):
            return True

        result = await reg.execute_tool("safe", approver=approve)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_execute_tool_allowed_values_violation(self):
        reg = PluginRegistry()

        async def color_picker(**kwargs):
            return kwargs.get("color", "red")

        reg.register_tool(
            "color_picker",
            color_picker,
            allowed_values={"color": {"red", "green", "blue"}},
        )
        with pytest.raises(ValueError, match="outside allowed values"):
            await reg.execute_tool("color_picker", {"color": "purple"})
        assert any("out of range" in d["reason"] for d in reg.denials())

    @pytest.mark.asyncio
    async def test_execute_tool_allowed_values_ok(self):
        reg = PluginRegistry()

        async def color_picker(**kwargs):
            return kwargs.get("color", "red")

        reg.register_tool(
            "color_picker",
            color_picker,
            allowed_values={"color": {"red", "green", "blue"}},
        )
        result = await reg.execute_tool("color_picker", {"color": "green"})
        assert result == "green"

    @pytest.mark.asyncio
    async def test_execute_tool_agent_visibility(self):
        reg = PluginRegistry()

        async def hidden(**kwargs):
            return "secret"

        reg.register_tool("hidden_tool", hidden, agent_visible=False)
        assert "hidden_tool" not in reg.list_tools()
        assert "hidden_tool" in reg.list_all_tools()


# ── PluginRegistry extensions ────────────────────────────────

class TestPluginRegistryExtensions:
    @pytest.mark.asyncio
    async def test_register_and_trigger_extension(self):
        reg = PluginRegistry()
        results = []

        async def my_hook(data):
            results.append(data)
            return "hooked"

        reg.register_extension("on_before_chat", my_hook)
        out = await reg.trigger_extension("on_before_chat", "test_data")
        assert out == ["hooked"]
        assert results == ["test_data"]

    @pytest.mark.asyncio
    async def test_trigger_extension_with_error(self):
        reg = PluginRegistry()

        async def bad_hook(data):
            raise RuntimeError("boom")

        reg.register_extension("on_error", bad_hook)
        out = await reg.trigger_extension("on_error", "data")
        assert out == []  # error swallowed, logged

    @pytest.mark.asyncio
    async def test_trigger_extension_no_hooks(self):
        reg = PluginRegistry()
        out = await reg.trigger_extension("nonexistent")
        assert out == []


# ── PluginRegistry unload ────────────────────────────────────

class TestPluginRegistryUnload:
    @pytest.mark.asyncio
    async def test_unload_plugin(self):
        reg = PluginRegistry()
        plugin = FakePlugin()
        await reg.load(plugin)
        result = await reg.unload("fake")
        assert result is True
        assert reg.get_plugin("fake") is None
        assert plugin.teardown_called

    @pytest.mark.asyncio
    async def test_unload_nonexistent(self):
        reg = PluginRegistry()
        result = await reg.unload("nope")
        assert result is False

    @pytest.mark.asyncio
    async def test_unload_all(self):
        reg = PluginRegistry()
        p1 = FakePlugin(name="a")
        p2 = FakePlugin(name="b")
        await reg.load(p1)
        await reg.load(p2)
        await reg.unload_all()
        assert reg.list_plugins() == []


# ── PluginRegistry load_package ──────────────────────────────

class TestPluginRegistryLoadPackage:
    @pytest.mark.asyncio
    async def test_load_package_not_found(self):
        reg = PluginRegistry()
        with pytest.raises(ImportError):
            await reg.load_package("nonexistent_package_xyz.plugin")

    @pytest.mark.asyncio
    async def test_load_package_no_plugin_attr(self):
        reg = PluginRegistry()
        with pytest.raises(ValueError, match="No 'plugin' attribute"):
            await reg.load_package("json")  # json has no 'plugin' attr

    @pytest.mark.asyncio
    async def test_load_package_wrong_type(self):
        from unittest.mock import patch

        reg = PluginRegistry()
        with patch("loopy.plugins.importlib.import_module") as mock_import:
            mock_mod = type("Mod", (), {"plugin": "not_a_plugin"})()
            mock_import.return_value = mock_mod
            with pytest.raises(TypeError, match="not a Plugin instance"):
                await reg.load_package("fake_module")


# ── PluginRegistry load_directory ────────────────────────────

class TestPluginRegistryLoadDirectory:
    @pytest.mark.asyncio
    async def test_load_directory_not_exists(self):
        reg = PluginRegistry()
        count = await reg.load_directory("/nonexistent/path")
        assert count == 0

    @pytest.mark.asyncio
    async def test_load_directory_with_plugin(self, tmp_path):
        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text(
            "from loopy.plugins import Plugin, PluginInfo\n"
            "class TestP(Plugin):\n"
            "    @property\n"
            "    def info(self):\n"
            "        return PluginInfo(name='dir_plugin', version='1.0.0')\n"
            "    async def setup(self, registry):\n"
            "        pass\n"
            "plugin = TestP()\n"
        )
        reg = PluginRegistry()
        count = await reg.load_directory(tmp_path)
        assert count == 1
        assert reg.get_plugin("dir_plugin") is not None

    @pytest.mark.asyncio
    async def test_load_directory_skips_underscore(self, tmp_path):
        plugin_file = tmp_path / "_private.py"
        plugin_file.write_text("# private\n")
        reg = PluginRegistry()
        count = await reg.load_directory(tmp_path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_load_directory_no_plugin_attr(self, tmp_path):
        plugin_file = tmp_path / "bare.py"
        plugin_file.write_text("x = 1\n")
        reg = PluginRegistry()
        count = await reg.load_directory(tmp_path)
        assert count == 0


# ── PluginLoader.discover ────────────────────────────────────

class TestPluginLoaderDiscover:
    @pytest.mark.asyncio
    async def test_discover_no_package_no_dir(self):
        loader = PluginLoader()
        count = await loader.discover()
        assert count == 0

    @pytest.mark.asyncio
    async def test_discover_bad_package(self):
        loader = PluginLoader()
        count = await loader.discover(package="nonexistent_pkg_xyz")
        assert count == 0

    @pytest.mark.asyncio
    async def test_discover_directory(self, tmp_path):
        plugin_file = tmp_path / "disc_plugin.py"
        plugin_file.write_text(
            "from loopy.plugins import Plugin, PluginInfo\n"
            "class D(Plugin):\n"
            "    @property\n"
            "    def info(self):\n"
            "        return PluginInfo(name='discovered', version='1.0.0')\n"
            "    async def setup(self, r):\n"
            "        pass\n"
            "plugin = D()\n"
        )
        loader = PluginLoader()
        count = await loader.discover(directory=tmp_path)
        assert count == 1


# ── redact_arguments ─────────────────────────────────────────

class TestRedactArguments:
    def test_redacts_api_key(self):
        result = redact_arguments({"api_key": "sk-secret", "name": "hello"})
        assert result["api_key"] == "***"
        assert result["name"] == "hello"

    def test_redacts_nested(self):
        result = redact_arguments({"config": {"token": "abc", "safe": "ok"}})
        assert result["config"]["token"] == "***"
        assert result["config"]["safe"] == "ok"

    def test_keeps_lists(self):
        result = redact_arguments({"items": [1, 2, 3]})
        assert result["items"] == [1, 2, 3]
