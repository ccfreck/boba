from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from boba import remote


@pytest.fixture
def remote_config(tmp_path: Path) -> Path:
    # Spaces exercise OpenSSH's own parsing of the known-hosts option.
    directory = tmp_path / "client files"
    directory.mkdir()
    (directory / "identity").write_text("FAKE_PRIVATE_KEY")
    (directory / "known_hosts").write_text("")
    path = tmp_path / "remote.yaml"
    path.write_text(yaml.safe_dump({
        "host": "gateway.example.test", "identity_file": "client files/identity",
        "known_hosts_file": "client files/known_hosts",
    }))
    return path


@pytest.mark.parametrize("host", ["-oProxyCommand=evil", "user@host", "host;command", "host\ncommand", "", "a/b", "fe80::1%bad\nvalue"])
def test_rejects_invalid_destination(host: str) -> None:
    with pytest.raises(ValueError):
        remote.RemoteSettings(host=host, identity_file="key", known_hosts_file="hosts")


@pytest.mark.parametrize("host", ["gateway.example.test", "192.0.2.1", "2001:db8::1"])
def test_accepts_network_destinations(host: str) -> None:
    assert remote.RemoteSettings(host=host, identity_file="key", known_hosts_file="hosts").host == host


def test_missing_host_trust_fails_closed(remote_config: Path) -> None:
    (remote_config.parent / "client files/known_hosts").unlink()
    with pytest.raises(FileNotFoundError):
        remote.ssh_command(remote_config)


def test_real_openssh_effective_options(remote_config: Path) -> None:
    if not shutil.which("ssh"):
        pytest.skip("OpenSSH client unavailable")
    command = remote.ssh_command(remote_config)
    # -G prints effective configuration and exits without opening a connection.
    result = subprocess.run([command[0], "-G", *command[1:]], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    options = dict(line.split(" ", 1) for line in result.stdout.splitlines() if " " in line)
    for name, value in {
        "user": "boba-mcp", "port": "2222", "batchmode": "yes",
        "stricthostkeychecking": "true", "identitiesonly": "yes",
        "clearallforwardings": "yes", "forwardagent": "no", "forwardx11": "no",
        "passwordauthentication": "no", "kbdinteractiveauthentication": "no",
        "preferredauthentications": "publickey", "requesttty": "false",
    }.items():
        assert options[name] == value
    assert "client files/known_hosts" in options["userknownhostsfile"]
    assert "localforward" not in options and "remoteforward" not in options
    assert "FAKE_PRIVATE_KEY" not in " ".join(command)


@pytest.mark.parametrize("exit_code", [0, 1, 255])
def test_adapter_preserves_exit_and_streams_without_retry(remote_config: Path, monkeypatch, capsys, exit_code: int) -> None:
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, exit_code)
    monkeypatch.setattr(sys, "argv", ["boba-remote", "--config", str(remote_config)])
    monkeypatch.setattr(remote.subprocess, "run", run)
    with pytest.raises(SystemExit) as stopped:
        remote.main()
    assert stopped.value.code == exit_code
    assert len(calls) == 1 and calls[0][1] == {"check": False}
    assert capsys.readouterr().out == ""


def test_configuration_error_does_not_leak_values(tmp_path: Path, monkeypatch, capsys) -> None:
    path = tmp_path / "remote.yaml"
    path.write_text("host: SECRET_INVALID_VALUE\n")
    monkeypatch.setattr(sys, "argv", ["boba-remote", "--config", str(path)])
    with pytest.raises(SystemExit) as stopped:
        remote.main()
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert output.out == "" and "SECRET" not in output.err
