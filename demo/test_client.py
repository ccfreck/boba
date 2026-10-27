"""Real MCP client: --direct bypasses Boba inside the safe demo sandbox."""

import argparse
import asyncio
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(direct: bool, config: str, path: str) -> None:
    root = Path(__file__).resolve().parents[1]
    args = [str(root / "demo/vulnerable_server.py")] if direct else ["-m", "boba.main", "--config", config]
    async with stdio_client(StdioServerParameters(command=sys.executable, args=args)) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = await client.list_tools()
            print("Tools:", ", ".join(tool.name for tool in tools.tools))
            result = await client.call_tool("read_file", {"path": path})
            print(result.model_dump_json(by_alias=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--config", default="config/boba.yaml")
    parser.add_argument("--path", default="hello.txt")
    options = parser.parse_args()
    asyncio.run(run(options.direct, options.config, options.path))
