# Threat model and security boundary

## Protected assets and trust

Assets: downstream tool execution permissions, sandbox file contents, and a
useful audit trail without secret payloads. The attacker can control tool names
and arguments, submit malformed calls, probe paths, and generate high call rates.

The administrator, policy/configuration files, executable selection, tool semantics,
and startup schemas are trusted. Agent IDs are operator labels, not authentication.
Downstream responses remain untrusted and are returned to the client without
content inspection. An approved tool can itself be malicious or vulnerable;
Boba is not a substitute for reviewing and restricting downstream software.

## Controls and evidence

| Threat | Control | Verification |
| --- | --- | --- |
| Unknown/unapproved operation | Discovery + explicit allowlist + default deny | Policy and real gateway tests |
| Argument/schema confusion | JSON Schema validation before dispatch | Malformed argument integration test |
| Credential read | Built-in protected components + configurable path rules | Fake AWS, SSH, `.env`, secrets tests |
| Traversal/symlink escape | Lexical checks + canonical root containment | Path and real gateway tests |
| Shell tool execution | No supported shell tools in v0.1 | Allowlisted-shell denial test |
| Detection-only “blocking” | Single gated call site; handler-entry counter | Ten real denied calls, zero entries |
| Repeated probing | Bounded frequency findings on all attempts | Threshold/window/denial tests |
| Sensitive audit payloads | Fixed field allowlist, fixed reasons, redacted unknown names | Storage sanitization tests |
| Fail-open audit/policy errors | Block on evaluation or initial audit failure | Failure injection and startup tests |
| Timeout/disconnect | Bounded call, generic error, durable outcome | Real subprocess failure tests |

## Filesystem limitations

Between Boba's path check and a downstream process opening a file, another actor
can replace a directory or symlink (TOCTOU). Passing canonical absolute paths does
not eliminate this race. Protect sandbox ownership and use least-privilege OS
permissions or stronger process isolation. The demo independently opens each path
component relative to directory descriptors with `O_NOFOLLOW`, rejects traversal,
and reads regular files only, capped at 64 KiB. Its root and parent directories
must remain administrator-controlled. This implementation requires POSIX.

Canonicalization does not detect hard links to sensitive inodes under harmless
names, bind mounts, or secret copies renamed to ordinary files. Path policy is
not content classification. Do not put real secrets in the demo, allow untrusted
actors to populate the sandbox, or treat filename rules as a complete data-loss
prevention system. The demo allows directory name listing, including sensitive
entry names, while protected file reads are blocked by Boba.

## Other limitations

- Direct MCP, local tools, network connections, and other paths outside Boba are
  entirely outside the boundary. OS isolation is separately required.
- Allowed timeout/cancelled operations may have started. No rollback or retry is
  claimed. The event records authorization separately from execution outcome.
- Protocol-invalid envelopes rejected by the SDK before a tool handler runs are
  not per-tool security events. Valid tool requests with invalid arguments are.
- SQLite events are not cryptographically authenticated; privileged local users
  can alter them. A failed completion write leaves `pending`, not a false success.
- There is no global resource sandbox. Large messages, expensive schemas, slow
  filesystem operations, large tool responses, and long audit histories can
  consume resources. Discovery and rate state have explicit bounds, but this is
  not a general denial-of-service defense. Frequency detection alerts only.
- Schemas are snapshotted, not pinned across releases. Dynamic tool change
  notifications, resources, prompts, sampling, elicitation, subscriptions, and
  multi-round tool execution are not proxied.
- Dashboard access is local and unauthenticated. Bind it to loopback and protect
  the database and policy permissions. Rotate/archive events as necessary.
