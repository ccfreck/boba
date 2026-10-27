"""Policy-permissive, OS-confined demo. All credentials are fictional.

POSIX descriptor-relative traversal prevents symlink swaps from escaping the
sandbox. The gateway deliberately has a separate path validation implementation.
"""

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


def open_sandbox(root: Path, value: str, directory: bool = False) -> int:
    path = Path(value)
    if path.is_absolute():
        path = path.relative_to(root)
    if ".." in path.parts or "\\" in value or "\x00" in value:
        raise ValueError("Invalid sandbox path")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = path.parts
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 1 or directory:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


async def serve(root: Path, counter: Path | None) -> None:
    import stat

    schema: dict[str, Any] = {
        "type": "object", "properties": {"path": {"type": "string"}},
        "required": ["path"], "additionalProperties": False,
    }
    tools = [types.Tool(name=name, description=description, input_schema=schema)
             for name, description in [
                 ("read_file", "Read a UTF-8 file inside the demo sandbox."),
                 ("list_directory", "List names inside the demo sandbox."),
             ]]

    async def list_tools(ctx: ServerRequestContext, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
        # This records handler entry, before validation or file access.
        if counter:
            with counter.open("a", encoding="utf-8") as stream:
                stream.write("executed\n")
        try:
            if params.name not in {tool.name for tool in tools}:
                raise ValueError("Unknown tool")
            args = params.arguments or {}
            if set(args) != {"path"} or not isinstance(args["path"], str):
                raise ValueError("Invalid arguments")
            fd = open_sandbox(root, args["path"], params.name == "list_directory")
            try:
                if params.name == "list_directory":
                    result = "\n".join(sorted(os.listdir(fd)))
                else:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise ValueError("Not a regular file")
                    result = os.read(fd, 65537).decode("utf-8")
                    if len(result.encode("utf-8")) > 65536:
                        raise ValueError("File too large")
            finally:
                os.close(fd)
            return types.CallToolResult(content=[types.TextContent(type="text", text=result)])
        except (OSError, ValueError, UnicodeError):
            return types.CallToolResult(is_error=True, content=[types.TextContent(type="text", text="Demo sandbox rejected request")])

    server = Server("boba-demo", on_list_tools=list_tools, on_call_tool=call_tool)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parent / "safe_files")
    parser.add_argument("--counter", type=Path)
    options = parser.parse_args()
    asyncio.run(serve(options.root.resolve(strict=True), options.counter))
