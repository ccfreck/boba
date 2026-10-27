import asyncio
from pathlib import Path

from mcp import types
import pytest

from boba.events.storage import EventStore
from boba.gateway.interceptor import Interceptor
from boba.security.policy_engine import PolicyEngine


class CountingClient:
    def __init__(self, mode: str = "success") -> None:
        self.calls = 0
        self.mode = mode

    async def call_tool(self, name: str, arguments: dict) -> types.CallToolResult:
        self.calls += 1
        if self.mode == "disconnect":
            raise ConnectionError("SECRET_DOWNSTREAM_PAYLOAD")
        if self.mode == "timeout":
            await asyncio.sleep(10)
        return types.CallToolResult(content=[types.TextContent(type="text", text="SECRET_RESPONSE")])


async def test_block_never_calls_downstream(engine: PolicyEngine, tmp_path: Path) -> None:
    client = CountingClient()
    store = EventStore(tmp_path / "events.db")
    gateway = Interceptor(engine, client, store, "agent", "demo", 1)
    assert (await gateway.call("read_file", {"path": ".env"})).is_error
    assert client.calls == 0
    assert store.all()[0]["outcome"] == "blocked"


@pytest.mark.parametrize("mode", ["disconnect", "timeout"])
async def test_downstream_failure_is_logged(engine: PolicyEngine, tmp_path: Path, mode: str) -> None:
    store = EventStore(tmp_path / "events.db")
    gateway = Interceptor(engine, CountingClient(mode), store, "agent", "demo", 0.02)
    result = await gateway.call("read_file", {"path": "hello.txt"})
    assert result.is_error
    event = store.all()[0]
    assert event["decision"] == "allow" and event["outcome"] == "error"
    assert "SECRET" not in str(event)


async def test_payloads_and_unknown_names_not_logged(engine: PolicyEngine, tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    gateway = Interceptor(engine, CountingClient(), store, "agent", "demo", 1)
    await gateway.call("read_file", {"path": "hello.txt"})
    await gateway.call("SECRET_TOOL_NAME", {"token": "SECRET_ARGUMENT"})
    assert "SECRET" not in str(store.all())


async def test_audit_failure_prevents_forwarding(engine: PolicyEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = EventStore(tmp_path / "events.db")
    def fail(event: object) -> None:
        raise OSError("Disk full")
    monkeypatch.setattr(store, "save", fail)
    client = CountingClient()
    gateway = Interceptor(engine, client, store, "agent", "demo", 1)
    assert (await gateway.call("read_file", {"path": "hello.txt"})).is_error
    assert (await gateway.call("read_file", {"path": ".env"})).is_error
    assert client.calls == 0


async def test_durable_audit_precedes_execution_and_result_preserved(engine: PolicyEngine, tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    expected = types.CallToolResult(content=[types.TextContent(type="text", text="result")],
                                    structured_content={"value": 7}, meta={"test": "preserved"})

    class Client:
        async def call_tool(self, name: str, arguments: dict) -> types.CallToolResult:
            assert store.all()[0]["outcome"] == "pending"
            assert Path(arguments["path"]).is_absolute()
            return expected

    gateway = Interceptor(engine, Client(), store, "agent", "demo", 1)
    assert await gateway.call("read_file", {"path": "hello.txt"}) is expected
    assert store.all()[0]["outcome"] == "success"


async def test_cancellation_keeps_audit(engine: PolicyEngine, tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.db")
    entered = asyncio.Event()

    class Client:
        async def call_tool(self, name: str, arguments: dict) -> types.CallToolResult:
            entered.set()
            await asyncio.sleep(60)
            return types.CallToolResult(content=[])

    gateway = Interceptor(engine, Client(), store, "agent", "demo", 120)
    task = asyncio.create_task(gateway.call("read_file", {"path": "hello.txt"}))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.all()[0]["outcome"] == "cancelled"
