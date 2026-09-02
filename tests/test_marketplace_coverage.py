"""Coverage tests for loopy.plugins.marketplace — install/uninstall validation,
cache load/save/update, and the MarketplacePlugin tool surface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loopy.plugins.marketplace import (
    KNOWN_PLUGINS,
    MarketplacePlugin,
    PluginMarketplace,
    PluginPackage,
)

# ---------------------------------------------------------------------------
# PluginPackage
# ---------------------------------------------------------------------------


class TestPluginPackage:
    def test_to_dict(self):
        pkg = PluginPackage(
            name="loopy-rag",
            version="1.0.0",
            description="RAG plugin",
            author="Test",
            installed=True,
            latest_version="1.2.0",
        )
        d = pkg.to_dict()
        assert d["name"] == "loopy-rag"
        assert d["version"] == "1.0.0"
        assert d["installed"] is True
        # Dependencies intentionally excluded from to_dict output
        assert "dependencies" not in d


# ---------------------------------------------------------------------------
# PluginMarketplace — validation, install/uninstall, cache
# ---------------------------------------------------------------------------


class TestValidatePackageName:
    @pytest.mark.parametrize(
        "name",
        [
            "loopy-rag",
            "loopy_rag",
            "loopy.rag",
            "loopy-rag-extra-1",
            "A",
            "a1",
        ],
    )
    def test_accepts_valid_names(self, name):
        assert PluginMarketplace._validate_package_name(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "",  # empty
            " " * 5,  # whitespace
            "loopy rag",  # space
            "-leading-dash",  # leading dash (pip option)
            "git+https://github.com/x/y",  # scheme
            "https://evil.example/x",  # URL
            "name/with/path",  # path separator
            "name\\with\\path",  # backslash
            "../relative",  # dot-dot
            "a" * 215,  # too long
            "git+",  # prefix
            "hg+",  # prefix
            "svn+",  # prefix
            "rm -rf /",  # space + extra
            "name;rm",  # shell metachar
        ],
    )
    def test_rejects_invalid_names(self, name):
        assert PluginMarketplace._validate_package_name(name) is False


class TestInstall:
    @pytest.mark.asyncio
    async def test_install_success(self):
        mp = PluginMarketplace()
        with patch("loopy.plugins.marketplace.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            ok = await mp.install("loopy-rag")
        assert ok is True
        assert mock_run.called
        args = mock_run.call_args[0][0]
        # pip install called with bare package name only — no option injection
        assert args[0:3] == [sys.executable, "-m", "pip"]
        assert args[3] == "install"
        assert args[-1] == "loopy-rag"

    @pytest.mark.asyncio
    async def test_install_upgrade_flag(self):
        mp = PluginMarketplace()
        with patch("loopy.plugins.marketplace.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            await mp.install("loopy-rag", upgrade=True)
        args = mock_run.call_args[0][0]
        assert "--upgrade" in args

    @pytest.mark.asyncio
    async def test_install_failure(self):
        mp = PluginMarketplace()
        with patch("loopy.plugins.marketplace.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="boom")
            ok = await mp.install("loopy-rag")
        assert ok is False

    @pytest.mark.asyncio
    async def test_install_invalid_name_rejected(self):
        """Invalid package names are rejected before subprocess.run is called."""
        mp = PluginMarketplace()
        with patch("loopy.plugins.marketplace.subprocess.run") as mock_run:
            ok = await mp.install("git+https://evil/x")
        assert ok is False
        assert not mock_run.called

    @pytest.mark.asyncio
    async def test_install_subprocess_exception(self):
        mp = PluginMarketplace()
        with patch(
            "loopy.plugins.marketplace.subprocess.run",
            side_effect=OSError("no pip"),
        ):
            ok = await mp.install("loopy-rag")
        assert ok is False


class TestUninstall:
    @pytest.mark.asyncio
    async def test_uninstall_success(self):
        mp = PluginMarketplace()
        with patch("loopy.plugins.marketplace.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            ok = await mp.uninstall("loopy-rag")
        assert ok is True
        args = mock_run.call_args[0][0]
        assert args[3] == "uninstall"
        assert "-y" in args
        assert args[-1] == "loopy-rag"

    @pytest.mark.asyncio
    async def test_uninstall_failure(self):
        mp = PluginMarketplace()
        with patch("loopy.plugins.marketplace.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="nope")
            ok = await mp.uninstall("loopy-rag")
        assert ok is False

    @pytest.mark.asyncio
    async def test_uninstall_invalid_name_rejected(self):
        mp = PluginMarketplace()
        with patch("loopy.plugins.marketplace.subprocess.run") as mock_run:
            ok = await mp.uninstall("--help")
        assert ok is False
        assert not mock_run.called

    @pytest.mark.asyncio
    async def test_uninstall_subprocess_exception(self):
        mp = PluginMarketplace()
        with patch(
            "loopy.plugins.marketplace.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pip", 60),
        ):
            ok = await mp.uninstall("loopy-rag")
        assert ok is False


class TestCacheIO:
    def test_load_cache_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mp = PluginMarketplace()
        assert mp._cache == {}

    def test_save_then_load_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mp1 = PluginMarketplace()
        mp1._cache["loopy-rag"] = PluginPackage(name="loopy-rag", installed=True)
        mp1._save_cache()

        cache_file = tmp_path / ".loopy" / "marketplace_cache.json"
        assert cache_file.exists()

        # Force a fresh load from disk
        mp2 = PluginMarketplace()
        assert "loopy-rag" in mp2._cache
        assert mp2._cache["loopy-rag"].installed is True

    def test_load_cache_corrupt_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        cache_file = tmp_path / ".loopy" / "marketplace_cache.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("not valid json {")

        # Should swallow exception and leave cache empty
        mp = PluginMarketplace()
        assert mp._cache == {}

    def test_update_cache_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mp = PluginMarketplace()
        mp._cache["loopy-rag"] = PluginPackage(name="loopy-rag", installed=False)
        mp._update_cache("loopy-rag", installed=True)
        assert mp._cache["loopy-rag"].installed is True

    def test_update_cache_new(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mp = PluginMarketplace()
        assert "loopy-rag" not in mp._cache
        mp._update_cache("loopy-rag", installed=True)
        assert "loopy-rag" in mp._cache
        assert mp._cache["loopy-rag"].installed is True


class TestListHelpers:
    def test_list_installed_filters_by_importability(self):
        mp = PluginMarketplace()
        # Importability depends on which optional modules are present in env;
        # we just assert the call returns PluginPackage instances.
        installed = mp.list_installed()
        assert all(isinstance(p, PluginPackage) for p in installed)
        # All returned items must be marked installed.
        assert all(p.installed for p in installed)

    def test_list_available_marks_installed_flag(self):
        mp = PluginMarketplace()
        available = mp.list_available()
        names = {p.name for p in available}
        # KNOWN_PLUGINS is the source of truth — must match.
        assert names == set(KNOWN_PLUGINS.keys())


# ---------------------------------------------------------------------------
# MarketplacePlugin (Plugin subclass)
# ---------------------------------------------------------------------------


class TestMarketplacePlugin:
    def test_info_metadata(self):
        plugin = MarketplacePlugin()
        info = plugin.info
        assert info.name == "loopy-marketplace"
        assert "marketplace" in info.capabilities
        assert "tool" in info.capabilities

    @pytest.mark.asyncio
    async def test_setup_registers_only_read_only_tools(self):
        plugin = MarketplacePlugin()
        registry = MagicMock()
        registry.register_tool = MagicMock()

        await plugin.setup(registry)

        # Only read-only tools are registered (install_plugin deliberately omitted).
        names = [c.args[0] for c in registry.register_tool.call_args_list]
        assert "search_plugins" in names
        assert "list_plugins" in names
        assert "install_plugin" not in names

        # All registered as read_only scope.
        scopes = [c.kwargs.get("scope") for c in registry.register_tool.call_args_list]
        assert all(s == "read_only" for s in scopes)

    @pytest.mark.asyncio
    async def test_search_plugins_tool(self):
        plugin = MarketplacePlugin()
        registry = MagicMock()
        await plugin.setup(registry)

        results = await plugin._search_plugins("rag")
        assert isinstance(results, list)
        assert any(r["name"] == "loopy-rag" for r in results)

    @pytest.mark.asyncio
    async def test_list_plugins_tool_installed_only(self):
        plugin = MarketplacePlugin()
        registry = MagicMock()
        await plugin.setup(registry)

        results = await plugin._list_plugins(installed_only=True)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_list_plugins_tool_all(self):
        plugin = MarketplacePlugin()
        registry = MagicMock()
        await plugin.setup(registry)

        results = await plugin._list_plugins(installed_only=False)
        assert len(results) == len(KNOWN_PLUGINS)

    @pytest.mark.asyncio
    async def test_install_plugin_helper(self):
        plugin = MarketplacePlugin()
        registry = MagicMock()
        await plugin.setup(registry)

        with patch.object(plugin.marketplace, "install", new=AsyncMock(return_value=True)):
            result = await plugin._install_plugin("loopy-rag")
        assert result["success"] is True
        assert result["package"] == "loopy-rag"
