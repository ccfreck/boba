# Decision point: Boba architecture

## The gap

Boba currently checks requests sent through it to one local MCP server. It does
not control everything the agent can do.

An agent with other tools could go around Boba by:

- Reading protected files through its own file or terminal tools.
- Connecting directly to another MCP server or service.
- Using credentials available in its environment.
- Changing Boba's rules or connection settings if those files are writable.

**The gap: Boba can block a request, but it cannot currently force the agent to
send that request through Boba.** Which bypasses are possible depends on the
agent's host permissions and configuration.

## Architecture options

| Option | Why choose it? | Gap remaining |
| --- | --- | --- |
| 1. Optional Boba checkpoint | Simple setup for protecting selected tool calls; closest to today. | Other agent tools can bypass Boba. |
| 2. One gateway for all MCP servers | Centralizes MCP policies, connections, and audit logs. | Direct terminal, file, or network access can still bypass it. |
| 3. Sandboxed agent, Boba outside | Restricts the agent's access and makes Boba the required route to protected tools. | Approved MCP servers still need their own access restrictions. |
| 4. Sandboxed agent and separately sandboxed servers | Also limits damage from buggy or malicious approved tools. | More setup and maintenance; allowed responses still need careful handling. |
| 5. Shared Boba service | Gives multiple agents or users central policies and logs. | Requires authentication, per-user permissions, and reliable hosting; agent restrictions are still needed. |

These options can be combined. For example, a sandboxed agent can use one gateway
that routes to several separately sandboxed MCP servers.

## Recommended architecture

**Start with option 3: put the agent in a sandbox and keep Boba outside it.**

```text
INSIDE AGENT SANDBOX
  Agent + working files + restricted terminal
                    |
          Controlled connection
                    |
                    v
OUTSIDE AGENT SANDBOX
  Boba: rules, protected credentials, audit logs
                    |
                    v
  Approved MCP servers → Protected files and services
```

The agent can work on files explicitly provided to it. Protected operations must
go through Boba. MCP servers can later run in their own separate sandboxes.

### Why this approach?

- **Closes side doors:** restrict file, process, and network access that could
  bypass Boba.
- **Protects the rules:** the agent cannot edit Boba's policies or configuration.
- **Protects credentials:** service credentials stay outside the agent's environment
  and are supplied only to the components that need them.
- **Preserves useful tools:** the agent can still use a terminal within its limited
  workspace.
- **Starts small:** prove the boundary with one agent and one MCP server before
  adding multi-server routing or shared hosting.

## What must be enforced

- Give the agent access only to approved working files, not Boba's configuration,
  credentials, or protected host files.
- Restrict network access so protected services cannot be reached directly.
- Prevent the agent from changing its restrictions or controlling the host through
  privileged interfaces such as the Docker socket.
- Provide a controlled connection to Boba across the sandbox boundary.
- Restrict MCP server permissions too; being outside the agent's sandbox does not
  mean a server should have unrestricted access.

**A container alone is not enough. Its mounts, permissions, and network rules
must enforce these limits.**

## Decision status and next step

**Proposed, not yet implemented or approved.** Boba currently provides one local
stdio connection; it does not create an agent sandbox or enforce this boundary.

Next step: build a small proof of concept with one sandboxed agent, Boba outside,
and one MCP server. Verify that an approved request succeeds through Boba while
direct access to protected files, credentials, and services fails.

This addresses bypasses. It does not by itself add response inspection, prevent
every harmful allowed operation, or make audit logs tamper-proof. See the
[threat model](threat-model.md) for the existing limitations.
