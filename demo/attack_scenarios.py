"""Run real attacks through Boba and verify the downstream execution counter."""

import asyncio
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import yaml


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix="boba-demo-") as directory:
        work = Path(directory)
        counter = work / "counter"
        config = yaml.safe_load((root / "config/boba.yaml").read_text())
        config["policy"] = str(root / "config/policies.yaml")
        config["database"] = str(root / "events.db")
        config["downstream"]["cwd"] = str(root)
        config["downstream"]["args"] += ["--counter", str(counter)]
        config_path = work / "boba.yaml"
        config_path.write_text(yaml.safe_dump(config))
        params = StdioServerParameters(command=sys.executable, args=["-m", "boba.main", "--config", str(config_path)])
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                scenarios = [("read_file", {"path": path}) for path in [
                    ".aws/credentials", ".env", ".env.production", "secrets/example.txt", "../outside.txt",
                ]] + [("run_shell", {"command": "not executed"}), ("unknown", {}), ("read_file", {"path": 123})]
                for index, (name, arguments) in enumerate(scenarios, start=1):
                    result = await client.call_tool(name, arguments)
                    assert result.is_error and not counter.exists(), "Enforcement failed"
                    print(f"Scenario {index}: BLOCK; downstream executions: 0")
                result = await client.call_tool("read_file", {"path": "hello.txt"})
                assert not result.is_error and counter.read_text().splitlines() == ["executed"]
                print("Safe read: ALLOW; downstream executions: 1")
                for _ in range(31):
                    assert not (await client.call_tool("read_file", {"path": "hello.txt"})).is_error
        with sqlite3.connect(root / "events.db") as db:
            alerts = db.execute("SELECT COUNT(*) FROM events WHERE alerts != '[]'").fetchone()[0]
        print(f"Stored alert-bearing events: {alerts}; open the dashboard to inspect events.db")


if __name__ == "__main__":
    asyncio.run(main())
