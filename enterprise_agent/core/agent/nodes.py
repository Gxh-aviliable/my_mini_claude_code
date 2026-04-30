"""LangGraph agent nodes for Enterprise Agent.

Each node is an async function that takes state and returns state updates.
Nodes are connected in a StateGraph workflow defined in graph.py.

Node flow:
    init_context -> load_memory -> llm_call -> route_after_llm
                                            -> tool_executor -> save_memory -> llm_call
                                            -> compress_context -> llm_call
                                            -> END
"""

import json
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from enterprise_agent.core.agent.state import AgentState
from enterprise_agent.core.agent.tools import ALL_TOOLS
from enterprise_agent.core.agent.context import get_context_manager, get_transcript_manager
from enterprise_agent.core.agent.llm_factory import get_llm
from enterprise_agent.config.settings import settings


# Initialize LLM using factory (supports Anthropic, GLM, DeepSeek, OpenAI)
llm = get_llm()

# Bind tools to LLM
llm_with_tools = llm.bind_tools(ALL_TOOLS)


def _convert_to_langchain_messages(messages: List[Dict]) -> List[Any]:
    """Convert dict messages to LangChain message objects.

    Args:
        messages: List of message dicts

    Returns:
        List of LangChain message objects
    """
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        elif role == "system":
            result.append(SystemMessage(content=content))
        elif role == "tool":
            result.append(ToolMessage(
                content=content,
                tool_call_id=msg.get("tool_call_id", "")
            ))
        else:
            result.append(HumanMessage(content=content))

    return result


def _convert_from_langchain_messages(messages: List[Any]) -> List[Dict]:
    """Convert LangChain message objects to dicts.

    Args:
        messages: List of LangChain messages

    Returns:
        List of message dicts
    """
    result = []
    for msg in messages:
        if hasattr(msg, "type"):
            role = msg.type
            content = str(msg.content) if msg.content else ""
            tool_call_id = getattr(msg, "tool_call_id", None)

            entry = {"role": role, "content": content}
            if tool_call_id:
                entry["tool_call_id"] = tool_call_id

            # Extract tool calls from AIMessage
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {})
                    }
                    for tc in msg.tool_calls
                ]

            result.append(entry)
        elif isinstance(msg, dict):
            result.append(msg)
        else:
            result.append({"role": "unknown", "content": str(msg)})

    return result


async def init_context_node(state: AgentState) -> Dict[str, Any]:
    """Initialize context node - Reset state fields for new request.

    This node prepares the state for a fresh agent invocation.
    """
    return {
        "token_count": 0,
        "pending_tool_calls": [],
        "tool_results": {},
        "should_compress": False,
        "should_end": False,
        "messages": [],  # Will be populated by load_memory
        # TodoWrite nag reminder state
        "rounds_without_todo": 0,
        "used_todo_last_round": False,
        "has_open_todos": False,
    }


async def load_memory_node(state: AgentState) -> Dict[str, Any]:
    """Load memory from Redis.

    Retrieves conversation history from short-term memory.
    """
    from enterprise_agent.memory.short_term import ShortTermMemory
    from enterprise_agent.db.redis import redis_client

    stm = ShortTermMemory(redis_client)
    messages = await stm.get_messages(state["session_id"])

    # Apply microcompact to loaded messages to prevent bloat
    ctx_mgr = get_context_manager()
    messages = ctx_mgr.microcompact(messages, keep_last=3)

    return {"messages": messages}


async def pre_llm_microcompact_node(state: AgentState) -> Dict[str, Any]:
    """Apply microcompact before LLM call.

    Clears old tool results to prevent token bloat.
    This is the key mechanism from original mini_claude_code.py.
    """
    messages = state.get("messages", [])
    ctx_mgr = get_context_manager()

    # Apply microcompact
    compacted = ctx_mgr.microcompact(messages, keep_last=3)

    return {"messages": compacted}


async def llm_call_node(state: AgentState) -> Dict[str, Any]:
    """LLM call node - Invoke LLM with tools bound.

    Handles both text responses and tool use requests.
    """
    messages = state.get("messages", [])

    # Convert to LangChain format for invocation
    lc_messages = _convert_to_langchain_messages(messages)

    response = await llm_with_tools.ainvoke(lc_messages)

    # Extract tool calls if present
    tool_calls = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_calls = [
            {
                "id": tc.get("id", ""),
                "name": tc.get("name", ""),
                "args": tc.get("args", {})
            }
            for tc in response.tool_calls
        ]

    # Track token usage
    token_count = state.get("token_count", 0)
    usage = getattr(response, "usage_metadata", {})
    if usage:
        token_count += usage.get("total_tokens", 0)
    else:
        # Estimate if not provided
        ctx_mgr = get_context_manager()
        token_count += ctx_mgr.estimate_tokens([response])

    # Convert response back to dict format
    response_dict = _convert_from_langchain_messages([response])[0]

    return {
        "messages": [response_dict],
        "pending_tool_calls": tool_calls,
        "token_count": token_count
    }


async def tool_executor_node(state: AgentState) -> Dict[str, Any]:
    """Tool executor node - Execute pending tool calls.

    Runs each tool and collects results.
    Special handling for compress tool to trigger compression.
    Tracks TodoWrite usage for nag reminder mechanism.
    """
    from enterprise_agent.core.agent.tools import ALL_TOOLS, get_tool_by_name
    from enterprise_agent.core.agent.tools.task import get_todo_manager

    results = {}
    tool_map = {t.name: t for t in ALL_TOOLS}
    compress_requested = False
    used_todo = False

    for tool_call in state.get("pending_tool_calls", []):
        tool_name = tool_call.get("name")
        tool_input = tool_call.get("args", {})
        tool_id = tool_call.get("id", tool_name)

        if tool_name in tool_map:
            try:
                # Invoke tool (tools may be sync or async)
                tool = tool_map[tool_name]
                if hasattr(tool, "ainvoke"):
                    result = await tool.ainvoke(tool_input)
                else:
                    result = tool.invoke(tool_input)

                # Track TodoWrite usage for nag reminder
                if tool_name == "todo_update":
                    used_todo = True

                # Special handling for compress tool
                if tool_name == "compress":
                    compress_requested = True
                    result_str = str(result)
                else:
                    # Limit output size
                    result_str = str(result)
                    if len(result_str) > 50000:
                        result_str = result_str[:50000] + "\n... (truncated, see transcript)"

                results[tool_id] = result_str
            except Exception as e:
                results[tool_id] = f"Error executing {tool_name}: {e}"
        else:
            results[tool_id] = f"Unknown tool: {tool_name}"

    # Build tool result messages
    tool_result_messages = []
    for tool_id, result in results.items():
        tool_result_messages.append({
            "role": "tool",
            "content": result,
            "tool_call_id": tool_id
        })

    # Check if there are open todos for nag reminder
    todo_mgr = get_todo_manager()
    has_open_todos = todo_mgr.has_open_items()

    return {
        "tool_results": results,
        "pending_tool_calls": [],
        "messages": tool_result_messages,
        "should_compress": compress_requested,  # Trigger compression if requested
        "used_todo_last_round": used_todo,
        "has_open_todos": has_open_todos,
    }


async def save_memory_node(state: AgentState) -> Dict[str, Any]:
    """Save memory to Redis.

    Persists conversation history to short-term memory.
    Also handles TodoWrite nag reminder mechanism (s03).
    """
    from enterprise_agent.memory.short_term import ShortTermMemory
    from enterprise_agent.db.redis import redis_client

    stm = ShortTermMemory(redis_client)

    # Save latest messages (assistant + tool results)
    messages = state.get("messages", [])
    for msg in messages[-4:]:  # Save last few messages
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        await stm.append_message(state["session_id"], role, content)

    # === TodoWrite nag reminder mechanism (s03) ===
    # Update rounds_without_todo counter
    used_todo = state.get("used_todo_last_round", False)
    rounds_without_todo = state.get("rounds_without_todo", 0)
    rounds_without_todo = 0 if used_todo else rounds_without_todo + 1

    # Check if we need to add nag reminder
    has_open_todos = state.get("has_open_todos", False)
    additional_messages = []

    if has_open_todos and rounds_without_todo >= 3:
        # Add nag reminder message
        additional_messages.append({
            "role": "user",
            "content": "<reminder>Update your todos. You have open todo items that need status updates.</reminder>"
        })
        # Reset counter after reminder
        rounds_without_todo = 0

    return {
        "rounds_without_todo": rounds_without_todo,
        "messages": additional_messages,
    }


async def compress_context_node(state: AgentState) -> Dict[str, Any]:
    """Compress context node - Full summarization when threshold exceeded.

    This implements the auto-compact mechanism:
    1. Check token threshold
    2. Save transcript to file
    3. Generate summary via LLM
    4. Replace messages with summary
    """
    ctx_mgr = get_context_manager()
    token_count = state.get("token_count", 0)

    # Check if compression needed
    if token_count > settings.TOKEN_THRESHOLD:
        messages = state.get("messages", [])
        session_id = state.get("session_id", "unknown")

        # Perform full compression
        compression_result = await ctx_mgr.auto_compact(messages, session_id)

        return {
            "messages": compression_result["compressed_messages"],
            "context_summary": compression_result["context_summary"],
            "transcript_path": compression_result["transcript_path"],
            "token_count": compression_result["token_count_reset"],
            "should_compress": False
        }

    return {"should_compress": False}


async def manual_compress_node(state: AgentState) -> Dict[str, Any]:
    """Manual compression node - Triggered by compress tool.

    Always performs compression regardless of threshold.
    """
    ctx_mgr = get_context_manager()
    messages = state.get("messages", [])
    session_id = state.get("session_id", "unknown")

    # Always compress when manually triggered
    compression_result = await ctx_mgr.manual_compress(messages, session_id)

    return {
        "messages": compression_result["compressed_messages"],
        "context_summary": compression_result["context_summary"],
        "transcript_path": compression_result["transcript_path"],
        "token_count": compression_result["token_count_reset"],
        "should_compress": False,
        "should_end": True  # End this invocation after manual compress
    }


def route_after_llm(state: AgentState) -> str:
    """Route after LLM call based on state.

    Determines next node based on:
    - Has tool calls -> tool_executor
    - Exceeds token threshold -> compress_context
    - Otherwise -> end
    """
    # Check for tool calls first
    if state.get("pending_tool_calls"):
        return "tool_call"

    # Check for manual compression request
    if state.get("should_compress") and not state.get("token_count", 0) > settings.TOKEN_THRESHOLD:
        return "manual_compress"

    # Check for auto compression threshold
    if state.get("token_count", 0) > settings.TOKEN_THRESHOLD:
        return "compress"

    return "end"


def route_after_tool(state: AgentState) -> str:
    """Route after tool execution.

    After tools run, we check if:
    - Manual compression was requested via compress tool
    - Auto compression threshold exceeded
    before going back to LLM.
    """
    # Check for manual compression request first
    if state.get("should_compress"):
        return "manual_compress"

    token_count = state.get("token_count", 0)

    # Check threshold after tool execution (tool outputs can be large)
    if token_count > settings.TOKEN_THRESHOLD:
        return "compress"

    return "llm_call"


async def check_background_node(state: AgentState) -> Dict[str, Any]:
    """Check background task notifications.

    Drains completed background task results and injects into context.
    """
    from enterprise_agent.core.agent.tools.background import get_background_manager

    bg_mgr = get_background_manager()
    notifications = bg_mgr.drain_notifications()

    if notifications:
        notification_text = "\n".join(
            f"[Background:{n['task_id']}] {n['status']}: {n['result'][:500]}"
            for n in notifications
        )
        return {
            "messages": [{
                "role": "system",
                "content": f"<background-results>\n{notification_text}\n</background-results>"
            }]
        }

    return {}


async def check_inbox_node(state: AgentState) -> Dict[str, Any]:
    """Check inbox for messages from teammates.

    Reads and drains the lead agent's inbox.
    """
    from enterprise_agent.core.agent.tools.team import get_message_bus

    bus = get_message_bus()
    messages = bus.read_inbox("lead")

    if messages:
        inbox_text = json.dumps(messages, indent=2)
        return {
            "messages": [{
                "role": "system",
                "content": f"<inbox>\n{inbox_text}\n</inbox>"
            }]
        }

    return {}