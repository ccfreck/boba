from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def test_real_demo_discovery_and_execution(tmp_path: Path) -> None:
    counter = tmp_path / "counter"
    params = StdioServerParameters(command=sys.executable, args=[
        str(ROOT / "demo/vulnerable_server.py"), "--counter", str(counter),
    ])
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as client:
            await client.initialize()
            listing = await client.list_tools()
            assert {tool.name for tool in listing.tools} == {"read_file", "list_directory"}
            assert listing.tools[0].input_schema["required"] == ["path"]
            result = await client.call_tool("read_file", {"path": "hello.txt"})
            assert not result.is_error
            assert "Hello from Boba" in result.content[0].text
            fake = await client.call_tool("read_file", {"path": ".aws/credentials"})
            assert not fake.is_error  # Direct access is deliberately policy-permissive.
            escaped = await client.call_tool("read_file", {"path": "../../pyproject.toml"})
            assert escaped.is_error
    assert counter.read_text().splitlines() == ["executed"] * 3
