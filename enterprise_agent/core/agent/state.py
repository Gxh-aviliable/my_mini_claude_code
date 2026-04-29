from typing import TypedDict, List, Dict, Any, Optional, Annotated
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """LangGraph代理状态定义

    包含消息历史、用户信息、任务追踪、工具执行状态等。
    """

    # 消息历史（LangGraph自动合并）
    messages: Annotated[List[Dict], add_messages]

    # 用户和会话信息
    session_id: str
    user_id: int

    # 任务追踪
    current_task: Optional[Dict[str, Any]]
    todos: List[Dict[str, Any]]

    # 上下文管理
    context_summary: Optional[str]
    token_count: int

    # 工具执行
    pending_tool_calls: List[Dict[str, Any]]
    tool_results: Dict[str, Any]

    # 子代理
    sub_agents: Dict[str, Any]

    # 记忆引用
    short_term_memory_ref: Optional[str]
    long_term_memory_refs: List[str]

    # 工作流控制
    should_compress: bool
    should_end: bool