from typing import Optional

from langchain_core.tools import tool

from enterprise_agent.config.settings import settings
from enterprise_agent.core.agent.tools.workspace import get_user_workspace, resolve_path


@tool
def read_file(path: str, limit: Optional[int] = None) -> str:
    """Read file contents from workspace.

    Args:
        path: Relative path to file within workspace
        limit: Maximum number of lines to read (optional)

    Returns:
        File contents as string
    """
    try:
        fp = resolve_path(path)
        lines = fp.read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:settings.TOOL_OUTPUT_MAX_CHARS]
    except Exception as e:
        return f"Error: {e}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to file in workspace.

    Args:
        path: Relative path to file within workspace
        content: Content to write

    Returns:
        Success message with bytes written
    """
    try:
        fp = resolve_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


@tool
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace exact text in file.

    Args:
        path: Relative path to file within workspace
        old_text: Exact text to find and replace
        new_text: New text to insert

    Returns:
        Success message or error
    """
    try:
        fp = resolve_path(path)
        content = fp.read_text(encoding="utf-8")
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"