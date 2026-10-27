from pathlib import Path

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from boba.config import Settings, load_yaml
from boba.events.storage import EventStore
from boba.gateway.interceptor import Interceptor
from boba.gateway.upstream import connect, discover
from boba.security.policy_engine import Policy, PolicyEngine


async def serve(config_path: Path) -> None:
    config_path = config_path.resolve(strict=True)
    settings = Settings.load(config_path)
    base = config_path.parent
    policy_path = (base / settings.policy).resolve(strict=True)
    # Reject malformed configuration before starting the downstream executable.
    policy = Policy.model_validate(load_yaml(policy_path))
    if settings.downstream.name not in policy.servers:
        raise ValueError("Missing server policy")
    store = EventStore((base / settings.database).resolve())
    async with connect(settings.downstream, base) as client:
        tools = await discover(client)
        engine = PolicyEngine(policy, settings.downstream.name, policy_path.parent, tools)
        interceptor = Interceptor(engine, client, store, settings.agent_id,
                                  settings.downstream.name, settings.downstream.timeout_seconds)

        async def list_tools(ctx: ServerRequestContext, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
            return types.ListToolsResult(tools=[tool for tool in tools if engine.permitted(tool.name)])

        async def call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
            return await interceptor.call(params.name, params.arguments or {})

        # Schema validation stays inside the interceptor so invalid arguments get audited.
        server = Server("boba", version="0.1.0", on_list_tools=list_tools, on_call_tool=call_tool)
        async with stdio_server() as streams:
            await server.run(*streams, server.create_initialization_options())
