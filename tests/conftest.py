from pathlib import Path

from mcp import types
import pytest

from boba.security.policy_engine import Policy, PolicyEngine


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "hello.txt").write_text("hello")
    for name in (".env", ".env.production", ".aws/credentials", ".ssh/id_rsa", "secrets/key"):
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("FAKE_SECRET_DO_NOT_LOG")
    return root


@pytest.fixture
def tools() -> list[types.Tool]:
    return [types.Tool(name=name, description="test", input_schema={
        "type": "object", "properties": {"path": {"type": "string"}},
        "required": ["path"], "additionalProperties": False,
    }) for name in ("read_file", "list_directory", "run_shell", "unapproved")]


@pytest.fixture
def policy(sandbox: Path) -> Policy:
    return Policy.model_validate({
        "version": 1, "defaults": {"action": "block"},
        "servers": {"demo": {
            "allowed_tools": ["read_file", "list_directory"], "approved_roots": [str(sandbox)],
            "path_arguments": {"read_file": ["path"], "list_directory": ["path"]},
        }}, "rules": [{"id": "RATE", "name": "Rate", "action": "alert", "threshold": 3, "window_seconds": 60}],
    })


@pytest.fixture
def engine(policy: Policy, tools: list[types.Tool], sandbox: Path) -> PolicyEngine:
    return PolicyEngine(policy, "demo", sandbox, tools)
