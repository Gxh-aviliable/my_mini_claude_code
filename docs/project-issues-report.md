# Enterprise Agent 项目问题报告

> 检查日期：2026-05-05
> 检查范围：enterprise_agent 全部源代码

---

## 目录

1. [问题汇总](#问题汇总)
2. [架构问题](#架构问题)
3. [存储系统问题](#存储系统问题)
4. [API 层问题](#api-层问题)
5. [代码冗余/未使用](#代码冗余未使用)
6. [异步/并发问题](#异步并发问题)
7. [错误处理问题](#错误处理问题)
8. [安全风险](#安全风险)
9. [修复建议](#修复建议)

---

## 问题汇总

| 类别 | 高严重程度 | 中严重程度 | 低严重程度 |
|------|-----------|-----------|-----------|
| 架构问题 | 3 | 4 | 1 |
| 存储系统问题 | 2 | 2 | 1 |
| API 层问题 | 1 | 1 | 0 |
| 代码冗余 | 0 | 2 | 1 |
| 异步/并发问题 | 1 | 1 | 0 |
| 错误处理 | 0 | 1 | 2 |
| 安全风险 | 0 | 1 | 1 |

**总计：24 个问题**

---

## 架构问题

### 🔴 A-01: TodoManager 进程级别单例（高严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/task.py:224-239`

**问题描述**：
TodoManager 使用全局单例，所有用户共享同一个 todo 列表。在多用户场景下，用户A的 todo 会被用户B看到，数据完全混乱。

**代码示例**：
```python
# task.py 第 224-225 行
_task_manager: Optional[TaskManager] = None
_todo_manager: Optional[TodoManager] = None

def get_todo_manager() -> TodoManager:
    """Get or create TodoManager instance."""
    if _todo_manager is None:
        _todo_manager = TodoManager()  # ← 进程级别，所有用户共享
    return _todo_manager
```

**影响**：
- 多用户场景下 todo 数据混乱
- 进程重启后 todo 丢失（内存存储）

**修复建议**：
```python
def get_todo_manager(session_id: str) -> TodoManager:
    """Get session-level TodoManager instance."""
    # 使用 Redis 或文件存储，按 session_id 分离
```

---

### 🔴 A-02: BackgroundManager 进程级别单例（高严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/background.py:130-138`

**问题描述**：
BackgroundManager 使用全局单例，`tasks` 字典和 `notifications` 队列是进程级别的。所有用户的后台任务混在一起。

**代码示例**：
```python
# background.py 第 25-26 行
self.tasks: dict = {}      # ← 进程级别
self.notifications: Queue = Queue()  # ← 进程级别
```

**影响**：
- 用户A的后台任务结果被用户B获取
- 多用户场景数据混乱

---

### 🔴 A-03: TeammateManager/MessageBus 进程级别单例（高严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/team.py:659-683`

**问题描述**：
AsyncMessageBus、TeammateManager、PlanApprovalManager 都是进程级别单例。所有用户的 teammate 共享同一个 inbox 和配置。

**代码示例**：
```python
# team.py 第 659-662 行
_message_bus: Optional[AsyncMessageBus] = None
_teammate_manager: Optional[TeammateManager] = None
_plan_manager: Optional[PlanApprovalManager] = None
```

**影响**：
- 用户A的 teammate 消息被用户B看到
- teammate 配置混乱

---

### 🟡 A-04: ContextManager 进程级别单例（中严重程度）

**文件位置**：`enterprise_agent/core/agent/context.py:294-303`

**问题描述**：
ContextManager 和 TranscriptManager 是全局单例。TranscriptManager 使用 `Path.cwd()` 作为工作目录，在不同部署环境下可能不一致。

**影响**：
- transcript 文件路径可能不一致
- 多实例部署时 transcript 无法共享

---

### 🟡 A-05: SkillLoader 进程级别单例（中严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/skills.py:108-116`

**问题描述**：
SkillLoader 是全局单例，skills_dir 使用 `Path.cwd() / "skills"`，路径可能不一致。

---

### 🟡 A-06: ChromaLongTermMemory 进程级别单例（中严重程度）

**文件位置**：`enterprise_agent/memory/long_term.py:284-302`

**问题描述**：
`get_long_term_memory(user_id)` 虽然接受 user_id 参数，但实现有缺陷：

```python
# 首次调用创建实例，后续调用只更新 user_id
if _long_term_memory is None or _long_term_memory.user_id != user_id:
    _long_term_memory = ChromaLongTermMemory(user_id=user_id)
return _long_term_memory
```

这会导致切换 user_id 时创建新实例，但旧实例的引用仍可能被使用。

---

### 🟡 A-07: TaskManager 进程级别单例（中严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/task.py:224-232`

**问题描述**：
TaskManager 使用文件存储（`.tasks/` 目录），但工作目录是 `Path.cwd()`，不同会话可能指向不同位置。

---

### 🟢 A-08: agent_graph 全局单例（低严重程度）

**文件位置**：`enterprise_agent/core/agent/graph.py:188-189`

**问题描述**：
agent_graph 是全局单例，这是 LangGraph 的正常设计（图结构可以共享）。问题在于调用时缺少 thread_id。

---

## 存储系统问题

### 🔴 S-01: Checkpointer 缺少 thread_id（高严重程度）

**文件位置**：`enterprise_agent/api/routes/chat.py:42-46`

**问题描述**：
调用 agent_graph.ainvoke() 时没有传入 config 参数，导致 checkpointer 无法区分不同会话。

**代码示例**：
```python
# routes/chat.py 第 42-46 行（问题代码）
result = await agent_graph.ainvoke({
    "session_id": session_id,
    "user_id": user_id,
    "messages": [{"role": "user", "content": request.content}]
})  # ← 缺少 config={"configurable": {"thread_id": session_id}}
```

**修复建议**：
```python
result = await agent_graph.ainvoke(
    {
        "session_id": session_id,
        "user_id": user_id,
        "messages": [{"role": "user", "content": request.content}]
    },
    config={"configurable": {"thread_id": session_id}}
)
```

---

### 🔴 S-02: 用户消息重复存储（高严重程度）

**文件位置**：`enterprise_agent/api/routes/chat.py:39` + `enterprise_agent/core/agent/nodes.py:122-137`

**问题描述**：
用户消息被存储两次：
1. routes/chat.py 第 39 行：`await stm.append_message(session_id, "user", request.content)`
2. load_memory_node 从 Redis 加载后，与初始 messages 合并，导致重复

**流程分析**：
```
routes/chat.py:
  第39行: await stm.append_message(...) → Redis: ["你好"]

  第42行: agent_graph.ainvoke({"messages": [{"你好"}]})
          ↓ 初始 messages = [{"你好"}]

init_context_node:
  返回 {"messages": []}
  ↓ add_messages reducer: [{"你好"}] + [] = [{"你好"}]

load_memory_node:
  从 Redis 加载: [{"你好"}]  ← 第39行存的
  返回 {"messages": [{"你好"}]}
  ↓ add_messages reducer: [{"你好"}] + [{"你好"}] = [{"你好"}, {"你好"}]  ← 重复！
```

---

### 🟡 S-03: 长期记忆完全未使用（中严重程度）

**文件位置**：`enterprise_agent/memory/long_term.py`

**问题描述**：
ChromaLongTermMemory 类已实现，但没有任何地方调用其方法：
- `store_conversation()` - 未调用
- `search_conversations()` - 未调用
- `store_pattern()` - 未调用
- `search_patterns()` - 未调用

**验证**：
```bash
# grep 搜索结果
grep -r "store_conversation" enterprise_agent/  → 无匹配（除定义）
grep -r "search_conversations" enterprise_agent/ → 无匹配（除定义）
```

---

### 🟡 S-04: 存储冗余（中严重程度）

**问题描述**：
Checkpointer 和 Redis 都存储 messages，存在冗余：
- Checkpointer (MemorySaver): 进程内存中保存完整状态
- Redis ShortTermMemory: 保存 messages 列表

两者存储相同内容，浪费资源。

---

### 🟢 S-05: MemorySaver 不持久化（低严重程度）

**文件位置**：`enterprise_agent/core/agent/graph.py:123-124`

**问题描述**：
MemorySaver 是进程内存 checkpointer，进程重启后所有状态丢失。

**修复建议**：使用 RedisSaver 或数据库 checkpointer。

---

## API 层问题

### 🔴 API-01: routes/chat.py 预存消息（高严重程度）

**文件位置**：`enterprise_agent/api/routes/chat.py:39`

**问题描述**：
在调用 agent_graph 之前就将用户消息存入 Redis，导致与 load_memory_node 重复。

**修复建议**：
删除第 39 行，让 agent 内部流程处理存储。

---

### 🟡 API-02: session_id 生成逻辑分散（中严重程度）

**文件位置**：`enterprise_agent/api/routes/chat.py:34, 75`

**问题描述**：
session_id 在两个地方生成（非流式和流式），逻辑相同但分散。应该使用统一的会话管理。

---

## 代码冗余/未使用

### 🟡 C-01: ShortTermMemory 多个方法未使用（中严重程度）

**文件位置**：`enterprise_agent/memory/short_term.py`

**问题描述**：
ShortTermMemory 定义了以下方法，但未被调用：
- `get_state()` (第 55-61 行) - 未使用
- `set_state()` (第 63-74 行) - 未使用
- `acquire_lock()` (第 76-79 行) - 未使用
- `release_lock()` (第 81-84 行) - 未使用
- `cache_tool_result()` (第 86-96 行) - 未使用
- `get_cached_tool_result()` (第 98-107 行) - 未使用

**仅使用的方法**：
- `append_message()` - routes/chat.py, nodes.py
- `get_messages()` - nodes.py

---

### 🟡 C-02: agent_graph 多个节点可选但未切换（中严重程度）

**文件位置**：`enterprise_agent/core/agent/graph.py:127-192`

**问题描述**：
定义了 `build_agent_graph()` 和 `build_simple_agent_graph()` 两个版本，但默认只使用复杂版本。没有提供切换机制。

```python
# graph.py 第 188-192 行
agent_graph = build_agent_graph()      # 默认使用
simple_agent_graph = build_simple_agent_graph()  # 未使用
```

---

### 🟢 C-03: TodoManager 内存存储无持久化（低严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/task.py:151-221`

**问题描述**：
TodoManager 的 items 存储在内存中（`self.items: List[Dict] = []`），进程重启丢失。

---

## 异步/并发问题

### 🔴 AS-01: subagent.py task 工具返回类型错误（高严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/subagent.py:138-145`

**问题描述**：
task 工具在异步上下文中返回 `asyncio.create_task()`，但工具期望返回字符串。

**代码示例**：
```python
# subagent.py 第 138-145 行
@tool
def task(prompt: str, agent_type: Optional[str] = "Explore") -> str:
    try:
        loop = asyncio.get_running_loop()
        return asyncio.create_task(_run_subagent_async(prompt, agent_type or "Explore"))
        # ↑ 返回 Task 对象，不是字符串！
    except RuntimeError:
        return asyncio.run(_run_subagent_async(prompt, agent_type or "Explore"))
```

**影响**：tool_executor_node 会收到 Task 对象而不是字符串结果。

---

### 🟡 AS-02: team.py sync wrapper 使用 asyncio.run（中严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/team.py:708-771`

**问题描述**：
sync wrapper 函数使用 `asyncio.run()`，在已有运行循环的上下文中会抛出 RuntimeError。

**代码示例**：
```python
# team.py 第 708-711 行
def _spawn_teammate_sync(name: str, role: str, prompt: str) -> str:
    tm = get_teammate_manager()
    return asyncio.run(tm.spawn(name, role, prompt))  # ← 可能崩溃
```

---

## 错误处理问题

### 🟡 E-01: 缺少 Redis 连接失败处理（中严重程度）

**文件位置**：`enterprise_agent/db/redis.py:7-15`

**问题描述**：
Redis 连接池初始化时没有错误处理，如果 Redis 不可用，整个应用启动失败。

---

### 🟢 E-02: Chroma 初始化缺少错误处理（低严重程度）

**文件位置**：`enterprise_agent/db/chroma.py:26-37`

**问题描述**：
Chroma 初始化时如果 embedding model 下载失败，没有优雅处理。

---

### 🟢 E-03: LLM 调用缺少重试机制（低严重程度）

**文件位置**：`enterprise_agent/core/agent/nodes.py:165`

**问题描述**：
LLM 调用失败时直接抛出异常，没有重试机制。

---

## 安全风险

### 🟡 SEC-01: file_ops.py 路径验证不严格（中严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/file_ops.py:14-18`

**问题描述**：
SafePathValidator 使用 `Path.cwd()` 作为工作目录验证，但：
1. 不同进程 cwd 可能不同
2. Windows 下路径验证可能存在绕过风险

---

### 🟢 SEC-02: shell.py 危险命令列表不完整（低严重程度）

**文件位置**：`enterprise_agent/core/agent/tools/shell.py:5`

**问题描述**：
BLOCKED_COMMANDS 列表不完整，可能遗漏其他危险命令。

```python
BLOCKED_COMMANDS = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
# 缺少: "chmod 777", "chown root", ":(){ :|:& };:" 等
```

---

## 修复建议

### 优先级排序

| 优先级 | 问题ID | 问题描述 | 修复难度 |
|--------|--------|----------|----------|
| P0 | S-01 | Checkpointer 缺少 thread_id | 低 |
| P0 | S-02 | 用户消息重复存储 | 低 |
| P0 | A-01 | TodoManager 进程级别单例 | 中 |
| P0 | A-02 | BackgroundManager 进程级别单例 | 中 |
| P0 | A-03 | TeammateManager 进程级别单例 | 中 |
| P1 | API-01 | routes/chat.py 预存消息 | 低 |
| P1 | AS-01 | subagent task 返回类型错误 | 中 |
| P1 | S-03 | 长期记忆未使用 | 高 |
| P2 | A-04-A-07 | 其他进程级别单例 | 中 |
| P2 | C-01 | ShortTermMemory 未使用方法 | 低 |
| P2 | S-04 | 存储冗余 | 高 |
| P3 | 其他问题 | 错误处理、安全等 | 低 |

### 快速修复方案

#### 修复 S-01 + S-02 + API-01（最紧急）

修改 `routes/chat.py`：

```python
@router.post("/completions", response_model=ChatResponse)
async def chat_completion(
    request: ChatRequest,
    user_id: int = Depends(get_current_user)
):
    session_id = request.session_id or str(uuid.uuid4())

    # 删除预存消息（解决 S-02 和 API-01）
    # await stm.append_message(session_id, "user", request.content)  ← 删除

    # 添加 config 参数（解决 S-01）
    result = await agent_graph.ainvoke(
        {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [{"role": "user", "content": request.content}]
        },
        config={"configurable": {"thread_id": session_id}}  ← 新增
    )

    ...
```

#### 修复 A-01（TodoManager 会话级别）

修改 `task.py`：

```python
def get_todo_manager(session_id: str) -> TodoManager:
    """Get session-level TodoManager instance."""
    # 使用 Redis 存储
    from enterprise_agent.db.redis import redis_client
    return TodoManager(redis_client, session_id)

class TodoManager:
    def __init__(self, redis_client, session_id: str):
        self.redis = redis_client
        self.session_id = session_id
        self.key = f"session:{session_id}:todos"

    async def load_items(self):
        data = await self.redis.get(self.key)
        self.items = json.loads(data) if data else []

    async def save_items(self):
        await self.redis.set(self.key, json.dumps(self.items))
```

#### 修复 AS-01（subagent 返回类型）

修改 `subagent.py`：

```python
@tool
async def task(prompt: str, agent_type: Optional[str] = "Explore") -> str:
    """Spawn a subagent for isolated work."""
    # 使用 async 工具，直接返回 await 结果
    return await _run_subagent_async(prompt, agent_type or "Explore")
```

---

## 附录：问题检查方法

```bash
# 检查全局单例
grep -rn "^_[a-zA-Z_]+: Optional\[" enterprise_agent/

# 检查未使用的方法
grep -rn "get_state\|acquire_lock\|cache_tool_result" enterprise_agent/

# 检查长期记忆调用
grep -rn "store_conversation\|search_conversations" enterprise_agent/

# 检查 thread_id 使用
grep -rn "thread_id\|configurable" enterprise_agent/
```

---

*报告生成时间：2026-05-05*