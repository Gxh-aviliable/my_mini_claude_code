"""Subagent tool for delegating work to specialized agents.

Provides task tool for spawning subagents with limited tool access
to perform isolated exploration or execution work.

Supports multi-provider: Anthropic, GLM, DeepSeek, OpenAI.
"""

from langchain_core.tools import tool
from typing import Optional, List, Dict, Any
import asyncio

from enterprise_agent.config.settings import settings
from enterprise_agent.core.agent.llm_factory import get_llm, get_llm_for_subagent


# Available agent types and their tool sets
AGENT_TYPES = {
    "Explore": ["bash", "read_file"],
    "general-purpose": ["bash", "read_file", "write_file", "edit_file"],
}


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


async def _run_subagent_async(prompt: str, agent_type: str) -> str:
    """Run subagent asynchronously using LangChain.

    Supports multi-provider via LLM factory.
    """
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    # Validate agent type
    if agent_type not in AGENT_TYPES:
        return f"Error: Unknown agent_type '{agent_type}'. Available: {', '.join(AGENT_TYPES.keys())}"

    # Get tool names for this agent type
    tool_names = AGENT_TYPES[agent_type]

    # Build LangChain tools
    from langchain_core.tools import Tool
    tools = []
    for name in tool_names:
        if name == "bash":
            tools.append(Tool(name="bash", func=lambda cmd: _execute_subagent_tool("bash", {"command": cmd}), description="Run shell command"))
        elif name == "read_file":
            tools.append(Tool(name="read_file", func=lambda path: _execute_subagent_tool("read_file", {"path": path}), description="Read file"))
        elif name == "write_file":
            tools.append(Tool(name="write_file", func=lambda args: _execute_subagent_tool("write_file", args), description="Write file"))
        elif name == "edit_file":
            tools.append(Tool(name="edit_file", func=lambda args: _execute_subagent_tool("edit_file", args), description="Edit file"))

    # Get LLM and bind tools
    try:
        llm = get_llm()
        llm_with_tools = llm.bind_tools(tools)
    except Exception as e:
        return f"Error initializing LLM: {e}"

    # Subagent messages
    messages = [HumanMessage(content=prompt)]

    # Run subagent loop (max 30 rounds)
    for _ in range(30):
        try:
            response = await llm_with_tools.ainvoke(messages)
        except Exception as e:
            return f"Subagent error: {e}"

        messages.append(response)

        # Check if done (no tool calls)
        if not hasattr(response, "tool_calls") or not response.tool_calls:
            break

        # Execute tool calls
        tool_results = []
        for tool_call in response.tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", "")

            output = _execute_subagent_tool(tool_name, tool_args)
            tool_results.append(ToolMessage(content=output, tool_call_id=tool_id))

        messages.append(HumanMessage(content=tool_results))

    # Extract final summary
    if messages and len(messages) > 0:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            return str(last_msg.content) or "(no summary)"

    return "(subagent failed)"


@tool
def task(prompt: str, agent_type: Optional[str] = "Explore") -> str:
    """Spawn a subagent for isolated exploration or work.

    The subagent operates independently with limited tool access
    and returns a summary of its work.

    Supports multi-provider: Anthropic, GLM, DeepSeek, OpenAI.

    Args:
        prompt: The task prompt for the subagent
        agent_type: Type of agent - 'Explore' (read-only) or 'general-purpose' (read/write)

    Returns:
        Summary of subagent's work
    """
    # Run async subagent in sync context
    try:
        loop = asyncio.get_running_loop()
        # Already in async context - create task
        return asyncio.create_task(_run_subagent_async(prompt, agent_type or "Explore"))
    except RuntimeError:
        # No running loop - run directly
        return asyncio.run(_run_subagent_async(prompt, agent_type or "Explore"))