# `loopy.mcp` — Model Context Protocol client

Connect to any MCP server (stdio or HTTP+SSE) and surface its tools as
`MCPToolResult` objects. Capability gates reject dangerous operations
before they reach the server.

## Quickstart

```python
import asyncio
from loopy import MCPClient, MCPToolResult

async def main():
    async with MCPClient(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    ) as client:
        tools = await client.list_tools()
        result: MCPToolResult = await client.call_tool(
            "read_file",
            {"path": "/tmp/hello.txt"},
        )
        print(result.content)

asyncio.run(main())
```

## API

| Symbol | Purpose |
|---|---|
| `MCPClient` | Async context manager for MCP servers |
| `MCPToolResult` | Result envelope (content / error) |
| `LocalMCP` | In-process MCP server (for tests) |