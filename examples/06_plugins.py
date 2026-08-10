"""
Example 6: Plugin System

Demonstrates using first-party plugins (RAG, Tools, Memory).
"""

import asyncio

from loopy import Plugin, PluginRegistry
from loopy.plugins.memory import Memory, MemoryStore
from loopy.plugins.rag import Document, Retriever
from loopy.plugins.tools import Tool, ToolParameter, ToolsPlugin


async def main():
    # ============================================
    # Example 1: RAG Plugin
    # ============================================
    print("=== Example 1: RAG Plugin ===")
    
    retriever = Retriever()
    
    # Add documents
    documents = [
        "Python is a high-level programming language known for its simplicity.",
        "JavaScript is the language of the web, used for both frontend and backend.",
        "Rust is a systems programming language focused on safety and performance.",
        "Go is a simple and efficient language built for concurrency.",
        "TypeScript adds static typing to JavaScript for better tooling.",
    ]
    
    for doc_text in documents:
        retriever.add(Document.from_text(doc_text))
    
    # Search
    results = await retriever.search("programming language", top_k=3)
    
    print("Search results for 'programming language':")
    for r in results:
        print(f"  {r.rank}. (score: {r.score:.3f}) {r.document.content[:60]}...")
    print()
    
    # ============================================
    # Example 2: Tools Plugin
    # ============================================
    print("=== Example 2: Tools Plugin ===")
    
    tools_registry = PluginRegistry()
    tools_plugin = ToolsPlugin()
    await tools_plugin.setup(tools_registry)
    
    # Register a custom tool
    async def get_weather(city: str) -> dict:
        """Get weather for a city."""
        # Simulated weather data
        weather_data = {
            "Portland": {"temp": 72, "condition": "Cloudy"},
            "Seattle": {"temp": 65, "condition": "Rainy"},
            "San Francisco": {"temp": 68, "condition": "Foggy"},
        }
        return weather_data.get(city, {"temp": 70, "condition": "Unknown"})
    
    tools_plugin.tool_registry.register(Tool(
        name="get_weather",
        description="Get current weather for a city",
        handler=get_weather,
        parameters=[
            ToolParameter(name="city", type="string", description="City name"),
        ],
    ))
    
    # List tools
    tools = await tools_plugin._list_tools()
    print("Available tools:")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")
    print()
    
    # Execute tools
    result = await tools_plugin._execute_tool("calculator", {"expression": "2 + 2"})
    print(f"Calculator result: {result['output']}")
    
    result = await tools_plugin._execute_tool("get_weather", {"city": "Portland"})
    print(f"Weather in Portland: {result['output']}")
    print()
    
    # ============================================
    # Example 3: Memory Plugin
    # ============================================
    print("=== Example 3: Memory Plugin ===")
    
    import os
    import tempfile
    
    # Create temporary memory store
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name
    
    try:
        store = MemoryStore(storage_path=temp_path)
        
        # Store memories
        memories_to_store = [
            Memory(
                id="user_pref_1",
                content="User prefers dark mode in applications",
                category="preferences",
                importance=0.8,
            ),
            Memory(
                id="user_pref_2",
                content="User likes concise responses",
                category="preferences",
                importance=0.7,
            ),
            Memory(
                id="user_fact_1",
                content="User is a Python developer",
                category="facts",
                importance=0.9,
            ),
            Memory(
                id="user_fact_2",
                content="User works on AI/ML projects",
                category="facts",
                importance=0.85,
            ),
        ]
        
        for memory in memories_to_store:
            store.add(memory)
        
        print(f"Stored {len(memories_to_store)} memories")
        
        # Recall memories
        results = store.recall("developer preferences", top_k=3)
        print("\nRecalled memories for 'developer preferences':")
        for m in results:
            print(f"  - [{m.category}] (importance: {m.importance}) {m.content}")
        
        # List by category
        prefs = store.list_all(category="preferences")
        print(f"\nAll preference memories: {len(prefs)}")
        
        facts = store.list_all(category="facts")
        print(f"All fact memories: {len(facts)}")
        
        # Get summary
        summary = store.get_summary()
        print("\nMemory store summary:")
        print(f"  Total memories: {summary['total_memories']}")
        print(f"  Categories: {summary['categories']}")
        print(f"  Avg importance: {summary['avg_importance']:.2f}")
        
    finally:
        os.unlink(temp_path)
    
    print()
    
    # ============================================
    # Example 4: Custom Plugin
    # ============================================
    print("=== Example 4: Custom Plugin ===")
    
    from loopy import PluginInfo
    
    class CounterPlugin(Plugin):
        """Simple counter plugin example."""
        
        def __init__(self):
            self.count = 0
        
        @property
        def info(self) -> PluginInfo:
            return PluginInfo(
                name="counter",
                version="1.0.0",
                description="Simple counter plugin",
                capabilities=["tool"],
            )
        
        async def setup(self, registry: PluginRegistry) -> None:
            registry.register_tool("increment", self.increment)
            registry.register_tool("get_count", self.get_count)
        
        async def increment(self, amount: int = 1) -> dict:
            self.count += amount
            return {"count": self.count}
        
        async def get_count(self) -> dict:
            return {"count": self.count}
    
    # Load and use custom plugin
    registry = PluginRegistry()
    counter = CounterPlugin()
    await registry.load(counter)
    
    # Use the tools
    increment = registry.get_tool("increment")
    get_count = registry.get_tool("get_count")
    
    await increment(5)
    await increment(3)
    result = await get_count()
    print(f"Counter value: {result['count']}")
    
    # List loaded plugins
    plugins = registry.list_plugins()
    print(f"Loaded plugins: {[p.name for p in plugins]}")


if __name__ == "__main__":
    asyncio.run(main())
