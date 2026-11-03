"""Real loopback SSH + MCP tests. This fixture is not a deployable SSH server."""

import asyncio
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import pytest
import yaml

from boba.remote import ssh_command

asyncssh = pytest.importorskip("asyncssh", reason="Install .[dev,local-test]")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
async def local_gateway(tmp_path):
    if not shutil.which("ssh"):
        pytest.skip("OpenSSH client required")
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    identity = tmp_path / "identity"
    client_key.write_private_key(identity)
    identity.chmod(0o600)
    if sys.platform == "win32":
        import win32api
        import win32con
        import win32security
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:
            owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        finally:
            token.Close()
        acl = win32security.ACL()
        acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, owner)
        win32security.SetNamedSecurityInfo(str(identity), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, acl, None)
    counter = tmp_path / "counter"
    database = tmp_path / "events.db"
    policy = tmp_path / "policies.yaml"
    policy.write_text(yaml.safe_dump({
        "version": 1, "defaults": {"action": "block"}, "servers": {"probe": {
            "allowed_tools": ["probe"], "approved_roots": [str(tmp_path)],
            "path_arguments": {"probe": []},
        }},
    }))
    gateway_config = tmp_path / "boba.yaml"
    gateway_config.write_text(yaml.safe_dump({
        "version": 1, "policy": str(policy), "database": str(database),
        "downstream": {"name": "probe", "command": sys.executable, "cwd": str(ROOT),
                       "args": [str(ROOT / "tests/fixtures/local_probe_server.py"), str(counter)]},
    }))
    connections, children = [], []

    class Server(asyncssh.SSHServer):
        def connection_made(self, conn):
            connections.append(conn)

        def begin_auth(self, username):
            return True

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            return username == "boba-mcp" and key == client_key.convert_to_public()

    async def session(process):
        if process.command or process.subsystem:
            process.exit(1)
            return
        child = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "boba.main", "--config", str(gateway_config),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        children.append(child)
        try:
            await process.redirect(stdin=child.stdin, stdout=child.stdout)
            code = await asyncio.wait_for(child.wait(), 30)
            if code:
                print((await child.stderr.read()).decode())
            process.exit(code)
        finally:
            if child.returncode is None:
                child.terminate()
                await child.wait()
            process.close()
            await process.wait_closed()

    listener = await asyncssh.listen(
        "127.0.0.1", 0, server_factory=Server, server_host_keys=[host_key],
        process_factory=session, encoding=None, allow_pty=False, login_timeout=5,
    )
    port = listener.get_port()
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(f"[127.0.0.1]:{port} " + host_key.export_public_key().decode())
    config = tmp_path / "remote.yaml"
    config.write_text(yaml.safe_dump({
        "host": "127.0.0.1", "port": port, "identity_file": str(identity),
        "known_hosts_file": str(known_hosts),
    }))
    try:
        yield config, counter, database, children
    finally:
        listener.close()
        await listener.wait_closed()
        for conn in connections:
            conn.close()
            await conn.wait_closed()
        for child in children:
            if child.returncode is None:
                # Give Boba time to close its downstream process on stdin EOF.
                try:
                    await asyncio.wait_for(child.wait(), 5)
                except TimeoutError:
                    child.terminate()
                    await child.wait()


async def test_local_ssh_mcp_policy_and_audit(local_gateway):
    config, counter, database, children = local_gateway
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "boba.remote", "--config", str(config),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def request(number, method, params):
        message = {"jsonrpc": "2.0", "id": number, "method": method, "params": params}
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()
        line = await asyncio.wait_for(process.stdout.readline(), 15)
        if not line:
            raise AssertionError((await process.stderr.read()).decode())
        reply = json.loads(line)
        assert reply["id"] == number and "error" not in reply
        return reply["result"]

    try:
        async with asyncio.timeout(25):
            await request(1, "initialize", {"protocolVersion": "2025-11-25",
                "capabilities": {}, "clientInfo": {"name": "local-test", "version": "1"}})
            process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            listing = await request(2, "tools/list", {})
            assert [tool["name"] for tool in listing["tools"]] == ["probe"]
            assert (await request(3, "tools/call", {"name": "unknown", "arguments": {}}))["isError"]
            assert (await request(4, "tools/call", {"name": "probe", "arguments": {"unexpected": "value"}}))["isError"]
            assert not counter.exists()
            result = await request(5, "tools/call", {"name": "probe", "arguments": {}})
            assert not result.get("isError") and result["content"][0]["text"] == "LOCAL_PROBE_OK"
            assert counter.read_text().splitlines() == ["executed"]
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()
    with sqlite3.connect(database) as db:
        rows = db.execute("SELECT decision, outcome FROM events").fetchall()
    assert rows.count(("block", "blocked")) == 2
    assert rows.count(("allow", "success")) == 1


@pytest.mark.parametrize("failure", ["client_key", "host_key", "command"])
async def test_local_ssh_rejects_before_boba(local_gateway, failure):
    config, counter, database, children = local_gateway
    settings = yaml.safe_load(config.read_text())
    wrong_key = asyncssh.generate_private_key("ssh-ed25519")
    if failure == "client_key":
        wrong_key.write_private_key(settings["identity_file"])
    elif failure == "host_key":
        Path(settings["known_hosts_file"]).write_text(
            f"[127.0.0.1]:{settings['port']} " + wrong_key.export_public_key().decode())
    command = ssh_command(config)
    if failure == "command":
        command.append("id")
    process = await asyncio.create_subprocess_exec(
        *command, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 15)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode != 0 and stdout == b""
    assert b"bad permissions" not in stderr
    if failure == "client_key":
        assert b"Permission denied" in stderr, stderr
    elif failure == "host_key":
        assert b"Host key verification failed" in stderr, stderr
    assert children == [] and not counter.exists() and not database.exists()


async def test_local_ssh_refuses_forwarding(local_gateway):
    config, _, _, children = local_gateway
    settings = yaml.safe_load(config.read_text())
    async with asyncssh.connect(
        "127.0.0.1", port=settings["port"], username="boba-mcp",
        client_keys=[settings["identity_file"]], known_hosts=settings["known_hosts_file"],
        agent_path=None,
    ) as connection:
        with pytest.raises(asyncssh.ChannelOpenError):
            await connection.open_connection("127.0.0.1", 80)
    assert children == []
