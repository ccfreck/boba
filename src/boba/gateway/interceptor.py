"""There is exactly one downstream call site, gated by policy and audit."""

import asyncio
import logging
from time import monotonic
from typing import Any, Protocol

from mcp import types

from boba.events.models import SecurityEvent
from boba.events.storage import EventStore
from boba.security.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)


class ToolClient(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult: ...


def error_result(reason: str) -> types.CallToolResult:
    return types.CallToolResult(is_error=True, content=[types.TextContent(type="text", text=f"Boba: {reason}")])


class Interceptor:
    def __init__(self, engine: PolicyEngine, client: ToolClient, store: EventStore,
                 agent: str, server: str, timeout: float) -> None:
        self.engine, self.client, self.store = engine, client, store
        self.agent, self.server, self.timeout = agent, server, timeout

    async def call(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        started = monotonic()
        decision, forwarded = self.engine.evaluate(name, arguments)
        # Unknown tool names are attacker-controlled and may themselves be secrets.
        safe_name = name if name in self.engine.server.allowed_tools else "<unapproved>"
        event = SecurityEvent(**decision.model_dump(), agent_id=self.agent,
                              server=self.server, tool=safe_name)
        if decision.decision == "block":
            event.outcome = "blocked"
        event.duration_ms = (monotonic() - started) * 1000
        try:
            self.store.save(event)
        except Exception:
            logger.error("Audit write failed; request not forwarded")
            return error_result("Audit unavailable; request denied")
        if decision.decision == "block":
            return error_result(decision.reason)
        try:
            async with asyncio.timeout(self.timeout):
                result = await self.client.call_tool(name, forwarded)
            event.outcome = "error" if result.is_error else "success"
            return result
        except asyncio.CancelledError:
            event.outcome = "cancelled"
            event.reason = "Request cancelled; execution may have started"
            raise
        except Exception:
            event.outcome = "error"
            event.severity = "warning"
            event.reason = "Downstream unavailable, timed out, or returned invalid response"
            return error_result(event.reason)
        finally:
            event.duration_ms = (monotonic() - started) * 1000
            try:
                self.store.save(event)
            except Exception:
                logger.error("Audit completion write failed; durable pending event retained")
