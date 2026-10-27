# Implementation progress and release checklist

## Milestone 1 — MCP foundations

Implemented Python packaging, real SDK stdio demo/client, harmless fixtures and
fake credentials. The demo independently confines filesystem operations.

Verification: `python -m pytest tests/test_foundations.py -q` (1 passed during
implementation). Manual: `python demo/test_client.py --direct` discovers tools and
reads `hello.txt`; direct fake credential access demonstrates the permissive baseline.

## Milestone 2 — Gateway

Implemented bounded tool discovery, permitted schema-preserving tool listing,
central interception, canonical argument forwarding, and unchanged successful MCP
results. Denials return MCP error results. Transport lifecycle uses SDK contexts.

Verification: `python -m pytest tests/test_integration.py -q`. The main integration
test checks ten denied attempts with zero downstream handler entries, then one
successful safe read. Manual: `python demo/attack_scenarios.py` asserts eight denied
attempts, one safe read, and produces frequency alerts for the dashboard.

## Milestone 3 — Policy enforcement

Implemented strict versioned YAML, default deny, explicit tool/path contracts,
block-over-allow precedence, schema validation, path containment and protected
components, fail-closed evaluation, and disabled shell execution tools.

Verification: `python -m pytest tests/test_policy_engine.py tests/test_path_validator.py -q`.
Manual: add a tool blocking rule, restart, and repeat a previously permitted call.

## Milestone 4 — Monitoring

Implemented durable pre-execution events, payload-free SQLite storage, completion
outcomes, bounded rate detection, and a read-only Streamlit dashboard. The dashboard
test covers empty state, real SQLite events, metrics, and filtering.

Verification: `python -m pytest tests/test_detection.py tests/test_gateway.py tests/test_dashboard.py -q`.
Manual: run the attack client, launch the README dashboard command, and refresh.

## Milestone 5 — Validation and release

Implemented real-process timeout/disconnection tests, invalid-policy startup test,
architecture/policy/threat documentation, install/run instructions, and MIT license.
The initial core suite passed 41 tests. The dashboard's first cold import exceeded
its test harness's 3-second default; the harness now allows 30 seconds. Final
suite results are recorded below.

### Local verification record

- Environment: macOS arm64, Python 3.14, MCP 2.3.0.
- Attack runner: eight blocks with zero executions, followed by an allowed read
  with one execution; frequency run produced ten alert-bearing events.
- `pip check`: no broken requirements.
- `compileall`: source, demo, and tests compiled successfully.
- Final `python -m pytest -q`: **47 passed in 8.96 seconds**. Four dependency
  deprecation warnings originate from Streamlit's pandas chart implementation.
- `python -m pip wheel --no-deps --wheel-dir dist .`: successfully built
  `boba_mcp-0.1.0-py3-none-any.whl`.
- Manual protected client read: valid MCP error result, `Protected credential path`.
- Local environment recovery: macOS marked the editable-install `.pth` file
  hidden, causing Python 3.14 to skip it. Clearing that file's hidden flag restored
  imports before the successful final full-suite run. No import-path workaround
  was added to application code.

### Release checklist

- [x] Real MCP client/server/gateway interoperability.
- [x] Pre-execution blocking evidence and canonical path tests.
- [x] Strict policy loading and fail-closed evaluation/storage behavior.
- [x] Real timeout/disconnection error recording.
- [x] Metadata-only events and bounded frequency alerts.
- [x] Dashboard empty-state, event rendering, and filtering tests.
- [x] README, architecture, threat model, policy semantics, license.
- [x] Final full-suite and package-build results recorded above.
- [ ] Verify Python 3.11 and Linux in release CI (not locally exercised).
- [ ] Human visual dashboard review (automated Streamlit harness covers behavior).
- [ ] Create a reviewed v0.1.0 Git tag and publish distribution if desired.

## Future releases

- **v0.2:** tool schema pinning, description change detection, tool poisoning signals.
- **v0.3:** sensitive-operation approval queues and decision audit trails.
- **v0.4:** Streamable HTTP and authenticated remote agent/server connections.
- **v0.5:** response inspection, prompt injection heuristics, additional behaviors.
- **v1.0:** multiple downstream servers, stronger isolation, SIEM export, centralized policies.

These remain future work; v0.1's transport adapter and centralized interceptor
provide extension points without pre-implementing those systems.
