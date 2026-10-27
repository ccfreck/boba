# Boba policy format, version 1

This is a custom Boba YAML format, not an MCP standard. Examples are in
`config/policies.yaml`. YAML is safely loaded; duplicate keys, unknown fields,
invalid types, duplicate rule IDs, and unsupported versions are rejected.
Configuration files are limited to 1 MiB. Only `defaults.action: block` is valid.

## Permission and matching semantics

1. A tool must have been discovered and its arguments must match its advertised
   JSON Schema. Local schema references are supported; nonlocal references are
   rejected, and Boba's validator does not retrieve network schemas. JSON Schema
   `format` is annotation-only. Downstream schemas must accurately describe their
   tools; Boba does not infer missing restrictions.
2. Tool names in `allowed_tools` are exact, case-sensitive matches. Each needs a
   `path_arguments` entry. Empty `[]` means an administrator explicitly reviewed
   the tool as having no filesystem arguments; it is not an automatic exemption
   for arbitrary code or command runners.
3. `execute_command`, `run_shell`, and `shell_exec` (case-insensitive) are always
   disabled in v0.1, even if allowlisted. Other execution-capable tools remain
   default-denied and must not be granted by a read-only policy.
4. Built-in filesystem restrictions always apply to configured path bindings.
5. Each ordinary rule matches if **both** its tool selector and path selector
   match. An omitted selector means unrestricted for that dimension. Within each
   list, entries are **OR**. At least one selector is required. Rules containing
   only `tools` match that tool regardless of arguments. A path rule without any
   bound paths cannot match. All matching block IDs and alert IDs are collected.
6. Any explicit block beats the allowlist. Alerts never change authorization.
   Identity/schema/permission/built-in path failures short-circuit ordinary rule
   evaluation and identify the relevant `BOBA-*` safeguard instead of a custom ID.

Path patterns use Python `fnmatchcase` over a slash-prefixed, case-folded absolute
lexical **and** canonical path. `*` can span `/`; `**` has no special recursive
meaning beyond repeated `*`. Matching also tries a trailing slash so directory
patterns such as `**/secrets/**` cover the directory itself. `?` and character
classes follow `fnmatchcase`. Patterns are not regular expressions or gitignore
rules. The sample patterns also match root-level sensitive files.

## Filesystem contract

- Bindings are **required top-level string fields**, e.g. `read_file: [path]`.
  Nested paths, lists, URIs, globs, tilde expansion, Windows/backslash syntax,
  percent-encoded paths, colons, and control characters are unsupported. No
  percent-decoding or variable expansion occurs. Some harmless names are
  conservatively rejected.
- Relative paths resolve against the **first** approved root. Absolute paths must
  be lexically and canonically contained in the same approved root. Roots must
  exist at startup. Path arguments must exist when evaluated.
- Any `..` component is rejected, even if normalization would remain in-root.
  Canonical `resolve(strict=True)` follows symlinks; an escaped target is denied.
  Symlinks to protected files are denied. In-root symlinks to safe files may pass
  and the canonical path is forwarded.
- `.aws`, `.ssh`, `secrets` components and every `.env*` component are always
  protected, case-insensitively. These protections cannot be disabled by YAML.
  Custom patterns add protections, for example `**/private/**`.
- Filesystem tools must accept absolute canonical paths and must enforce their
  own approved-root checks. Path validation cannot secure tools with undisclosed
  filesystem behavior. See TOCTOU and hard-link limitations in the threat model.

## Behavioral rules

A rule with `threshold` and `window_seconds` is a rate rule. It must have
`action: alert`, cannot have `paths`, and may restrict exact `tools`.
Thresholds range from 1–10,000; windows from 1–86,400 seconds. Up to 100 rules are
accepted. A rate rule counts **all matching intercepted attempts**, allowed or
blocked, across tools for the configured agent/server in one gateway process.

The window is `(now - window_seconds, now]`, measured using a monotonic clock.
An alert is added to every request that makes the count **strictly exceed** the
threshold. Each rule stores only the latest `threshold + 1` timestamps, which is
sufficient to determine exceedance exactly. Restarting resets the window; multiple
gateway processes do not share counters. Client-supplied identities do not create
new rate buckets.

## Decisions and events

`decision` is `allow` or `block`; `alerts` is a separate list of rule IDs. Allowed
requests are `info`, allowed requests with alerts are `warning`, and blocks are
`critical`. Downstream errors are `warning`. `rule_ids` lists blocking rules or
a built-in safeguard; `alerts` lists monitoring findings. Rule descriptions are
administrator configuration, never user payloads.

Reload by restarting the gateway. The dashboard shows policy currently on disk;
it does not claim that an already-running gateway has reloaded it.
