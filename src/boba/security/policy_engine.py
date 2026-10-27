"""All authorization decisions terminate here before downstream execution."""

from pathlib import Path
from typing import Any, Literal

from jsonschema import validators
from mcp import types
from pydantic import Field, model_validator
from referencing import Registry

from boba.config import Identifier, StrictModel, load_yaml
from boba.security.command_rules import prohibited
from boba.security.path_validator import UnsafePath, matches, validate_path
from boba.security.rate_detector import RateDetector


class Defaults(StrictModel):
    action: Literal["block"] = "block"


class ServerPolicy(StrictModel):
    allowed_tools: list[Identifier]
    approved_roots: list[str] = Field(min_length=1)
    path_arguments: dict[Identifier, list[str]]

    @model_validator(mode="after")
    def bindings(self) -> "ServerPolicy":
        if set(self.allowed_tools) != set(self.path_arguments):
            raise ValueError("Each allowed tool needs an explicit path binding (or empty list)")
        if any(not field or "/" in field for fields in self.path_arguments.values() for field in fields):
            raise ValueError("Only top-level path fields are supported")
        return self


class Rule(StrictModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=200)
    action: Literal["block", "alert"]
    tools: list[Identifier] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    threshold: int | None = Field(default=None, ge=1, le=10000)
    window_seconds: int | None = Field(default=None, ge=1, le=86400)

    @model_validator(mode="after")
    def valid_rule(self) -> "Rule":
        rate = self.threshold is not None or self.window_seconds is not None
        if rate and (self.threshold is None or self.window_seconds is None or self.action != "alert" or self.paths):
            raise ValueError("Rate rules need threshold/window and action alert, without paths")
        if not rate and not (self.tools or self.paths):
            raise ValueError("Rule needs a matcher")
        if any(not pattern for pattern in self.paths):
            raise ValueError("Empty path pattern")
        return self


class Policy(StrictModel):
    version: Literal[1]
    defaults: Defaults
    servers: dict[Identifier, ServerPolicy]
    rules: list[Rule] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self) -> "Policy":
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Duplicate rule IDs")
        return self


class Decision(StrictModel):
    decision: Literal["allow", "block"] = "block"
    severity: Literal["info", "warning", "critical"] = "critical"
    rule_ids: list[str] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    reason: str = "Policy evaluation failed"


def check_references(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef"} and (not isinstance(item, str) or not item.startswith("#")):
                raise ValueError("Only local schema references are supported")
            check_references(item)
    elif isinstance(value, list):
        for item in value:
            check_references(item)


class PolicyEngine:
    def __init__(self, policy: Policy, server: str, base: Path, tools: list[types.Tool]) -> None:
        self.policy = policy
        self.server = policy.servers[server]  # Missing server fails startup closed.
        self.roots = [(base / root).resolve(strict=True) for root in self.server.approved_roots]
        if not all(root.is_dir() for root in self.roots):
            raise ValueError("Approved root is not a directory")
        self.tools = {tool.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise ValueError("Duplicate downstream tool names")
        self.validators: dict[str, Any] = {}
        for tool in tools:
            check_references(tool.input_schema)
            validator = validators.validator_for(tool.input_schema)
            validator.check_schema(tool.input_schema)
            self.validators[tool.name] = validator(tool.input_schema, registry=Registry())
        self.rates = RateDetector()

    @classmethod
    def load(cls, path: Path, server: str, tools: list[types.Tool]) -> "PolicyEngine":
        return cls(Policy.model_validate(load_yaml(path)), server, path.parent, tools)

    def permitted(self, name: str) -> bool:
        return (name in self.tools and name in self.server.allowed_tools and not prohibited(name)
                and not any(rule.action == "block" and not rule.paths and name in rule.tools
                            for rule in self.policy.rules))

    def evaluate(self, name: str, arguments: dict[str, Any]) -> tuple[Decision, dict[str, Any]]:
        alerts: list[str] = []
        try:
            # Count every intercepted attempt, including denials. State keys are policy IDs, never input.
            for rule in self.policy.rules:
                if rule.threshold is not None and (not rule.tools or name in rule.tools):
                    if self.rates.observe(rule.id, rule.threshold, rule.window_seconds):
                        alerts.append(rule.id)
            decision, forwarded = self._authorize(name, arguments)
            decision.alerts.extend(alerts)
            if decision.alerts and decision.decision == "allow":
                decision.severity = "warning"
            return decision, forwarded
        except Exception:
            # Fail closed; exception text can contain complete argument values.
            return Decision(rule_ids=["BOBA-EVALUATION"], alerts=alerts), {}

    def _authorize(self, name: str, arguments: dict[str, Any]) -> tuple[Decision, dict[str, Any]]:
        def block(reason: str, rule: str) -> tuple[Decision, dict[str, Any]]:
            return Decision(reason=reason, rule_ids=[rule]), {}

        if name not in self.tools:
            return block("Unknown tool", "BOBA-IDENTITY")
        if not self.validators[name].is_valid(arguments):
            return block("Arguments do not match input schema", "BOBA-SCHEMA")
        if prohibited(name):
            return block("Shell execution is disabled", "BOBA-COMMAND")
        if name not in self.server.allowed_tools:
            return block("Tool is not permitted", "BOBA-PERMISSION")
        paths: list[Path] = []
        forwarded = dict(arguments)
        try:
            for field in self.server.path_arguments[name]:
                lexical, canonical = validate_path(arguments.get(field), self.roots)
                paths.extend([lexical, canonical])
                forwarded[field] = str(canonical)
        except UnsafePath as error:
            return block(str(error), "BOBA-PATH")
        blocks: list[str] = []
        alerts: list[str] = []
        for rule in self.policy.rules:
            if rule.threshold is not None or (rule.tools and name not in rule.tools):
                continue
            if rule.paths and not any(matches(path, rule.paths) for path in paths):
                continue
            (blocks if rule.action == "block" else alerts).append(rule.id)
        if blocks:
            return Decision(reason="Explicit blocking rule matched", rule_ids=blocks, alerts=alerts), {}
        return Decision(decision="allow", severity="info", reason="Explicit tool permission", alerts=alerts), forwarded
