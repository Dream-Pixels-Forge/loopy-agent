"""
Plugin System — Extensible architecture for loopy.

Base classes and first-party plugins:
- RAG: Retrieval-Augmented Generation
- Tools: Tool-use with function calling
- Memory: Long-term agent memory
"""

from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("loopy.plugins")


@dataclass
class PluginInfo:
    """Metadata about a plugin."""
    
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    url: str = ""
    
    # Capabilities this plugin provides
    capabilities: list[str] = field(default_factory=list)
    
    # Dependencies
    requires: list[str] = field(default_factory=list)


class Plugin(ABC):
    """
    Base plugin class.
    
    All plugins must inherit from this and implement `setup()`.
    
    Example:
        class MyPlugin(Plugin):
            @property
            def info(self) -> PluginInfo:
                return PluginInfo(
                    name="my-plugin",
                    version="1.0.0",
                    description="My awesome plugin",
                )
            
            async def setup(self, registry: PluginRegistry) -> None:
                # Register tools, middleware, etc.
                registry.register_tool("my_tool", my_tool_handler)
    """
    
    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Return plugin metadata."""
        ...
    
    @abstractmethod
    async def setup(self, registry: PluginRegistry) -> None:
        """Initialize the plugin."""
        ...
    
    async def teardown(self) -> None:  # noqa: B027
        """Cleanup when plugin is unloaded."""
        ...


class PluginRegistry:
    """
    Central registry for plugins and their components.
    
    Example:
        registry = PluginRegistry()
        
        # Load plugins
        await registry.load(MyPlugin())
        await registry.load_package("loopy.plugins.anthropic")
        
        # Use registered components
        tool = registry.get_tool("my_tool")
        middleware = registry.get_middleware("cache")
    """

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._tools: dict[str, Callable] = {}
        self._middleware: dict[str, Any] = {}
        self._providers: dict[str, Any] = {}
        self._extensions: dict[str, list[Callable]] = {}

    async def load(self, plugin: Plugin) -> None:
        """Load a plugin instance."""
        info = plugin.info
        
        if info.name in self._plugins:
            logger.warning(f"Plugin {info.name} already loaded, skipping")
            return
        
        # Check dependencies
        for dep in info.requires:
            if dep not in self._plugins:
                raise RuntimeError(
                    f"Plugin {info.name} requires {dep}, which is not loaded"
                )
        
        # Load the plugin
        await plugin.setup(self)
        self._plugins[info.name] = plugin
        
        logger.info(f"Loaded plugin: {info.name} v{info.version}")

    async def load_package(self, module_path: str) -> None:
        """
        Load a plugin from a Python module path.
        
        The module must have a `plugin` attribute that is a Plugin instance.
        
        Example:
            await registry.load_package("my_package.my_plugin")
        """
        try:
            module = importlib.import_module(module_path)
            plugin_instance = getattr(module, "plugin", None)
            
            if plugin_instance is None:
                raise ValueError(f"No 'plugin' attribute in {module_path}")
            
            if not isinstance(plugin_instance, Plugin):
                raise TypeError(f"'plugin' in {module_path} is not a Plugin instance")
            
            await self.load(plugin_instance)
            
        except ImportError as e:
            logger.error(f"Failed to import {module_path}: {e}")
            raise

    async def load_directory(self, directory: str | Path) -> int:
        """
        Load all plugins from a directory.
        
        Looks for Python files with a `plugin` attribute.
        
        Returns:
            Number of plugins loaded
        """
        directory = Path(directory)
        loaded = 0
        
        if not directory.exists():
            logger.warning(f"Plugin directory not found: {directory}")
            return 0
        
        for py_file in directory.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            module_name = py_file.stem
            try:
                spec = importlib.util.spec_from_file_location(
                    f"loopy_plugins.{module_name}",
                    py_file,
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    plugin_instance = getattr(module, "plugin", None)
                    if plugin_instance and isinstance(plugin_instance, Plugin):
                        await self.load(plugin_instance)
                        loaded += 1
            except Exception as e:
                logger.error(f"Failed to load plugin from {py_file}: {e}")
        
        return loaded

    def register_tool(self, name: str, handler: Callable) -> None:
        """Register a tool handler."""
        self._tools[name] = handler
        logger.debug(f"Registered tool: {name}")

    def get_tool(self, name: str) -> Callable | None:
        """Get a registered tool."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tools."""
        return list(self._tools.keys())

    def register_middleware(self, name: str, middleware: Any) -> None:
        """Register middleware."""
        self._middleware[name] = middleware
        logger.debug(f"Registered middleware: {name}")

    def get_middleware(self, name: str) -> Any:
        """Get registered middleware."""
        return self._middleware.get(name)

    def register_provider(self, name: str, provider: Any) -> None:
        """Register an LLM provider."""
        self._providers[name] = provider
        logger.debug(f"Registered provider: {name}")

    def get_provider(self, name: str) -> Any:
        """Get a registered provider."""
        return self._providers.get(name)

    def register_extension(self, hook_name: str, callback: Callable) -> None:
        """Register an extension hook."""
        if hook_name not in self._extensions:
            self._extensions[hook_name] = []
        self._extensions[hook_name].append(callback)
        logger.debug(f"Registered extension for hook: {hook_name}")

    async def trigger_extension(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Trigger all callbacks for a hook."""
        results = []
        for callback in self._extensions.get(hook_name, []):
            try:
                if callable(callback):
                    result = await callback(*args, **kwargs)
                else:
                    result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Extension hook {hook_name} failed: {e}")
        return results

    def get_plugin(self, name: str) -> Plugin | None:
        """Get a loaded plugin."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        """List all loaded plugins."""
        return [p.info for p in self._plugins.values()]

    async def unload(self, name: str) -> bool:
        """Unload a plugin."""
        if name not in self._plugins:
            return False
        
        plugin = self._plugins[name]
        await plugin.teardown()
        del self._plugins[name]
        
        logger.info(f"Unloaded plugin: {name}")
        return True

    async def unload_all(self) -> None:
        """Unload all plugins."""
        for name in list(self._plugins.keys()):
            await self.unload(name)


# ============================================================
# Plugin Loader - discovers and loads plugins automatically
# ============================================================

class PluginLoader:
    """
    Automatic plugin discovery and loading.
    
    Example:
        loader = PluginLoader()
        
        # Discover plugins from entry points
        await loader.discover()
        
        # Or from specific locations
        await loader.discover(
            package="my_package.plugins",
            directory="~/.loopy/plugins",
        )
    """

    def __init__(self, registry: PluginRegistry | None = None):
        self.registry = registry or PluginRegistry()

    async def discover(
        self,
        package: str | None = None,
        directory: str | Path | None = None,
    ) -> int:
        """
        Discover and load plugins.
        
        Returns:
            Number of plugins loaded
        """
        loaded = 0

        # Load from package
        if package:
            try:
                mod = importlib.import_module(package)
                plugins_attr = getattr(mod, "__plugins__", [])
                for plugin_cls in plugins_attr:
                    if isinstance(plugin_cls, type) and issubclass(plugin_cls, Plugin):
                        await self.registry.load(plugin_cls())
                        loaded += 1
            except ImportError as e:
                logger.warning(f"Could not import {package}: {e}")

        # Load from directory
        if directory:
            loaded += await self.registry.load_directory(directory)

        return loaded


# ============================================================
# First-party plugins
# ============================================================

def lazy_import_rag():
    from loopy.plugins.rag import Document, RAGPlugin, Retriever
    return RAGPlugin, Document, Retriever

def lazy_import_tools():
    from loopy.plugins.tools import Tool, ToolResult, ToolsPlugin
    return ToolsPlugin, Tool, ToolResult

def lazy_import_memory():
    from loopy.plugins.memory import Memory, MemoryPlugin, MemoryStore
    return MemoryPlugin, Memory, MemoryStore

def lazy_import_audio():
    from loopy.plugins.audio import AudioPlugin, SpeechToText, TextToSpeech
    return AudioPlugin, SpeechToText, TextToSpeech

def lazy_import_marketplace():
    from loopy.plugins.marketplace import MarketplacePlugin, PluginMarketplace
    return MarketplacePlugin, PluginMarketplace


# Public exports
__all__ = [
    # Base classes
    "Plugin",
    "PluginInfo",
    "PluginRegistry",
    "PluginLoader",
    # Lazy import functions
    "lazy_import_rag",
    "lazy_import_tools",
    "lazy_import_memory",
    "lazy_import_audio",
    "lazy_import_marketplace",
]
