"""No command execution tools are supported in v0.1."""

PROHIBITED_TOOLS = frozenset({"execute_command", "run_shell", "shell_exec"})


def prohibited(tool: str) -> bool:
    return tool.casefold() in PROHIBITED_TOOLS
