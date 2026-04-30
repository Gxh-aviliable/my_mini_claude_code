"""Subagent tool for delegating work to specialized agents.

Provides task tool for spawning subagents with limited tool access
to perform isolated exploration or execution work.
"""

from langchain_core.tools import tool
from typing import Optional, List, Dict, Any
from anthropic import Anthropic
import os

from enterprise_agent.config.settings import settings


# Available agent types and their tool sets
AGENT_TYPES = {
    "Explore": ["bash", "read_file"],
    "general-purpose": ["bash", "read_file", "write_file", "edit_file"],
}


def _build_tool_schema(tool_name: str) -> Dict[str, Any]:
    """Build tool schema for subagent."""
    schemas = {
        "bash": {
            "name": "bash",
            "description": "Run a shell command.",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        },
        "read_file": {
            "name": "read_file",
            "description": "Read file contents.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["path"]
            }
        },
        "write_file": {
            "name": "write_file",
            "description": "Write content to file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        },
        "edit_file": {
            "name": "edit_file",
            "description": "Replace exact text in file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        },
    }
    return schemas.get(tool_name)


def _execute_subagent_tool(tool_name: str, tool_input: Dict) -> str:
    """Execute a tool call within subagent context.

    Uses the actual tool implementations from other modules.
    """
    from enterprise_agent.core.agent.tools.file_ops import read_file, write_file, edit_file
    from enterprise_agent.core.agent.tools.shell import bash

    tool_map = {
        "bash": bash,
        "read_file": read_file,
        "write_file": write_file,
        "edit_file": edit_file,
    }

    tool = tool_map.get(tool_name)
    if not tool:
        return f"Unknown tool: {tool_name}"

    # Execute the tool
    try:
        result = tool.invoke(tool_input)
        return str(result)[:50000]  # Limit output size
    except Exception as e:
        return f"Error: {e}"


@tool
def task(prompt: str, agent_type: Optional[str] = "Explore") -> str:
    """Spawn a subagent for isolated exploration or work.

    The subagent operates independently with limited tool access
    and returns a summary of its work.

    Args:
        prompt: The task prompt for the subagent
        agent_type: Type of agent - 'Explore' (read-only) or 'general-purpose' (read/write)

    Returns:
        Summary of subagent's work
    """
    # Validate agent type
    if agent_type not in AGENT_TYPES:
        return f"Error: Unknown agent_type '{agent_type}'. Available: {', '.join(AGENT_TYPES.keys())}"

    # Get tools for this agent type
    tool_names = AGENT_TYPES[agent_type]
    tools = [_build_tool_schema(t) for t in tool_names if _build_tool_schema(t)]

    # Initialize Anthropic client
    client = Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        base_url=os.getenv("ANTHROPIC_BASE_URL")
    )

    # Subagent messages
    sub_messages = [{"role": "user", "content": prompt}]

    # Run subagent loop (max 30 rounds)
    response = None
    for _ in range(30):
        try:
            response = client.messages.create(
                model=settings.MODEL_ID,
                messages=sub_messages,
                tools=tools,
                max_tokens=8000
            )
        except Exception as e:
            return f"Subagent error: {e}"

        sub_messages.append({"role": "assistant", "content": response.content})

        # Check if done
        if response.stop_reason != "tool_use":
            break

        # Execute tool calls
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = _execute_subagent_tool(block.name, block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output
                })

        sub_messages.append({"role": "user", "content": results})

    # Extract final summary
    if response:
        summary_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                summary_parts.append(block.text)
        return "".join(summary_parts) or "(no summary)"

    return "(subagent failed)"