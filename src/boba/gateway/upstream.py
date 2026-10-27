"""The sole downstream transport adapter (local stdio for v0.1)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from boba.config import Downstream


@asynccontextmanager
async def connect(config: Downstream, base: Path) -> AsyncIterator[ClientSession]:
    parameters = StdioServerParameters(
        command=sys.executable if config.command == "@python" else config.command,
        args=config.args, cwd=(base / config.cwd).resolve(),
    )
    # A downstream can write secrets to stderr; do not route it into Boba's logs.
    with open(os.devnull, "w") as errors:
        async with stdio_client(parameters, errlog=errors) as streams:
            async with ClientSession(*streams, read_timeout_seconds=config.timeout_seconds) as client:
                await client.initialize()
                yield client


async def discover(client: ClientSession) -> list[types.Tool]:
    tools: list[types.Tool] = []
    cursor: str | None = None
    seen: set[str] = set()
    for _ in range(100):
        result = await client.list_tools(params=types.PaginatedRequestParams(cursor=cursor) if cursor else None)
        tools.extend(result.tools)
        if len(tools) > 1000:
            raise ValueError("Downstream tool limit exceeded")
        cursor = result.next_cursor
        if not cursor:
            return tools
        if cursor in seen:
            raise ValueError("Repeated tool discovery cursor")
        seen.add(cursor)
    raise ValueError("Downstream discovery page limit exceeded")
