from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from enterprise_agent.core.agent.state import AgentState
from enterprise_agent.core.agent.nodes import (
    init_context_node,
    load_memory_node,
    llm_call_node,
    tool_executor_node,
    save_memory_node,
    compress_context_node,
    route_after_llm
)


def build_agent_graph():
    """Build LangGraph workflow

    Returns:
        Compiled StateGraph
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("init_context", init_context_node)
    graph.add_node("load_memory", load_memory_node)
    graph.add_node("llm_call", llm_call_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("save_memory", save_memory_node)
    graph.add_node("compress_context", compress_context_node)

    # Define edges
    graph.set_entry_point("init_context")
    graph.add_edge("init_context", "load_memory")
    graph.add_edge("load_memory", "llm_call")

    # Conditional routing after LLM call
    graph.add_conditional_edges(
        "llm_call",
        route_after_llm,
        {
            "tool_call": "tool_executor",
            "compress": "compress_context",
            "end": END
        }
    )

    # Tool execution flow
    graph.add_edge("tool_executor", "save_memory")
    graph.add_edge("save_memory", "llm_call")

    # Context compression flow
    graph.add_edge("compress_context", "llm_call")

    # Compile with checkpointer for persistence
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Global graph instance
agent_graph = build_agent_graph()