from typing import Dict, Any

from langchain_anthropic import ChatAnthropic

from enterprise_agent.core.agent.state import AgentState
from enterprise_agent.core.agent.tools import ALL_TOOLS
from enterprise_agent.config.settings import settings


# Initialize LLM
llm = ChatAnthropic(
    model=settings.MODEL_ID,
    api_key=settings.ANTHROPIC_API_KEY
)

# Bind tools to LLM
llm_with_tools = llm.bind_tools(ALL_TOOLS)


async def init_context_node(state: AgentState) -> Dict[str, Any]:
    """Initialize context node - Reset state fields"""
    return {
        "token_count": 0,
        "pending_tool_calls": [],
        "tool_results": {},
        "should_compress": False,
        "should_end": False
    }


async def load_memory_node(state: AgentState) -> Dict[str, Any]:
    """Load memory from Redis"""
    from enterprise_agent.memory.short_term import ShortTermMemory
    from enterprise_agent.db.redis import redis_client

    stm = ShortTermMemory(redis_client)
    messages = await stm.get_messages(state["session_id"])

    return {"messages": messages}


async def llm_call_node(state: AgentState) -> Dict[str, Any]:
    """LLM call node - Invoke LLM with tools"""
    response = await llm_with_tools.ainvoke(state["messages"])

    tool_calls = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_calls = response.tool_calls

    token_count = state.get("token_count", 0)
    usage = getattr(response, "usage_metadata", {})
    token_count += usage.get("total_tokens", 0)

    return {
        "messages": [response],
        "pending_tool_calls": tool_calls,
        "token_count": token_count
    }


async def tool_executor_node(state: AgentState) -> Dict[str, Any]:
    """Tool executor node - Execute pending tool calls"""
    from enterprise_agent.core.agent.tools import ALL_TOOLS

    results = {}
    tool_map = {t.name: t for t in ALL_TOOLS}

    for tool_call in state.get("pending_tool_calls", []):
        tool_name = tool_call.get("name")
        tool_input = tool_call.get("args", {})

        if tool_name in tool_map:
            result = await tool_map[tool_name].ainvoke(tool_input)
            results[tool_call.get("id", tool_name)] = result

    return {"tool_results": results, "pending_tool_calls": []}


async def save_memory_node(state: AgentState) -> Dict[str, Any]:
    """Save memory to Redis"""
    from enterprise_agent.memory.short_term import ShortTermMemory
    from enterprise_agent.db.redis import redis_client

    stm = ShortTermMemory(redis_client)

    # Save latest messages
    for msg in state.get("messages", [])[-2:]:
        role = msg.get("role", "assistant") if isinstance(msg, dict) else "assistant"
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        await stm.append_message(state["session_id"], role, str(content))

    return {}


async def compress_context_node(state: AgentState) -> Dict[str, Any]:
    """Compress context node - Summarize when token threshold exceeded"""
    if state.get("token_count", 0) > settings.TOKEN_THRESHOLD:
        messages = state.get("messages", [])
        summary_prompt = f"Summarize this conversation for context compression:\n{messages[-50:]}"
        summary = await llm.ainvoke([{"role": "user", "content": summary_prompt}])

        return {
            "messages": [{"role": "system", "content": f"[Context compressed]\n{summary.content}"}],
            "context_summary": summary.content,
            "token_count": 0,
            "should_compress": False
        }
    return {"should_compress": False}


def route_after_llm(state: AgentState) -> str:
    """Route after LLM call based on state"""
    if state.get("pending_tool_calls"):
        return "tool_call"
    if state.get("token_count", 0) > settings.TOKEN_THRESHOLD:
        return "compress"
    return "end"