from pathlib import Path

from mcp import types
import pytest

from boba.config import load_yaml
from boba.security.policy_engine import Policy, PolicyEngine, Rule


@pytest.mark.parametrize(("tool", "args", "allowed"), [
    ("read_file", {"path": "hello.txt"}, True),
    ("read_file", {"path": ".env"}, False),
    ("read_file", {"path": 123}, False),
    ("read_file", {}, False),
    ("read_file", {"path": "hello.txt", "secret": "TOKEN"}, False),
    ("unknown", {}, False), ("unapproved", {"path": "hello.txt"}, False),
    ("run_shell", {"path": "hello.txt"}, False),
])
def test_authorization(engine: PolicyEngine, tool: str, args: dict, allowed: bool) -> None:
    decision, _ = engine.evaluate(tool, args)
    assert (decision.decision == "allow") == allowed


def test_explicit_block_and_alert_precedence(engine: PolicyEngine) -> None:
    engine.policy.rules.extend([
        Rule(id="ALERT", name="observe", action="alert", tools=["read_file"]),
        Rule(id="DENY", name="deny", action="block", paths=["**/hello.txt"]),
    ])
    decision, _ = engine.evaluate("read_file", {"path": "hello.txt"})
    assert decision.decision == "block"
    assert decision.rule_ids == ["DENY"]
    assert decision.alerts == ["ALERT"]


def test_evaluation_failure_closed(engine: PolicyEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object) -> None:
        raise RuntimeError("SECRET")
    monkeypatch.setattr(engine, "_authorize", fail)
    decision, args = engine.evaluate("read_file", {"path": "hello.txt"})
    assert decision.decision == "block" and args == {}
    assert "SECRET" not in decision.model_dump_json()


def test_bad_policy_and_duplicate_yaml(policy: Policy, tmp_path: Path) -> None:
    data = policy.model_dump()
    data["defaults"]["action"] = "allow"
    with pytest.raises(ValueError):
        Policy.model_validate(data)
    data["defaults"]["action"] = "block"
    data["typo"] = True
    with pytest.raises(ValueError):
        Policy.model_validate(data)
    path = tmp_path / "bad.yaml"
    path.write_text("version: 1\nversion: 2\n")
    with pytest.raises(ValueError):
        load_yaml(path)


def test_remote_schema_ref_rejected(policy: Policy, sandbox: Path) -> None:
    tool = types.Tool(name="read_file", input_schema={"type": "object", "$ref": "https://example.invalid/schema"})
    with pytest.raises(ValueError):
        PolicyEngine(policy, "demo", sandbox, [tool])


def test_allowlisting_shell_still_denied(engine: PolicyEngine) -> None:
    engine.server.allowed_tools.append("run_shell")
    engine.server.path_arguments["run_shell"] = []
    assert not engine.permitted("run_shell")
    assert engine.evaluate("run_shell", {"path": "hello.txt"})[0].decision == "block"
