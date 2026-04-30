"""Tool registry for Enterprise Agent.

Imports and registers all available tools for use with LangGraph.
Tools are organized by module:
- file_ops: read_file, write_file, edit_file
- shell: bash
- task: todo_update, task_create, task_get, task_update, task_list, claim_task
- subagent: task (subagent delegation)
- background: background_run, check_background
- skills: load_skill, list_skills, reload_skills
- team: spawn_teammate, list_teammates, send_message, read_inbox,
        broadcast, shutdown_request, plan_approval, idle
- context_tools: compress, list_transcripts, get_transcript, context_status
"""

from langchain_core.tools import Tool

# File operations
from enterprise_agent.core.agent.tools.file_ops import (
    read_file,
    write_file,
    edit_file,
)

# Shell execution
from enterprise_agent.core.agent.tools.shell import bash

# Task management
from enterprise_agent.core.agent.tools.task import (
    todo_update,
    task_create,
    task_get,
    task_update,
    task_list,
    claim_task,
)

# Subagent delegation
from enterprise_agent.core.agent.tools.subagent import task as subagent_task

# Background tasks
from enterprise_agent.core.agent.tools.background import (
    background_run,
    check_background,
)

# Skills
from enterprise_agent.core.agent.tools.skills import (
    load_skill,
    list_skills,
    reload_skills,
)

# Team collaboration
from enterprise_agent.core.agent.tools.team import (
    spawn_teammate,
    list_teammates,
    send_message,
    read_inbox,
    broadcast,
    shutdown_request,
    plan_approval,
    idle,
)

# Context management
from enterprise_agent.core.agent.tools.context_tools import (
    compress,
    list_transcripts,
    get_transcript,
    context_status,
)


# === Tool Registry ===

ALL_TOOLS = [
    # File operations
    read_file,
    write_file,
    edit_file,

    # Shell
    bash,

    # Task management
    todo_update,
    task_create,
    task_get,
    task_update,
    task_list,
    claim_task,

    # Subagent
    subagent_task,

    # Background
    background_run,
    check_background,

    # Skills
    load_skill,
    list_skills,
    reload_skills,

    # Team
    spawn_teammate,
    list_teammates,
    send_message,
    read_inbox,
    broadcast,
    shutdown_request,
    plan_approval,
    idle,

    # Context management
    compress,
    list_transcripts,
    get_transcript,
    context_status,
]


def get_tools_for_permissions(user_permissions: list) -> list:
    """Filter tools based on user permissions.

    Args:
        user_permissions: List of permission strings from JWT

    Returns:
        List of tools the user is allowed to use
    """
    # Permission mapping
    # Format: 'tools:<category>' grants access to that category
    permission_map = {
        "tools:file": [read_file, write_file, edit_file],
        "tools:shell": [bash],
        "tools:task": [todo_update, task_create, task_get, task_update, task_list, claim_task],
        "tools:subagent": [subagent_task],
        "tools:background": [background_run, check_background],
        "tools:skills": [load_skill, list_skills, reload_skills],
        "tools:team": [spawn_teammate, list_teammates, send_message, read_inbox, broadcast, shutdown_request, plan_approval, idle],
        "tools:context": [compress, list_transcripts, get_transcript, context_status],
        "tools:all": ALL_TOOLS,
    }

    # If no permissions, return basic tools (file + task + context)
    if not user_permissions:
        return [
            read_file, write_file, edit_file,
            todo_update, task_create, task_get, task_update, task_list,
            load_skill, list_skills,
            compress, context_status
        ]

    # Collect tools for each permission
    allowed_tools = []
    for perm in user_permissions:
        if perm in permission_map:
            allowed_tools.extend(permission_map[perm])

    # Remove duplicates while preserving order
    seen = set()
    unique_tools = []
    for tool in allowed_tools:
        if tool.name not in seen:
            seen.add(tool.name)
            unique_tools.append(tool)

    return unique_tools


def get_tool_by_name(name: str):
    """Get a specific tool by name.

    Args:
        name: Tool name

    Returns:
        Tool function or None if not found
    """
    for tool in ALL_TOOLS:
        if tool.name == name:
            return tool
    return None