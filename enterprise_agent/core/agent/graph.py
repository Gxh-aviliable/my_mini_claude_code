"""LangGraph agent workflow definition.

Builds the StateGraph that orchestrates the agent's behavior:

    init_context -> pre_microcompact -> load_memory -> llm_call -> route_after_llm
                                                                         |
                         +-----------------------------------------------+
                         |                    |                          |
                    tool_executor         compress_context           END
                         |                    |
                    save_memory          llm_call
                         |
                    route_after_tool
                         |
               +---------+---------+
               |                   |
          compress_context      llm_call
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from enterprise_agent.core.agent.state import AgentState
from enterprise_agent.core.agent.nodes import (
    init_context_node,
    load_memory_node,
    pre_llm_microcompact_node,
    llm_call_node,
    tool_executor_node,
    save_memory_node,
    compress_context_node,
    manual_compress_node,
    check_background_node,
    check_inbox_node,
    route_after_llm,
    route_after_tool
)


def build_agent_graph():
    """Build LangGraph workflow.

    The graph implements:
    - Pre-LLM microcompact to prevent tool output bloat
    - Conditional routing after LLM (tool_call / compress / end)
    - Post-tool routing with threshold check
    - Manual compression support
    - Background task notification injection
    - Inbox message checking

    Returns:
        Compiled StateGraph with MemorySaver checkpointer
    """
    graph = StateGraph(AgentState)

    # === Add Nodes ===

    # Entry and initialization
    graph.add_node("init_context", init_context_node)
    graph.add_node("load_memory", load_memory_node)

    # Pre-LLM microcompact (key mechanism from original)
    graph.add_node("pre_microcompact", pre_llm_microcompact_node)

    # Core LLM call
    graph.add_node("llm_call", llm_call_node)

    # Tool execution
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("save_memory", save_memory_node)

    # Compression nodes
    graph.add_node("compress_context", compress_context_node)
    graph.add_node("manual_compress", manual_compress_node)

    # Optional: Background and inbox checks
    graph.add_node("check_background", check_background_node)
    graph.add_node("check_inbox", check_inbox_node)

    # === Define Edges ===

    # Entry flow
    graph.set_entry_point("init_context")
    graph.add_edge("init_context", "load_memory")

    # Pre-processing before LLM
    graph.add_edge("load_memory", "check_background")  # Inject background results
    graph.add_edge("check_background", "check_inbox")   # Inject inbox messages
    graph.add_edge("check_inbox", "pre_microcompact")   # Apply microcompact
    graph.add_edge("pre_microcompact", "llm_call")      # Then call LLM

    # Conditional routing after LLM
    graph.add_conditional_edges(
        "llm_call",
        route_after_llm,
        {
            "tool_call": "tool_executor",
            "compress": "compress_context",
            "manual_compress": "manual_compress",
            "end": END
        }
    )

    # Tool execution flow
    graph.add_edge("tool_executor", "save_memory")
    graph.add_conditional_edges(
        "save_memory",
        route_after_tool,
        {
            "compress": "compress_context",
            "manual_compress": "manual_compress",
            "llm_call": "llm_call"
        }
    )

    # Compression flow - back to LLM with compressed context
    graph.add_edge("compress_context", "llm_call")

    # Manual compress ends the invocation
    graph.add_edge("manual_compress", END)

    # Compile with checkpointer for persistence
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def build_simple_agent_graph():
    """Build simplified LangGraph workflow without background/inbox checks.

    This is a simpler version for basic usage:

    init_context -> load_memory -> llm_call -> route
                                         -> tool_executor -> save -> llm_call
                                         -> compress -> llm_call
                                         -> END

    Returns:
        Compiled StateGraph
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("init_context", init_context_node)
    graph.add_node("load_memory", load_memory_node)
    graph.add_node("pre_microcompact", pre_llm_microcompact_node)
    graph.add_node("llm_call", llm_call_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("save_memory", save_memory_node)
    graph.add_node("compress_context", compress_context_node)

    # Entry flow
    graph.set_entry_point("init_context")
    graph.add_edge("init_context", "load_memory")
    graph.add_edge("load_memory", "pre_microcompact")
    graph.add_edge("pre_microcompact", "llm_call")

    # Conditional routing after LLM
    graph.add_conditional_edges(
        "llm_call",
        route_after_llm,
        {
            "tool_call": "tool_executor",
            "compress": "compress_context",
            "manual_compress": END,  # Simplified: manual compress just ends
            "end": END
        }
    )

    # Tool flow
    graph.add_edge("tool_executor", "save_memory")
    graph.add_conditional_edges(
        "save_memory",
        route_after_tool,
        {
            "compress": "compress_context",
            "manual_compress": END,  # Simplified: manual compress just ends
            "llm_call": "llm_call"
        }
    )

    # Compress back to LLM
    graph.add_edge("compress_context", "llm_call")

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Global graph instance (use full version by default)
agent_graph = build_agent_graph()

# Alternative simple graph
simple_agent_graph = build_simple_agent_graph()