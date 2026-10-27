"""Real MCP peer used only to test transport failures."""

import asyncio
import os
import sys

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


async def listing(ctx: ServerRequestContext, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(name="probe", input_schema={"type": "object"})])


async def call(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    if sys.argv[1] == "disconnect":
        os._exit(1)
    await asyncio.sleep(60)
    return types.CallToolResult(content=[])


async def main() -> None:
    server = Server("failure-fixture", on_list_tools=listing, on_call_tool=call)
    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())


asyncio.run(main())
