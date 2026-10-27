"""Strict, administrator-owned YAML configuration."""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
import yaml

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently replacing security settings."""


def unique_mapping(loader: UniqueLoader, node: yaml.MappingNode) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("Invalid or duplicate YAML key")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_yaml(path: Path) -> Any:
    if path.stat().st_size > 1_048_576:
        raise ValueError("Configuration too large")
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)


class Downstream(StrictModel):
    name: Identifier
    command: str = "@python"
    args: list[str]
    cwd: str = ".."
    timeout_seconds: float = Field(default=10.0, gt=0, le=300)


class Settings(StrictModel):
    version: Literal[1]
    agent_id: Identifier = "demo-agent"
    policy: str = "policies.yaml"
    database: str = "../events.db"
    downstream: Downstream

    @classmethod
    def load(cls, path: Path) -> "Settings":
        return cls.model_validate(load_yaml(path))
