"""Portable synthetic tool for single-device transport tests; no file access."""

import asyncio
from pathlib import Path
import sys

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


async def listing(ctx, params):
    return types.ListToolsResult(tools=[types.Tool(
        name="probe", input_schema={"type": "object", "additionalProperties": False},
    )])


async def call(ctx, params):
    with Path(sys.argv[1]).open("a") as counter:
        counter.write("executed\n")
    return types.CallToolResult(content=[types.TextContent(type="text", text="LOCAL_PROBE_OK")])


async def main():
    server = Server("local-probe", on_list_tools=listing, on_call_tool=call)
    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())


asyncio.run(main())
