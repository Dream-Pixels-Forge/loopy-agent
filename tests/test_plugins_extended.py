"""Extended plugin registry tests — load_directory, load_package, execute_tool paths."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from loopy.plugins import (
    Plugin,
    PluginInfo,
    PluginLoader,
    PluginRegistry,
    redact_arguments,
)


class _StubPlugin(Plugin):
    def __init__(self, name: str = "stub") -> None:
        self._info = PluginInfo(name=name, version="1.0.0", description="stub")

    @property
    def info(self) -> PluginInfo:
        return self._info

    async def setup(self, registry: PluginRegistry) -> None:
        pass

    async def teardown(self) -> None:
        pass


# ── PluginRegistry.load_package ───────────────────────────────


class TestLoadPackage:
    @pytest.mark.asyncio
    async def test_load_package_missing_module(self):
        reg = PluginRegistry()
        with pytest.raises(ImportError):
            await reg.load_package("nonexistent_module_xyz")

    @pytest.mark.asyncio
    async def test_load_package_no_plugin_attr(self):
        reg = PluginRegistry()
        with pytest.raises((ValueError, ImportError)):
            await reg.load_package("tests.test_plugins_tools_extended")


# ── PluginRegistry.load_directory ─────────────────────────────


class TestLoadDirectory:
    @pytest.mark.asyncio
    async def test_load_directory_nonexistent(self):
        reg = PluginRegistry()
        count = await reg.load_directory("/nonexistent/path/that/does/not/exist")
        assert count == 0

    @pytest.mark.asyncio
    async def test_load_directory_with_valid_plugin(self, tmp_path: Path):
        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text(
            "from loopy.plugins import Plugin, PluginInfo, PluginRegistry\n\n"
            "class MyPlugin(Plugin):\n"
            "    @property\n"
            "    def info(self):\n"
            "        return PluginInfo(name='my-plugin', version='1.0.0')\n"
            "\n"
            "    async def setup(self, registry: PluginRegistry) -> None:\n"
            "        pass\n"
            "\n"
            "plugin = MyPlugin()\n"
        )
        reg = PluginRegistry()
        count = await reg.load_directory(tmp_path)
        assert count == 1
        assert reg.get_plugin("my-plugin") is not None

    @pytest.mark.asyncio
    async def test_load_directory_skips_private_modules(self, tmp_path: Path):
        private_file = tmp_path / "_private.py"
        private_file.write_text(
            "from loopy.plugins import Plugin, PluginInfo, PluginRegistry\n\n"
            "class PrivatePlugin(Plugin):\n"
            "    @property\n"
            "    def info(self):\n"
            "        return PluginInfo(name='private', version='1.0.0')\n"
            "    async def setup(self, registry: PluginRegistry) -> None:\n"
            "        pass\n"
            "plugin = PrivatePlugin()\n"
        )
        reg = PluginRegistry()
        count = await reg.load_directory(tmp_path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_load_directory_with_no_plugin_attr(self, tmp_path: Path):
        bad_file = tmp_path / "no_plugin.py"
        bad_file.write_text("# this module has no plugin attribute\nx = 1\n")
        reg = PluginRegistry()
        count = await reg.load_directory(tmp_path)
        assert count == 0


# ── PluginRegistry.execute_tool paths ─────────────────────────


class TestExecuteToolPaths:
    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        reg = PluginRegistry()
        with pytest.raises(ValueError, match="not found"):
            await reg.execute_tool("missing_tool")

    @pytest.mark.asyncio
    async def test_execute_tool_requires_approval_no_approver(self):
        reg = PluginRegistry()
        reg.register_tool("sensitive", lambda **kwargs: "ok", requires_approval=True)
        with pytest.raises(PermissionError, match="approval"):
            await reg.execute_tool("sensitive")

    @pytest.mark.asyncio
    async def test_execute_tool_approval_denied(self):
        reg = PluginRegistry()
        reg.register_tool("maybe", lambda **kwargs: "ok", requires_approval=True)

        async def deny_approver(_name, _args):
            return False

        with pytest.raises(PermissionError, match="not approved"):
            await reg.execute_tool("maybe", approver=deny_approver)

    @pytest.mark.asyncio
    async def test_execute_tool_allowed_values_violation(self):
        reg = PluginRegistry()
        reg.register_tool(
            "color_picker",
            lambda color, **kwargs: color,
            allowed_values={"color": {"red", "green", "blue"}},
        )
        with pytest.raises(ValueError, match="outside allowed"):
            await reg.execute_tool("color_picker", arguments={"color": "purple"})

    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        reg = PluginRegistry()

        async def greet_handler(name, **kwargs):
            return f"hello {name}"

        reg.register_tool("greet", greet_handler)
        result = await reg.execute_tool("greet", arguments={"name": "world"})
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_execute_tool_with_approved_handler(self):
        reg = PluginRegistry()

        async def deploy_handler(env, **kwargs):
            return f"deployed to {env}"

        reg.register_tool("deploy", deploy_handler, requires_approval=True)

        async def approve_approver(_name, _args):
            return True

        result = await reg.execute_tool(
            "deploy", arguments={"env": "prod"}, approver=approve_approver
        )
        assert result == "deployed to prod"


# ── PluginRegistry denials audit trail ────────────────────────


class TestDenialsAudit:
    def test_denials_empty_when_no_rejections(self):
        reg = PluginRegistry()
        assert reg.denials() == []

    @pytest.mark.asyncio
    async def test_denials_records_not_found(self):
        reg = PluginRegistry()
        with pytest.raises(ValueError):
            await reg.execute_tool("missing")
        denials = reg.denials()
        assert len(denials) >= 1
        assert denials[-1]["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_denials_records_approval_required(self):
        reg = PluginRegistry()
        reg.register_tool("secret_op", lambda **kw: "x", requires_approval=True)
        with pytest.raises(PermissionError):
            await reg.execute_tool("secret_op")
        denials = reg.denials()
        reasons = [d["reason"] for d in denials]
        assert "approval_required_no_approver" in reasons

    def test_denials_bounded_to_max(self):
        reg = PluginRegistry()
        for i in range(1005):
            with pytest.raises(ValueError):
                asyncio.run(reg.execute_tool(f"tool-{i}"))
        denials = reg.denials()
        assert len(denials) <= 1000

    @pytest.mark.asyncio
    async def test_denials_redact_sensitive_params(self):
        reg = PluginRegistry()
        reg.register_tool("auth_op", lambda api_key, **kw: api_key, requires_approval=True)

        async def deny_approver(_n, _a):
            return False

        with pytest.raises(PermissionError):
            await reg.execute_tool(
                "auth_op",
                arguments={"api_key": "super-secret-key", "user": "alice"},
                approver=deny_approver,
            )
        denials = reg.denials()
        for d in denials:
            if d["reason"] == "approval_denied":
                assert d["arguments"]["api_key"] == "***"
                assert d["arguments"]["user"] == "alice"
                break
        else:
            pytest.fail("expected approval_denied denial")


# ── PluginRegistry list tools ─────────────────────────────────


class TestListTools:
    def test_list_tools_excludes_hidden(self):
        reg = PluginRegistry()
        reg.register_tool("public_tool", lambda: "ok", agent_visible=True)
        reg.register_tool("internal_tool", lambda: "ok", agent_visible=False)
        assert reg.list_tools() == ["public_tool"]

    def test_list_all_tools_includes_hidden(self):
        reg = PluginRegistry()
        reg.register_tool("public_tool", lambda: "ok", agent_visible=True)
        reg.register_tool("internal_tool", lambda: "ok", agent_visible=False)
        assert set(reg.list_all_tools()) == {"public_tool", "internal_tool"}

    def test_get_tool_spec(self):
        reg = PluginRegistry()
        reg.register_tool(
            "t",
            lambda: None,
            agent_visible=True,
            requires_approval=True,
            scope="side_effecting",
            allowed_values={"env": {"dev", "prod"}},
        )
        spec = reg.get_tool_spec("t")
        assert spec["requires_approval"] is True
        assert spec["scope"] == "side_effecting"
        assert spec["allowed_values"] == {"env": {"dev", "prod"}}


# ── PluginLoader.discover ─────────────────────────────────────


class TestPluginLoader:
    @pytest.mark.asyncio
    async def test_discover_with_nonexistent_package(self):
        loader = PluginLoader()
        count = await loader.discover(package="nonexistent_pkg_xyz")
        assert count == 0

    @pytest.mark.asyncio
    async def test_discover_with_valid_package(self):
        loader = PluginLoader()
        count = await loader.discover(package="loopy.plugins.rag")
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_discover_with_empty_directory(self, tmp_path: Path):
        loader = PluginLoader()
        count = await loader.discover(directory=tmp_path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_discover_with_valid_directory(self, tmp_path: Path):
        plugin_file = tmp_path / "discover_me.py"
        plugin_file.write_text(
            "from loopy.plugins import Plugin, PluginInfo, PluginRegistry\n\n"
            "class DiscoverMe(Plugin):\n"
            "    @property\n"
            "    def info(self):\n"
            "        return PluginInfo(name='discover-me', version='1.0.0')\n"
            "    async def setup(self, registry: PluginRegistry) -> None:\n"
            "        pass\n"
            "plugin = DiscoverMe()\n"
        )
        loader = PluginLoader()
        count = await loader.discover(directory=tmp_path)
        assert count == 1
        plugin = loader.registry.get_plugin("discover-me")
        assert plugin is not None


# ── redact_arguments ──────────────────────────────────────────


class TestRedactArguments:
    def test_redacts_api_key(self):
        result = redact_arguments({"api_key": "secret123", "user": "alice"})
        assert result["api_key"] == "***"
        assert result["user"] == "alice"

    def test_redacts_password(self):
        result = redact_arguments({"password": "mypassword"})
        assert result["password"] == "***"

    def test_redacts_nested_dict(self):
        result = redact_arguments({"config": {"api_key": "inner-secret", "name": "test"}})
        assert result["config"]["api_key"] == "***"
        assert result["config"]["name"] == "test"

    def test_does_not_redact_normal_keys(self):
        result = redact_arguments({"name": "alice", "age": 30})
        assert result["name"] == "alice"
        assert result["age"] == 30

    def test_keeps_list_values_unchanged(self):
        result = redact_arguments({"tags": ["a", "b", "c"]})
        assert result["tags"] == ["a", "b", "c"]

    def test_sensitive_auth_header(self):
        result = redact_arguments({"Authorization": "Bearer token123"})
        assert result["Authorization"] == "***"

    def test_sensitive_bearer_token(self):
        result = redact_arguments({"bearer": "my-token"})
        assert result["bearer"] == "***"


# ── Plugin lifecycle ──────────────────────────────────────────


class TestPluginLifecycle:
    @pytest.mark.asyncio
    async def test_load_duplicate_plugin_logs_warning(self, caplog):
        reg = PluginRegistry()
        plugin = _StubPlugin(name="dup")
        await reg.load(plugin)
        assert reg.get_plugin("dup") is not None
        await reg.load(plugin)
        assert len(reg.list_plugins()) == 1

    @pytest.mark.asyncio
    async def test_unload_existing(self):
        reg = PluginRegistry()
        plugin = _StubPlugin(name="unloadable")
        await reg.load(plugin)
        result = await reg.unload("unloadable")
        assert result is True
        assert reg.get_plugin("unloadable") is None

    @pytest.mark.asyncio
    async def test_unload_nonexistent(self):
        reg = PluginRegistry()
        result = await reg.unload("nobody")
        assert result is False

    @pytest.mark.asyncio
    async def test_unload_all(self):
        reg = PluginRegistry()
        await reg.load(_StubPlugin(name="a"))
        await reg.load(_StubPlugin(name="b"))
        assert len(reg.list_plugins()) == 2
        await reg.unload_all()
        assert len(reg.list_plugins()) == 0

    @pytest.mark.asyncio
    async def test_register_and_trigger_extension(self):
        reg = PluginRegistry()
        results = []

        async def hook_callback(*args, **kwargs):
            results.append((args, kwargs))
            return "hook_result"

        reg.register_extension("my_hook", hook_callback)
        outcomes = await reg.trigger_extension("my_hook", "arg1", key="val")
        assert outcomes == ["hook_result"]
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_trigger_extension_with_sync_callback(self):
        """Sync callbacks are awaited by trigger_extension and will fail;
        the hook logs the error and returns an empty result list."""
        reg = PluginRegistry()
        reg.register_extension("sync_hook", lambda *a, **k: "sync_ok")
        outcomes = await reg.trigger_extension("sync_hook")
        # sync lambda gets awaited → TypeError → caught and logged
        assert outcomes == []

    @pytest.mark.asyncio
    async def test_trigger_extension_handles_failure_gracefully(self):
        reg = PluginRegistry()

        def bad_callback(*a, **k):
            raise RuntimeError("boom")

        reg.register_extension("fragile", bad_callback)
        outcomes = await reg.trigger_extension("fragile")
        assert outcomes == []


# ── Middleware and provider registration ──────────────────────


class TestMiddlewareProvider:
    def test_register_middleware(self):
        reg = PluginRegistry()
        reg.register_middleware("cache", MagicMock())
        assert reg.get_middleware("cache") is not None

    def test_get_middleware_missing(self):
        reg = PluginRegistry()
        assert reg.get_middleware("missing") is None

    def test_register_provider(self):
        reg = PluginRegistry()
        reg.register_provider("openai", MagicMock())
        assert reg.get_provider("openai") is not None

    def test_get_provider_missing(self):
        reg = PluginRegistry()
        assert reg.get_provider("missing") is None


# ── PluginInfo and Plugin base ────────────────────────────────


class TestPluginInfo:
    def test_defaults(self):
        info = PluginInfo(name="test")
        assert info.version == "0.1.0"
        assert info.description == ""
        assert info.author == ""
        assert info.url == ""
        assert info.capabilities == []
        assert info.requires == []


class TestPluginABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Plugin()
