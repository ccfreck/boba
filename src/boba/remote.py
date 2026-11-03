"""MCP stdio client adapter for the dedicated, forced-command SSH endpoint."""

import argparse
import ipaddress
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import Field, field_validator

from boba.config import StrictModel, load_yaml


class RemoteSettings(StrictModel):
    host: str
    port: int = Field(default=2222, ge=1, le=65535)
    identity_file: str
    known_hosts_file: str

    @field_validator("host")
    @classmethod
    def valid_host(cls, value: str) -> str:
        if len(value) > 253 or not re.fullmatch(r"[A-Za-z0-9.:-]+", value):
            raise ValueError("Expected a hostname or IP address")
        try:
            ipaddress.ip_address(value)
        except ValueError:
            if not all(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in value.split(".")
            ):
                raise ValueError("Expected a hostname or IP address")
        return value


def ssh_command(config_path: Path) -> list[str]:
    """No shell, user SSH config, implicit trust, forwarding, or fallback."""
    config_path = config_path.resolve(strict=True)
    settings = RemoteSettings.model_validate(load_yaml(config_path))
    executable = shutil.which("ssh")
    if executable is None:
        raise ValueError("OpenSSH client is required")
    paths = []
    for value in (settings.identity_file, settings.known_hosts_file):
        path = (config_path.parent / value).resolve(strict=True)
        if not path.is_file() or any(c in path.as_posix() for c in '\r\n"'):
            raise ValueError("Invalid credential or host-key file path")
        paths.append(path.as_posix())
    identity, known_hosts = paths
    options = [
        "BatchMode=yes", "StrictHostKeyChecking=yes", "UpdateHostKeys=no",
        "VerifyHostKeyDNS=no", f'UserKnownHostsFile="{known_hosts}"',
        "GlobalKnownHostsFile=none", "IdentitiesOnly=yes", "IdentityAgent=none",
        "PreferredAuthentications=publickey", "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no", "ClearAllForwardings=yes",
        "ForwardAgent=no", "ForwardX11=no", "ProxyCommand=none", "ProxyJump=none",
        "ControlMaster=no", "ConnectTimeout=10", "ConnectionAttempts=1",
        "ServerAliveInterval=15", "ServerAliveCountMax=2", "LogLevel=ERROR",
    ]
    command = [executable, "-F", "none", "-T", "-S", "none", "-e", "none"]
    for option in options:
        command.extend(["-o", option])
    command.extend(["-i", identity, "-p", str(settings.port), "-l", "boba-mcp", settings.host])
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect an MCP client to the Boba SSH endpoint")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        command = ssh_command(args.config)
        # Inherit byte streams directly. stdout is reserved for MCP messages.
        result = subprocess.run(command, check=False)
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("Boba remote: configuration or connection failed", file=sys.stderr)
        raise SystemExit(1) from None
    raise SystemExit(result.returncode if result.returncode >= 0 else 1)


if __name__ == "__main__":
    main()
