# Enterprise Agent 代码阅读指南

本文档为重构项目提供循序渐进的代码阅读路径，帮助理解整个系统的实现。

---

## 阅读路径概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        代码阅读路径                                       │
│                                                                         │
│  Stage 1: 配置入口                                                       │
│  ┌─────────────┐    ┌─────────────┐                                     │
│  │ settings.py │───▶│ api/main.py │                                     │
│  └─────────────┘    └─────────────┘                                     │
│                            │                                            │
│                            ▼                                            │
│  Stage 2: 核心Agent                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │ state.py    │───▶│ graph.py    │───▶│ nodes.py    │                 │
│  │ (数据结构)  │    │ (工作流图)  │    │ (节点实现)  │                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│                            │                                            │
│                            ▼                                            │
│  Stage 3: 工具系统                                                       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │__init__.py  │───▶│ file_ops.py │───▶│ shell.py    │───▶ task.py ... │
│  │ (工具注册)  │    │ (基础工具)  │    │ (命令执行)  │                  │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│                            │                                            │
│                            ▼                                            │
│  Stage 4-7: 上下文 → API → 支撑 → 对照原始                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Stage 1: 配置与入口（了解项目骨架）

### 文件列表

| 序号 | 文件 | 说明 |
|------|------|------|
| 1 | `config/settings.py` | 所有配置项、多模型配置、Chroma 配置 |
| 2 | `api/main.py` | FastAPI 入口，路由注册，lifespan 启动 Chroma |

### 阅读重点

**settings.py**：
- 了解多模型配置：`LLM_PROVIDER`, `LLM_API_KEY`, `MODEL_ID`
- 了解 Chroma 配置：`CHROMA_PERSIST_DIR`, `EMBEDDING_MODEL`
- 重点看 `get_effective_api_key()`, `get_effective_base_url()`, `get_effective_model_id()`
- 理解 Pydantic BaseSettings 如何从 `.env` 加载配置

**main.py**：
- 看 `lifespan()` 函数如何初始化 Chroma (`init_chroma()`)
- 理解路由注册顺序：auth → chat → sessions
- 看 CORS、中间件的配置

---

## Stage 2: 核心 Agent 工作流（理解主循环）

### 文件列表

| 序号 | 文件 | 说明 |
|------|------|------|
| 3 | `core/agent/state.py` | AgentState 状态定义 |
| 4 | `core/agent/graph.py` | LangGraph 工作流构建 |
| 5 | `core/agent/nodes.py` | 节点函数具体实现 |
| 6 | `core/agent/llm_factory.py` | **新增** LLM 工厂函数（多模型支持） |

### 阅读顺序

#### 1. state.py → 先看数据结构

```python
class AgentState(TypedDict):
    # 消息历史（LangGraph自动合并）
    messages: Annotated[List[Dict], add_messages]

    # 用户和会话信息
    session_id: str
    user_id: int

    # 上下文管理
    token_count: int
    should_compress: bool
    transcript_path: Optional[str]

    # 工具执行
    pending_tool_calls: List[Dict]
    tool_results: Dict

    # TodoWrite nag reminder
    rounds_without_todo: int
    used_todo_last_round: bool
    has_open_todos: bool
```

**理解要点**：状态是 LangGraph 工作流的核心，所有节点通过读写状态来协作。

---

#### 2. graph.py → 理解工作流图

```python
def build_agent_graph():
    graph = StateGraph(AgentState)

    # === 节点定义 ===
    graph.add_node("init_context", init_context_node)
    graph.add_node("load_memory", load_memory_node)
    graph.add_node("pre_microcompact", pre_llm_microcompact_node)
    graph.add_node("llm_call", llm_call_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("save_memory", save_memory_node)
    graph.add_node("compress_context", compress_context_node)

    # === 流程连接 ===
    graph.set_entry_point("init_context")
    graph.add_edge("init_context", "load_memory")
    graph.add_edge("load_memory", "check_background")
    graph.add_edge("check_background", "check_inbox")
    graph.add_edge("check_inbox", "pre_microcompact")
    graph.add_edge("pre_microcompact", "llm_call")

    # === 条件路由 ===
    graph.add_conditional_edges(
        "llm_call",
        route_after_llm,
        {"tool_call": "tool_executor", "compress": "compress_context", "end": END}
    )

    return graph.compile(checkpointer=MemorySaver())
```

**理解要点**：
- 节点是处理函数，边是流转路径
- 条件路由根据状态决定下一步
- MemorySaver 作为 checkpointer 持久化状态

---

#### 3. nodes.py → 逐个节点深入

按执行顺序阅读：

| 序号 | 节点函数 | 功能 | 关键逻辑 |
|------|----------|------|----------|
| 1 | `init_context_node` | 初始化状态 | 重置 token_count、pending_tool_calls、nag reminder 字段 |
| 2 | `load_memory_node` | 从 Redis 加载历史 | 调用 ShortTermMemory.get_messages() |
| 3 | `check_background_node` | 注入后台任务通知 | BackgroundManager.drain_notifications() |
| 4 | `check_inbox_node` | 注入 inbox 消息 | AsyncMessageBus.read_inbox("lead") |
| 5 | `pre_llm_microcompact_node` | 清理旧工具结果 | ContextManager.microcompact(keep_last=3) |
| 6 | `llm_call_node` | 核心：调用 LLM | **使用 get_llm()**，llm_with_tools.ainvoke() |
| 7 | `tool_executor_node` | 执行工具调用 | 遍历 pending_tool_calls，追踪 todo_update 使用 |
| 8 | `save_memory_node` | 保存 + nag reminder | stm.append_message()，TodoWrite 提醒逻辑 |
| 9 | `compress_context_node` | 自动压缩 | token_count > threshold 时触发 |
| 10 | `route_after_llm` | 条件路由 | pending_tool_calls → tool_executor，threshold → compress |
| 11 | `route_after_tool` | 工具后路由 | should_compress → manual_compress，否则 → llm_call |

**重点理解多模型支持**：
```python
# nodes.py 第 16-22 行
from enterprise_agent.core.agent.llm_factory import get_llm

llm = get_llm()  # 根据 LLM_PROVIDER 返回对应的模型
llm_with_tools = llm.bind_tools(ALL_TOOLS)
```

---

#### 4. llm_factory.py → 多模型工厂（新增）

```python
def get_llm() -> BaseChatModel:
    """根据 LLM_PROVIDER 配置返回对应的 LLM"""
    provider = settings.LLM_PROVIDER

    if provider == "anthropic":
        return ChatAnthropic(...)
    elif provider == "glm":
        return ChatOpenAI(base_url="https://open.bigmodel.cn/api/paas/v4", ...)
    elif provider == "deepseek":
        return ChatOpenAI(base_url="https://api.deepseek.com", ...)
```

---

## Stage 3: 工具系统（理解能力扩展）

### 文件列表

| 序号 | 文件 | 说明 |
|------|------|------|
| 6 | `core/agent/tools/__init__.py` | 工具注册总览 |
| 7 | `core/agent/tools/file_ops.py` | 读/写/编辑文件 |
| 8 | `core/agent/tools/shell.py` | Bash 命令执行 |
| 9 | `core/agent/tools/task.py` | 任务管理 |
| 10 | `core/agent/tools/subagent.py` | 子代理委托 |
| 11 | `core/agent/tools/background.py` | 后台任务 |
| 12 | `core/agent/tools/skills.py` | 技能加载 |
| 13 | `core/agent/tools/context_tools.py` | 上下文工具 |
| 14 | `core/agent/tools/team.py` | 团队协作 |

### 阅读重点

#### __init__.py → 先看全局

```python
ALL_TOOLS = [
    read_file, write_file, edit_file,  # 文件
    bash,                              # Shell
    todo_update, task_create, ...,     # 任务
    subagent_task,                     # 子代理
    background_run, check_background,  # 后台
    load_skill, list_skills,           # 技能
    spawn_teammate, send_message, ..., # 团队
    compress, list_transcripts, ...,   # 上下文
]

permission_map = {
    "tools:file": [read_file, write_file, edit_file],
    "tools:shell": [bash],
    "tools:task": [todo_update, task_create, ...],
    ...
}

def get_tools_for_permissions(user_permissions):
    # 根据 JWT 权限过滤可用工具
```

---

#### task.py → 双层任务系统

理解两个管理器的区别：

| 类 | 存储位置 | 用途 | 特点 |
|------|----------|------|------|
| `TodoManager` | 内存 | 短期清单 | 最多20项，仅1个in_progress |
| `TaskManager` | .tasks/*.json | 持久任务 | 支持依赖(blockedBy)，跨会话 |

关键方法：
```python
# TodoManager
update(items)        # 更新清单，返回渲染结果
has_open_items()    # 检查是否有未完成项（用于 nag reminder）

# TaskManager
create(subject)     # 创建任务，返回 JSON
get(task_id)        # 获取详情
update(task_id, status, add_blocked_by, ...)  # 更新状态/依赖
claim(task_id, owner)  # 认领任务
```

---

#### team.py → 最复杂的模块

按类逐步阅读：

```
AsyncMessageBus          ← 消息传递
    ├── send()           # 发送消息到 inbox
    ├── read_inbox()     # 读取并清空 inbox
    └── broadcast()      # 广播消息

TeammateConfig           ← 配置持久化
    ├── load/save()      # .team/config.json
    └── update_member_status()

TeammateRunner           ← 核心运行器
    ├── start()          # 创建 asyncio.Task
    ├── _run_loop()      # 主循环：Work → Idle → repeat
    ├── _work_phase()    # 处理消息，调用LLM，执行工具
    ├── _idle_phase()    # 轮询inbox，自动认领任务
    └── _claim_task()    # 认领未分配任务
```

重点理解 **Work-Idle 循环**：

```
Work Phase (最多50轮):
    1. 检查 inbox → 处理 shutdown_request / 消息
    2. Microcompact 清理上下文
    3. LLM 调用 + 工具绑定
    4. 工具执行 (idle → 进入 Idle Phase)
    5. 继续或结束

Idle Phase (最多60秒):
    1. 每5秒轮询 inbox
    2. 检查未认领任务 (pending + no owner + no blockedBy)
    3. 自动认领 → 恢复 Work Phase
    4. 无任务 → 超时后 shutdown
```

---

## Stage 4: 上下文管理（理解压缩机制）

### 文件

| 序号 | 文件 | 说明 |
|------|------|------|
| 15 | `core/agent/context.py` | ContextManager + TranscriptManager |

### 阅读重点

```python
class ContextManager:
    # Token 估算 (字符 / 4)
    estimate_tokens(messages) -> int

    # Microcompact: 清理旧工具结果，保留最近3个
    microcompact(messages, keep_last=3) -> messages

    # Auto Compact: 保存 transcript + LLM 摘要
    async auto_compact(messages, session_id) -> {
        "compressed_messages": [...],
        "context_summary": "...",
        "transcript_path": "...",
        "token_count_reset": 0
    }

class TranscriptManager:
    # 保存到 .transcripts/*.jsonl
    save(messages, session_id) -> Path

    # 加载 transcript
    load(path) -> List[Dict]

    # 列出所有 transcript
    list_transcripts() -> List[Dict]
```

---

## Stage 5: API 层（理解对外接口）

### 文件列表

| 序号 | 文件 | 说明 |
|------|------|------|
| 16 | `api/routes/chat.py` | 对话 API 实现 |
| 17 | `api/routes/auth.py` | 认证 API |
| 18 | `api/middleware/auth.py` | JWT 验证中间件 |
| 19 | `api/schemas/chat.py` | 请求/响应模型 |
| 20 | `api/schemas/auth.py` | 认证模型 |

### 阅读重点

**chat.py**：
```python
@router.post("/completions")
async def chat_completions(request: ChatRequest, user: User = Depends(...)):
    # 调用 agent_graph.invoke()
    result = agent_graph.invoke(state)
    return ChatResponse(...)

@router.post("/stream")
async def chat_stream(request: ChatRequest):
    # SSE 流式响应
    for event in agent_graph.astream(state):
        yield f"data: {json.dumps(event)}\n\n"
```

---

## Stage 6: 支撑系统（理解基础设施）

### 文件列表

| 序号 | 文件 | 说明 |
|------|------|------|
| 21 | `memory/short_term.py` | Redis 短期记忆 |
| 22 | `db/redis.py` | Redis 连接池 |
| 23 | `db/mysql.py` | MySQL 异步引擎 |
| 24 | `auth/jwt_handler.py` | JWT 创建/验证 |
| 25 | `auth/permissions.py` | 权限定义 |
| 26 | `models/*.py` | SQLAlchemy ORM 模型 |

---

## Stage 7: 与原始代码对照理解

### 文件

| 序号 | 文件 | 说明 |
|------|------|------|
| 27 | `mini_claude_code.py` | 原始实现，对照学习 |

### 对照表

| 原始版本 | 重构版本 | 位置 |
|----------|----------|------|
| `agent_loop()` 函数 | `graph.py` + `nodes.py` | LangGraph 工作流替代手动循环 |
| `TOOL_HANDLERS` 字典 | `tools/__init__.py` + 各模块 | 工具注册与分发 |
| `TODO` 全局对象 | `task.py` TodoManager | 短期清单管理 |
| `TASK_MGR` 全局对象 | `task.py` TaskManager | 持久任务管理 |
| `BG` BackgroundManager | `background.py` | 后台任务 |
| `SKILLS` SkillLoader | `skills.py` | 技能加载 |
| `BUS` MessageBus | `team.py` AsyncMessageBus | 消息传递（异步版本） |
| `TEAM` TeammateManager | `team.py` TeammateManager + TeammateRunner | 团队管理 |
| `microcompact()` 函数 | `context.py` ContextManager.microcompact() | 工具结果清理 |
| `auto_compact()` 函数 | `context.py` ContextManager.auto_compact() | 上下文压缩 |
| nag reminder (第698-700行) | `nodes.py` save_memory_node | TodoWrite 提醒 |

---

## 阅读建议

### 1. 边看边画图

每读完一个模块，画出其与其他模块的关系图：

```
例如读完 nodes.py 后画：

init_context ──▶ load_memory ──▶ llm_call
                     │              │
                     │              ▼
                     │        route_after_llm
                     │              │
                     │    ┌────────┼────────┐
                     │    │        │        │
                     │ tool_call  compress  end
                     │    │        │        │
                     │    ▼        ▼        ▼
                     │ tool_executor  compress_context  END
                     │    │        │
                     │    ▼        │
                     │ save_memory │
                     │    │        │
                     │    └───────▶│
```

### 2. 跟踪一个请求

从 `api/routes/chat.py` 的 `chat_completions()` 开始：

```
POST /chat/completions
    │
    ▼
api/routes/chat.py:chat_completions()
    │
    ▼
构建 AgentState
    │
    ▼
agent_graph.invoke(state)
    │
    ▼
init_context_node → load_memory_node → ... → llm_call_node
    │
    ▼
返回 ChatResponse
```

### 3. 对照原始代码

读完重构版本后，打开 `mini_claude_code.py` 找到对应部分：

| 重构概念 | 原始位置 |
|----------|----------|
| `llm_call_node` | 第672-676行 `response = client.messages.create(...)` |
| `tool_executor_node` | 第680-694行工具执行循环 |
| `save_memory_node` 的 nag reminder | 第698-700行 |
| `TeammateRunner._loop` | 第441-531行 teammate 主循环 |

---

## 总结

按照本文档的 7 个阶段顺序阅读：

1. **配置入口** → 了解系统骨架
2. **核心 Agent** → 理解 LangGraph 工作流
3. **工具系统** → 理解能力扩展
4. **上下文管理** → 理解压缩机制
5. **API 层** → 理解对外接口
6. **支撑系统** → 理解基础设施
7. **对照原始** → 加深理解

预计阅读时间：
- 快速浏览：2-3 小时
- 深入理解：1-2 天
- 完全掌握：3-5 天（包括调试运行）