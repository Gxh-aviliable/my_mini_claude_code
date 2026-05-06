import shlex
import subprocess
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from enterprise_agent.config.settings import settings
from enterprise_agent.core.agent.tools.workspace import get_user_workspace

BLOCKED_PATTERNS = [
    "rm -rf /", "rm -rf /*", "sudo ", "shutdown", "reboot", "mkfs",
    "dd if=", ":(){ :|:& };:", "chmod -R 777 /",
    "python -c", "python3 -c", "base64", "| sh", "| bash",
    "> /dev/", "wget ", "curl ",
]

BLOCKED_BINARIES = {"rm", "sudo", "shutdown", "reboot", "mkfs", "dd"}


def validate_command(command: str) -> Optional[str]:
    """Return error message if command is dangerous, None if OK."""
    cmd_lower = command.lower().strip()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return f"Blocked: command contains '{pattern}'"
    # Block path variants of dangerous binaries
    try:
        parts = shlex.split(command)
        if parts:
            cmd_name = Path(parts[0]).name
            if cmd_name in BLOCKED_BINARIES:
                return f"Blocked: '{cmd_name}' is not allowed"
    except ValueError:
        pass
    return None


@tool
def bash(command: str) -> str:
    """Run shell command in workspace.

    Args:
        command: Shell command to execute

    Returns:
        Command output (stdout + stderr)
    """
    error = validate_command(command)
    if error:
        return f"Error: {error}"

    try:
        workdir = get_user_workspace()
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=settings.COMMAND_TIMEOUT_SECONDS
        )
        output = (result.stdout + result.stderr).strip()
        return output[:settings.TOOL_OUTPUT_MAX_CHARS] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out ({settings.COMMAND_TIMEOUT_SECONDS} seconds limit)"
    except Exception as e:
        return f"Error: {e}"
