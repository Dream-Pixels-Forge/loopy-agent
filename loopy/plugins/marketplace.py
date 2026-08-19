"""
Marketplace Plugin — Discover and install plugins from PyPI.

Provides a registry for discovering, installing, and managing loopy plugins.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loopy.plugins import Plugin, PluginInfo, PluginRegistry

logger = logging.getLogger("loopy.plugins.marketplace")

# Known loopy plugins on PyPI
KNOWN_PLUGINS = {
    "loopy-rag": "loopy.plugins.rag",
    "loopy-tools": "loopy.plugins.tools",
    "loopy-memory": "loopy.plugins.memory",
    "loopy-audio": "loopy.plugins.audio",
    "loopy-anthropic": "loopy.plugins.anthropic",
    "loopy-openai": "loopy.plugins.openai",
    "loopy-ollama": "loopy.plugins.ollama",
}


@dataclass
class PluginPackage:
    """Information about an installable plugin package."""
    
    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    installed: bool = False
    latest_version: str = ""
    dependencies: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "installed": self.installed,
            "latest_version": self.latest_version,
        }


class PluginMarketplace:
    """
    Marketplace for discovering and installing loopy plugins.
    
    Example:
        marketplace = PluginMarketplace()
        
        # Search for plugins
        plugins = await marketplace.search("rag")
        
        # Install a plugin
        success = await marketplace.install("loopy-rag")
        
        # List installed plugins
        installed = marketplace.list_installed()
    """
    
    def __init__(self, registry: PluginRegistry | None = None):
        self.registry = registry or PluginRegistry()
        self._cache_path = Path.home() / ".loopy" / "marketplace_cache.json"
        self._cache: dict[str, PluginPackage] = {}
        self._load_cache()
    
    async def search(self, query: str) -> list[PluginPackage]:
        """
        Search for plugins matching the query.
        
        Args:
            query: Search query
        
        Returns:
            List of matching PluginPackage objects
        """
        # Check known plugins first
        results = []
        query_lower = query.lower()
        
        for name, module_path in KNOWN_PLUGINS.items():
            if query_lower in name.lower():
                package = PluginPackage(
                    name=name,
                    description=f"Loopy plugin: {name}",
                    installed=self._is_installed(module_path),
                )
                results.append(package)
        
        # Could also search PyPI API here
        # For now, return known plugins
        return results
    
    async def install(self, package_name: str, upgrade: bool = False) -> bool:
        """
        Install a plugin from PyPI (operator action).

        Only bare, PEP 508-style package names are accepted. URLs, ``git+``
        refs, local paths, and ``--`` option injection are rejected — ``pip
        install`` executes arbitrary build code, so the name must be
        strictly validated first.

        Args:
            package_name: Package name (e.g., "loopy-rag")
            upgrade: Whether to upgrade if already installed

        Returns:
            True if successful
        """
        if not self._validate_package_name(package_name):
            logger.error(
                "Refusing to install invalid package name: %r", package_name
            )
            return False

        try:
            cmd = [sys.executable, "-m", "pip", "install", package_name]
            if upgrade:
                cmd.append("--upgrade")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if result.returncode == 0:
                logger.info("Installed %s", package_name)
                self._update_cache(package_name, installed=True)
                return True
            else:
                logger.error("Failed to install %s: %s", package_name, result.stderr)
                return False
        except Exception as e:
            logger.error("Installation error: %s", e)
            return False

    @staticmethod
    def _validate_package_name(package_name: str) -> bool:
        """Reject anything that is not a bare, PEP 508-compatible package name.

        Blocks URLs, ``git+``/``hg+`` refs, local paths, and ``--`` option
        injection into ``pip install``.
        """
        if not package_name or len(package_name) > 214:
            return False
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", package_name):
            return False
        # Extra belt-and-suspenders: no scheme, path separators, dot-dot,
        # leading dashes, or option-looking prefixes.
        return not any(
            marker in package_name
            for marker in ("://", "git+", "hg+", "svn+", "\\", "/", "..")
        ) and not package_name.startswith("-")
    
    async def uninstall(self, package_name: str) -> bool:
        """
        Uninstall a plugin (operator action).

        The same strict name validation as :meth:`install` applies — only
        bare PEP 508 package names are accepted, so option injection
        (``--help``, ``--prefix=...``) cannot reach ``pip``.

        Args:
            package_name: Package name (e.g., "loopy-rag")

        Returns:
            True if successful
        """
        if not self._validate_package_name(package_name):
            logger.error(
                "Refusing to uninstall invalid package name: %r", package_name
            )
            return False

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "uninstall", "-y", package_name],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                logger.info("Uninstalled %s", package_name)
                self._update_cache(package_name, installed=False)
                return True
            else:
                logger.error("Failed to uninstall %s: %s", package_name, result.stderr)
                return False
        except Exception as e:
            logger.error("Uninstallation error: %s", e)
            return False
    
    def list_installed(self) -> list[PluginPackage]:
        """List all installed plugins."""
        installed = []
        
        for name, module_path in KNOWN_PLUGINS.items():
            if self._is_installed(module_path):
                package = PluginPackage(
                    name=name,
                    installed=True,
                )
                installed.append(package)
        
        return installed
    
    def list_available(self) -> list[PluginPackage]:
        """List all available plugins."""
        available = []
        
        for name, module_path in KNOWN_PLUGINS.items():
            package = PluginPackage(
                name=name,
                description=f"Loopy plugin: {name}",
                installed=self._is_installed(module_path),
            )
            available.append(package)
        
        return available
    
    def _is_installed(self, module_path: str) -> bool:
        """Check if a plugin module is importable."""
        try:
            __import__(module_path)
            return True
        except ImportError:
            return False
    
    def _load_cache(self) -> None:
        """Load marketplace cache."""
        if self._cache_path.exists():
            try:
                with open(self._cache_path) as f:
                    data = json.load(f)
                for name, info in data.items():
                    self._cache[name] = PluginPackage(**info)
            except Exception:
                pass
    
    def _save_cache(self) -> None:
        """Save marketplace cache."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            name: pkg.to_dict()
            for name, pkg in self._cache.items()
        }
        with open(self._cache_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _update_cache(self, name: str, installed: bool) -> None:
        """Update cache for a package."""
        if name in self._cache:
            self._cache[name].installed = installed
        else:
            self._cache[name] = PluginPackage(name=name, installed=installed)
        self._save_cache()


class MarketplacePlugin(Plugin):
    """
    Marketplace plugin for discovering and installing other plugins.
    
    Example:
        plugin = MarketplacePlugin()
        await registry.load(plugin)
        marketplace = plugin.marketplace
        plugins = await marketplace.search("rag")
    """
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="loopy-marketplace",
            version="0.4.0",
            description="Plugin marketplace for loopy",
            author="Dream Pixels Forge",
            capabilities=["tool", "marketplace"],
            requires=[],
        )
    
    async def setup(self, registry: PluginRegistry) -> None:
        """Initialize the Marketplace plugin."""
        self.marketplace = PluginMarketplace(registry)
        
        # Register read-only, discovery tools only (agent-visible).
        # NOTE: 'install_plugin' is deliberately NOT registered as an agent
        # tool — installing packages executes arbitrary code (setup.py/build
        # hooks) and is an operator action, never a model capability.
        # Operators can call marketplace.install() directly.
        registry.register_tool("search_plugins", self._search_plugins, scope="read_only")
        registry.register_tool("list_plugins", self._list_plugins, scope="read_only")
        
        logger.info("Marketplace plugin initialized")
    
    async def _search_plugins(self, query: str) -> list[dict[str, Any]]:
        """Search for plugins."""
        plugins = await self.marketplace.search(query)
        return [p.to_dict() for p in plugins]
    
    async def _install_plugin(self, package_name: str) -> dict[str, Any]:
        """Install a plugin."""
        success = await self.marketplace.install(package_name)
        return {
            "package": package_name,
            "success": success,
            "message": f"{'Installed' if success else 'Failed to install'} {package_name}",
        }
    
    async def _list_plugins(self, installed_only: bool = False) -> list[dict[str, Any]]:
        """List plugins."""
        if installed_only:
            plugins = self.marketplace.list_installed()
        else:
            plugins = self.marketplace.list_available()
        return [p.to_dict() for p in plugins]
