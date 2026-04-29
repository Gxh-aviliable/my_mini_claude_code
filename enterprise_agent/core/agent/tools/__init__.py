from langchain_core.tools import Tool

from enterprise_agent.core.agent.tools.file_ops import read_file, write_file, edit_file
from enterprise_agent.core.agent.tools.shell import bash
from enterprise_agent.core.agent.tools.task import todo_update


ALL_TOOLS = [
    read_file,
    write_file,
    edit_file,
    bash,
    todo_update,
]


def get_tools_for_permissions(user_permissions: list) -> list:
    """Filter tools based on user permissions

    Args:
        user_permissions: List of permission strings from JWT

    Returns:
        List of tools the user is allowed to use
    """
    # For now, return all tools
    # In production, filter based on permissions like 'tools:shell', 'tools:advanced'
    return ALL_TOOLS