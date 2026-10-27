from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import Field

from boba.security.policy_engine import Decision


class SecurityEvent(Decision):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_id: str
    server: str
    tool: str
    duration_ms: float = 0.0
    outcome: Literal["pending", "blocked", "success", "error", "cancelled"] = "pending"
