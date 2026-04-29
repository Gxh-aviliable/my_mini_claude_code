from langchain_core.tools import tool
import subprocess
from pathlib import Path

BLOCKED_COMMANDS = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]


@tool
def bash(command: str) -> str:
    """Run shell command in workspace.

    Args:
        command: Shell command to execute

    Returns:
        Command output (stdout + stderr)
    """
    # Check for dangerous commands
    if any(blocked in command for blocked in BLOCKED_COMMANDS):
        return "Error: Dangerous command blocked for safety"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=120
        )
        output = (result.stdout + result.stderr).strip()
        return output[:50000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (120 seconds limit)"
    except Exception as e:
        return f"Error: {e}"