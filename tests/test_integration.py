from pathlib import Path
import sqlite3
import sys
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[1]


async def test_real_gateway_blocks_before_downstream_execution(tmp_path: Path, sandbox: Path) -> None:
    counter = tmp_path / "counter"
    database = tmp_path / "events.db"
    policy = tmp_path / "policies.yaml"
    policy.write_text(yaml.safe_dump({
        "version": 1, "defaults": {"action": "block"}, "servers": {"demo": {
            "allowed_tools": ["read_file", "list_directory"], "approved_roots": [str(sandbox)],
            "path_arguments": {"read_file": ["path"], "list_directory": ["path"]},
        }}, "rules": [{"id": "RATE", "name": "Rate", "action": "alert", "threshold": 3, "window_seconds": 60}],
    }))
    config = tmp_path / "boba.yaml"
    config.write_text(yaml.safe_dump({
        "version": 1, "policy": str(policy), "database": str(database), "downstream": {
            "name": "demo", "command": sys.executable, "cwd": str(ROOT),
            "args": [str(ROOT / "demo/vulnerable_server.py"), "--root", str(sandbox), "--counter", str(counter)],
        },
    }))
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET")
    (sandbox / "escape").symlink_to(outside)
    params = StdioServerParameters(command=sys.executable, args=["-m", "boba.main", "--config", str(config)])
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as client:
            await client.initialize()
            tools = (await client.list_tools()).tools
            assert {tool.name for tool in tools} == {"read_file", "list_directory"}
            assert tools[0].input_schema == {
                "type": "object", "properties": {"path": {"type": "string"}},
                "required": ["path"], "additionalProperties": False,
            }
            attempts = [("read_file", {"path": path}) for path in
                        (".aws/credentials", ".env", ".env.production", "../outside.txt", "escape", ".ssh/id_rsa", "secrets/key")]
            attempts += [("unknown", {}), ("run_shell", {"command": "not executed"}), ("read_file", {"path": 42})]
            for name, args in attempts:
                result = await client.call_tool(name, args)
                assert result.is_error
                assert not counter.exists(), "Denied request entered downstream handler"
            allowed = await client.call_tool("read_file", {"path": "hello.txt"})
            assert not allowed.is_error and allowed.content[0].text == "hello"
            assert counter.read_text().splitlines() == ["executed"]
    with sqlite3.connect(database) as db:
        rows = db.execute("SELECT decision, outcome, alerts FROM events").fetchall()
    assert len(rows) == 11
    assert sum(row[0] == "block" for row in rows) == 10
    assert rows[-1][1] == "success"
    assert rows[-1][2] == '["RATE"]'


@pytest.mark.parametrize("mode", ["timeout", "disconnect"])
async def test_real_downstream_failure(tmp_path: Path, mode: str) -> None:
    policy = tmp_path / "policies.yaml"
    policy.write_text(yaml.safe_dump({
        "version": 1, "defaults": {"action": "block"}, "servers": {"failure": {
            "allowed_tools": ["probe"], "approved_roots": [str(tmp_path)], "path_arguments": {"probe": []},
        }},
    }))
    database = tmp_path / "events.db"
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({
        "version": 1, "policy": str(policy), "database": str(database), "downstream": {
            "name": "failure", "command": sys.executable, "cwd": str(ROOT), "timeout_seconds": 1.0,
            "args": [str(ROOT / "tests/fixtures/failing_server.py"), mode],
        },
    }))
    params = StdioServerParameters(command=sys.executable, args=["-m", "boba.main", "--config", str(config)])
    async with stdio_client(params) as streams:
        async with ClientSession(*streams, read_timeout_seconds=10) as client:
            await client.initialize()
            result = await client.call_tool("probe", {})
            assert result.is_error
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT decision, outcome FROM events").fetchone() == ("allow", "error")


async def test_invalid_policy_stops_before_starting_downstream(tmp_path: Path) -> None:
    policy = tmp_path / "bad.yaml"
    policy.write_text("version: 1\ndefaults: {action: allow}\nservers: {}\n")
    marker = tmp_path / "started"
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({
        "version": 1, "policy": str(policy), "database": str(tmp_path / "events.db"),
        "downstream": {"name": "demo", "command": sys.executable, "cwd": str(ROOT),
                       "args": ["-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"]},
    }))
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "boba.main", "--config", str(config),
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    assert process.returncode == 1 and not marker.exists()
    assert stdout == b"" and b"Boba stopped" in stderr
