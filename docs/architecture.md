# Architecture and decisions

## Runtime

`boba.main` reads strict settings, validates policy syntax, opens SQLite, and starts
one administrator-selected downstream stdio process. `gateway/upstream.py` owns
the official SDK client context and bounded paginated discovery. The gateway
snapshots tool definitions at startup and exposes only permitted ones.

`gateway/server.py` uses the SDK's low-level `Server` with `on_list_tools` and
`on_call_tool` handlers. Low-level dispatch preserves downstream schemas and full
`CallToolResult` values without synthesizing Python function signatures. Schema
validation is deliberately performed inside the interceptor so malformed tool
arguments produce security events. Malformed JSON-RPC/envelope fields that the
SDK rejects before dispatch are protocol errors, not tool execution events.

`security/policy_engine.py` returns a binary `Decision` and a separate copy of
authorized arguments. Bound filesystem fields are replaced with canonical absolute
paths. A failure returns block, never an implicit allow. `gateway/interceptor.py`
contains the only downstream tool call site. It requires both an allow decision
and a successful durable audit write before entering it.

Frequency accounting happens first so denied/invalid attempts also count. Final
authorization still validates tool identity and schema, then permissions, paths,
command restrictions and matching rules. Alerts remain independent findings.
Shell restrictions can reject early; no later stage can turn a block into allow.

## Storage and failure behavior

Events contain UUID, UTC timestamp, configured agent/server labels, approved tool
name or `<unapproved>`, decision, severity, rule IDs, alert IDs, fixed reason,
duration, and outcome. No argument/response/exception columns exist. Built-in
messages contain no substituted user values. Trusted policy names are shown in
the dashboard but not interpolated into tool errors.

An allowed call first commits `pending`, then updates the same UUID with its
outcome. A blocked call commits `blocked` and returns an MCP error result. SQLite
uses WAL and FULL synchronization for writes. If the initial write fails, no call
is forwarded. If completion logging fails, the pending record remains and a fixed
stderr message is emitted. The operation cannot be undone. Disk failure makes
guaranteed recording impossible; it never authorizes a request.

Timeouts, disconnects, and invalid downstream responses produce an error result
and `allow/error` event: authorization succeeded, execution did not complete
reliably. Cancellation records `cancelled` and is re-raised. Requests are not
retried. SDK and downstream diagnostics are suppressed in gateway mode because
they can contain raw payloads; Boba emits only fixed operational errors to stderr.

The Streamlit process opens SQLite read-only and renders real records. For this
local MVP it loads the event history into memory, so operators must manage
retention before datasets become large. It never creates demo events on startup.

## SDK verification

Implementation verified against the installed official **mcp 2.3.0** source:
`Server` constructor handlers, `ClientSession.initialize/list_tools/call_tool`,
`stdio_client`, `stdio_server`, snake-case model attributes, and paginated tool
listing. Dependency range is `mcp>=2.3,<3`. Relevant references:

- <https://py.sdk.modelcontextprotocol.io/>
- <https://github.com/modelcontextprotocol/python-sdk>

The implementation uses no private SDK APIs. Real subprocess tests verify actual
protocol serialization rather than mocking MCP messages.

## Extension seams

The transport context in `upstream.py` and the interceptor's `ToolClient` protocol
are sufficient seams for another transport later. Authorization and storage do
not depend on stdio streams. Multi-server routing, remote identities, approval
workflows, and schema change tracking need explicit designs in later releases;
none are implicitly supported by this single-server MVP.
