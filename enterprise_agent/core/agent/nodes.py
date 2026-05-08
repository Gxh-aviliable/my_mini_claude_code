"""LangGraph agent nodes for Enterprise Agent.

Each node is an async function that takes state and returns state updates.
Nodes are connected in a StateGraph workflow defined in graph.py.

Node flow:
    init_context -> check_background -> check_inbox -> pre_microcompact -> llm_call
                                                                              |
                         +----------------------------------------------------+
                         |                    |                               |
                    tool_executor         compress_context                END
                         |
                    save_memory
                         |
                    route_after_tool
                         |
               +---------+---------+
               |                   |
          compress_context    pre_microcompact
                                   |
                              llm_call

State persistence (messages, todos, etc.) is handled automatically by
RedisSaver checkpointer — no manual message loading/saving needed.
"""

import asyncio
import json
import logging
import os as _os
import platform
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from enterprise_agent.config.settings import settings
from enterprise_agent.core.agent.context import get_context_manager
from enterprise_agent.core.agent.llm_factory import get_llm
from enterprise_agent.core.agent.state import AgentState
from enterprise_agent.core.agent.tools import ALL_TOOLS

# System prompts for different agent roles
MAIN_SYSTEM_PROMPT = """You are an enterprise-grade AI assistant with access to powerful tools.

## Environment
{environment_info}

## Capabilities
- **Shell execution**: Run commands via `bash` tool
- **File operations**: Read, write, and edit files
- **Task management**: Create and track TODO items with `todo_update`
- **Team coordination**: Spawn and manage teammate agents
- **Background tasks**: Run long-running commands asynchronously
- **Context compression**: Compress conversation history when it gets too long

## Guidelines
1. Use tools when needed to accomplish tasks — don't just describe what to do
2. Manage your work with TODO items for multi-step tasks
3. Be concise and direct in your responses
4. When spawning teammates, provide clear role descriptions and prompts
5. Use background tasks for long-running operations
6. If context gets too long, use the `compress` tool to summarize and continue
7. Use Windows-compatible commands (cmd.exe shell) — avoid bash-isms like `pwd`, `ls`, `tail`, `/workspace` paths, `2>/dev/null`. Use `dir`, `cd /d`, `python` (not python3), and Windows path separators."""


def _build_environment_info() -> str:
    """Build environment info block for system prompt."""
    from enterprise_agent.core.agent.tools.workspace import get_user_workspace
    try:
        workspace = get_user_workspace()
    except Exception:
        workspace = str(Path(_os.getcwd()))
    return (
        f"- OS: {platform.system()} ({platform.release()})\n"
        f"- Shell: cmd.exe (Windows) — use Windows commands like `dir`, `cd /d`, `mkdir` (no -p)\n"
        f"- Workspace: {workspace}\n"
        f"- Python: {platform.python_version()}\n"
        f"- Encoding: utf-8 (PYTHONIOENCODING=utf-8 is auto-set for all commands)"
    )

def _extract_text(content: Any) -> str:
    """Extract plain text from LLM response content, which may be str or content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts) if parts else str(content)
    return str(content)


# LLM retry configuration
MAX_LLM_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds

# Lazy LLM initialization (avoids crash at import time if API key not set)
_llm = None
_llm_with_tools = None


def get_llm_with_tools():
    """Get LLM with tools bound (lazy initialization)."""
    global _llm, _llm_with_tools
    if _llm is None:
        _llm = get_llm()
        _llm_with_tools = _llm.bind_tools(ALL_TOOLS)
    return _llm_with_tools


def _convert_to_langchain_messages(messages: List[Any]) -> List[Any]:
    """Convert messages to LangChain message objects.

    Handles both dict messages and existing LangChain message objects.

    Args:
        messages: List of message dicts or LangChain message objects

    Returns:
        List of LangChain message objects
    """
    result = []
    for msg in messages:
        # If already a LangChain message, use it directly
        if hasattr(msg, "type") and hasattr(msg, "content"):
            result.append(msg)
            continue

        # Otherwise, convert from dict
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role in ("user", "human"):
                result.append(HumanMessage(content=content))
            elif role in ("assistant", "ai"):
                tool_calls = msg.get("tool_calls", [])
                # Preserve original content blocks (e.g., thinking blocks from
                # DeepSeek's thinking mode) if they were stored during conversion.
                content_blocks = msg.get("content_blocks")
                if content_blocks is not None:
                    result.append(AIMessage(content=content_blocks, tool_calls=tool_calls))
                else:
                    result.append(AIMessage(content=content, tool_calls=tool_calls))
            elif role == "system":
                result.append(SystemMessage(content=content))
            elif role == "tool":
                result.append(ToolMessage(
                    content=content,
                    tool_call_id=msg.get("tool_call_id", "")
                ))
            else:
                result.append(HumanMessage(content=content))
        else:
            # Fallback for unknown types
            result.append(HumanMessage(content=str(msg)))

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
            raw_content = msg.content

            # Preserve list-type content (e.g. thinking blocks from
            # DeepSeek/Anthropic extended thinking) as-is.
            # _extract_text() strips thinking blocks, which causes
            # DeepSeek API to return 400: "The `content[].thinking`
            # in the thinking mode must be passed back to the API."
            # Storing the list directly ensures the add_messages
            # reducer round-trips it correctly.
            if isinstance(raw_content, list):
                content = raw_content
            else:
                content = _extract_text(raw_content) if raw_content else ""

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
    """Initialize context node - Reset transient state + inject long-term memory.

    Messages are NOT cleared here — RedisSaver automatically restores
    the previous conversation history from the checkpointer.
    """
    result = {
        "token_count": 0,
        "pending_tool_calls": [],
        "tool_results": {},
        "tool_call_stats": {},
        "round_count": 0,
        "should_compress": False,
        "should_end": False,
        # TodoWrite nag reminder state
        "rounds_without_todo": 0,
        "used_todo_last_round": False,
        "has_open_todos": False,
    }

    # === Chroma 长期记忆检索（仅新会话首条消息） ===
    messages = state.get("messages", [])
    user_id = state.get("user_id")

    # 仅当会话只有 1 条消息（全新会话的第一条用户消息）时注入
    is_new_session = len(messages) == 1

    if is_new_session and user_id:
        last_user_msg = None
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if last_user_msg:
            try:
                from enterprise_agent.memory.long_term import get_long_term_memory
                memory = get_long_term_memory(user_id)
                past_conversations = await memory.search_conversations(
                    query=last_user_msg,
                    n_results=3,
                )

                if past_conversations:
                    # NOTE: This system message is appended by the add_messages
                    # reducer (AgentState.messages), ending up AFTER the current
                    # user message. This is functionally correct because
                    # llm_call_node passes ALL messages to the LLM, including
                    # this context. The MAIN_SYSTEM_PROMPT is inserted at index
                    # 0 during conversion.
                    context_parts = []
                    for conv in past_conversations:
                        role = conv.get("metadata", {}).get("role", "unknown")
                        content = conv.get("content", "")
                        if len(content) > 500:
                            content = content[:500] + "..."
                        context_parts.append(f"[{role}]: {content}")

                    context_text = "\n".join(context_parts)
                    if len(context_text) > 2000:
                        context_text = context_text[:2000] + "..."

                    result["messages"] = [{
                        "role": "user",
                        "content": (
                            "<long_term_memory>\n"
                            "以下是与当前问题相关的历史对话记录，供参考：\n"
                            f"{context_text}\n"
                            "</long_term_memory>"
                        )
                    }]
            except Exception:
                logging.warning("Chroma memory search failed (non-fatal)", exc_info=True)

    return result


async def pre_llm_microcompact_node(state: AgentState) -> Dict[str, Any]:
    """Apply microcompact before LLM call.

    Clears old tool results to prevent token bloat.
    This is the key mechanism from original mini_claude_code.py.
    """
    messages = state.get("messages", [])
    ctx_mgr = get_context_manager()

    # Apply microcompact (use langchain version to handle message objects)
    compacted = ctx_mgr.microcompact_langchain(messages, keep_last=settings.MICROCOMPACT_KEEP_LAST)

    return {"messages": compacted}


async def llm_call_node(state: AgentState) -> Dict[str, Any]:
    """LLM call node - Invoke LLM with tools bound.

    Handles both text responses and tool use requests.
    Intermediate system-level context (memory, background, inbox) uses
    role="user" with XML tags so MAIN_SYSTEM_PROMPT stays the sole SystemMessage.
    """
    messages = state.get("messages", [])

    # Strip any stray system messages from state before conversion.
    # Anthropic API requires all SystemMessage instances to be consecutive
    # at the start — any system-role message in the middle would break.
    # Only MAIN_SYSTEM_PROMPT (injected below) is the allowed SystemMessage.
    messages = [
        m for m in messages
        if not (isinstance(m, dict) and m.get("role") == "system")
        and not (hasattr(m, "type") and getattr(m, "type", "") == "system")
    ]

    # Convert to LangChain format for invocation
    lc_messages = _convert_to_langchain_messages(messages)

    # Insert system prompt as the sole SystemMessage at the beginning.
    # Inject live environment info (OS, shell, workspace, encoding) so the
    # agent doesn't waste rounds discovering the environment.
    lc_messages.insert(0, SystemMessage(content=MAIN_SYSTEM_PROMPT.format(
        environment_info=_build_environment_info()
    )))

    # Log: entering LLM call
    msg_count = len(lc_messages)
    total_chars = sum(len(str(m.content)) if hasattr(m, "content") else 0 for m in lc_messages)
    logging.info(f"[llm_call] {msg_count} messages (~{total_chars} chars, ~{state.get('token_count', 0)} tokens) → invoking LLM...")

    # LLM call with retry on transient failures
    for attempt in range(MAX_LLM_RETRIES):
        try:
            response = await get_llm_with_tools().ainvoke(lc_messages)
            break
        except Exception as e:
            if attempt < MAX_LLM_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logging.warning(
                    f"LLM call failed (attempt {attempt+1}/{MAX_LLM_RETRIES}): {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logging.exception(f"LLM call failed after {MAX_LLM_RETRIES} attempts")
                raise

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
        for tc in tool_calls:
            logging.info(f"[llm_call] → tool: {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)[:200]})")
    else:
        text_preview = str(response.content)[:150] if hasattr(response, "content") and response.content else "(empty)"
        logging.info(f"[llm_call] → text response: {text_preview}")

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

    round_count = state.get("round_count", 0) + 1
    logging.info(f"[llm_call] round {round_count}/{settings.MAX_AGENT_ROUNDS}")

    return {
        "messages": [response_dict],
        "pending_tool_calls": tool_calls,
        "token_count": token_count,
        "round_count": round_count,
    }


# Tools that are safe to retry (read-only, no side effects)
IDEMPOTENT_TOOLS = {
    "read_file", "list_skills", "list_teammates", "list_transcripts",
    "get_transcript", "context_status", "check_background", "read_inbox",
    "task_list", "task_get",
}

# Error patterns that indicate transient failures worth retrying
RETRYABLE_ERROR_PATTERNS = ("timeout", "connection", "rate limit", "try again")

MAX_TOOL_RETRIES = 2


def _should_retry_tool(tool_name: str, error: Exception) -> bool:
    """Only retry idempotent (read-only) tools on transient errors.

    Tools with side effects (write_file, bash, edit_file, etc.) are never
    retried because re-executing them would duplicate the side effect.
    """
    if tool_name not in IDEMPOTENT_TOOLS:
        return False
    error_str = str(error).lower()
    return any(pattern in error_str for pattern in RETRYABLE_ERROR_PATTERNS)


async def tool_executor_node(state: AgentState) -> Dict[str, Any]:
    """Tool executor node - Execute pending tool calls.

    Runs each tool and collects results.
    Special handling for compress tool to trigger compression.
    Tracks TodoWrite usage for nag reminder mechanism.

    Idempotent (read-only) tools are retried on transient errors.
    Side-effect tools (write, bash, etc.) are never retried.
    """
    from enterprise_agent.core.agent.tools.task import get_todo_manager

    results = {}
    tool_map = {t.name: t for t in ALL_TOOLS}
    compress_requested = False
    used_todo = False

    pending = state.get("pending_tool_calls", [])
    tool_call_stats = state.get("tool_call_stats", {}).copy()  # mutable state: copy before modifying
    logging.info(f"[tool_exec] executing {len(pending)} tool(s): {[tc.get('name') for tc in pending]}")

    for tool_call in pending:
        tool_name = tool_call.get("name")
        tool_input = tool_call.get("args", {})
        tool_id = tool_call.get("id", tool_name)

        # Auto-increment tool call stats (framework counts, no LLM hallucination)
        tool_call_stats[tool_name] = tool_call_stats.get(tool_name, 0) + 1

        if tool_name not in tool_map:
            results[tool_id] = f"Unknown tool: {tool_name}"
            logging.warning(f"[tool_exec] unknown tool: {tool_name}")
            continue

        tool = tool_map[tool_name]
        last_error = None

        for attempt in range(MAX_TOOL_RETRIES):
            try:
                # Invoke tool (tools may be sync or async)
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
                    if len(result_str) > settings.TOOL_OUTPUT_MAX_CHARS:
                        result_str = result_str[:settings.TOOL_OUTPUT_MAX_CHARS] + "\n... (truncated, see transcript)"

                results[tool_id] = result_str
                result_preview = result_str[:120].replace("\n", " ")
                logging.info(f"[tool_exec] ✓ {tool_name} ({len(result_str)} chars): {result_preview}...")
                break
            except Exception as e:
                last_error = e
                if attempt < MAX_TOOL_RETRIES - 1 and _should_retry_tool(tool_name, e):
                    delay = 1.0 * (attempt + 1)
                    logging.warning(
                        f"Retrying idempotent tool '{tool_name}' after error: {e} "
                        f"(attempt {attempt+1}/{MAX_TOOL_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                else:
                    results[tool_id] = f"Error executing {tool_name}: {e}"
                    logging.warning(f"[tool_exec] ✗ {tool_name} FAILED: {e}")
                    break

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
        "tool_call_stats": tool_call_stats,  # Framework auto-counted stats
        "should_compress": compress_requested,  # Trigger compression if requested
        "used_todo_last_round": used_todo,
        "has_open_todos": has_open_todos,
    }


async def save_memory_node(state: AgentState) -> Dict[str, Any]:
    """Save memory node - handles TodoWrite nag reminder logic.

    Message persistence is handled automatically by RedisSaver checkpointer.
    This node also injects auto-counted tool_call_stats when the agent
    completes all todos (wrapping up), so the LLM can report accurate
    tool usage counts instead of hallucinating.
    """
    # === TodoWrite nag reminder mechanism (s03) ===
    used_todo = state.get("used_todo_last_round", False)
    rounds_without_todo = state.get("rounds_without_todo", 0)
    rounds_without_todo = 0 if used_todo else rounds_without_todo + 1

    has_open_todos = state.get("has_open_todos", False)
    additional_messages = []

    if has_open_todos and rounds_without_todo >= settings.NAG_REMINDER_THRESHOLD:
        additional_messages.append({
            "role": "user",
            "content": "<reminder>Update your todos. You have open todo items that need status updates.</reminder>"
        })
        rounds_without_todo = 0

    # Inject auto-counted tool stats when agent finishes all todos.
    # The LLM self-reports tool counts unreliably (e.g. 24 vs actual 37).
    # Framework-counted stats are injected once as ground truth.
    tool_stats = state.get("tool_call_stats", {})
    if tool_stats and not has_open_todos and used_todo:
        total = sum(tool_stats.values())
        stats_text = "\n".join(f"- {name}: {count}" for name, count in sorted(tool_stats.items()))
        additional_messages.append({
            "role": "user",
            "content": (
                f"<tool_stats>\n"
                f"Framework-counted tool usage (accurate, use these numbers):\n"
                f"{stats_text}\n"
                f"Total: {total} tool calls\n"
                f"</tool_stats>"
            )
        })

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
    5. Store summary to Chroma as long-term memory
    """
    ctx_mgr = get_context_manager()
    token_count = state.get("token_count", 0)

    # Check if compression needed
    if token_count > settings.TOKEN_THRESHOLD:
        messages = state.get("messages", [])
        session_id = state.get("session_id", "unknown")
        user_id = state.get("user_id")

        # Perform full compression
        compression_result = await ctx_mgr.auto_compact(messages, session_id)

        # Store compression summary to Chroma as long-term memory
        summary = compression_result.get("context_summary")
        if summary and user_id:
            try:
                from enterprise_agent.memory.long_term import get_long_term_memory
                memory = get_long_term_memory(user_id)
                await memory.store_conversation(
                    session_id=session_id,
                    role="system",
                    content=_extract_text(summary),
                    metadata={"type": "session_summary"},
                )
            except Exception:
                logging.warning("Chroma memory store failed during compression (non-fatal)", exc_info=True)

        # Append explicit continuation instruction so the LLM doesn't just
        # echo the summary and stop — it receives a clear prompt to act.
        compressed_msgs = compression_result["compressed_messages"]
        compressed_msgs.append({
            "role": "user",
            "content": "<system-reminder>Context has been compressed. Continue the task immediately. Take the next concrete action using a tool — do NOT summarize or repeat what was in the compressed context.</system-reminder>"
        })

        return {
            "messages": compressed_msgs,
            "context_summary": summary,
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
    user_id = state.get("user_id")

    # Always compress when manually triggered
    compression_result = await ctx_mgr.manual_compress(messages, session_id)

    # Store compression summary to Chroma as long-term memory
    summary = compression_result.get("context_summary")
    if summary and user_id:
        try:
            from enterprise_agent.memory.long_term import get_long_term_memory
            memory = get_long_term_memory(user_id)
            await memory.store_conversation(
                session_id=session_id,
                role="system",
                content=_extract_text(summary),
                metadata={"type": "session_summary"},
            )
        except Exception:
            logging.warning("Chroma memory store failed during manual compression (non-fatal)", exc_info=True)

    return {
        "messages": compression_result["compressed_messages"],
        "context_summary": summary,
        "transcript_path": compression_result["transcript_path"],
        "token_count": compression_result["token_count_reset"],
        "should_compress": False,
        "should_end": True  # End this invocation after manual compress
    }


def route_after_llm(state: AgentState) -> str:
    """Route after LLM call based on state.

    Determines next node based on:
    - Max rounds exceeded -> end
    - Has tool calls -> tool_executor
    - Exceeds token threshold -> compress_context
    - Otherwise -> end
    """
    # Safety valve: stop if agent has been looping too long
    if state.get("round_count", 0) >= settings.MAX_AGENT_ROUNDS:
        logging.warning(f"[route_after_llm] max rounds ({settings.MAX_AGENT_ROUNDS}) reached, ending")
        return "end"

    # Check for tool calls first
    if state.get("pending_tool_calls"):
        return "tool_call"

    # Check for manual compression request (token not yet exceeded threshold)
    if state.get("should_compress") and state.get("token_count", 0) <= settings.TOKEN_THRESHOLD:
        return "manual_compress"

    # Check for auto compression threshold
    if state.get("token_count", 0) > settings.TOKEN_THRESHOLD:
        return "compress"

    return "end"


def route_after_tool(state: AgentState) -> str:
    """Route after tool execution.

    After tools run, we check if:
    - Max rounds exceeded -> end
    - Manual compression was requested via compress tool
    - Auto compression threshold exceeded
    before going back to LLM.
    """
    # Safety valve: stop if agent has been looping too long
    if state.get("round_count", 0) >= settings.MAX_AGENT_ROUNDS:
        logging.warning(f"[route_after_tool] max rounds ({settings.MAX_AGENT_ROUNDS}) reached, ending")
        return "end"

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
                "role": "user",
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
    messages = await bus.read_inbox("lead")

    if messages:
        inbox_text = json.dumps(messages, indent=2)
        return {
            "messages": [{
                "role": "user",
                "content": f"<inbox>\n{inbox_text}\n</inbox>"
            }]
        }

    return {}