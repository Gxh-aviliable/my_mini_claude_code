# Enterprise Agent 项目优化计划

> 本文档记录项目当前存在的问题及改进方案，来源于代码审计和面试准备中的深度分析。

---

## 一、幻觉防控机制缺失

### 1.1 缺少 System Prompt 约束

**问题描述：**
大模型本质是概率分布模型，不是知识库。幻觉的根本原因是模型优化目标（next token prediction）与"生成正确事实"之间的错位。当模型对某个知识点不确定时，它仍然会自信地生成流畅但错误的内容。具体技术层面：

- **解码策略**：temperature > 0 时采样引入随机性，top-p/top-k 截断可能跳过正确 token
- **注意力机制**：长上下文中注意力分散，关键信息被"淹没"
- **知识参数化**：事实知识被编码在 FFN 权重中，是隐式的、不可靠的，无法像数据库一样精确检索
- **校准缺失**：模型缺乏"知道自己不知道"的能力，对不确定的内容仍然给出高置信度回答

**当前状态：**
`llm_call_node` 直接将 messages 传入 LLM，没有任何 System Prompt 约束模型行为。模型不知道自己应该"不确定时说不知道"、"用工具验证事实"。

**当前代码：**
```python
# nodes.py:155
async def llm_call_node(state: AgentState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    lc_messages = _convert_to_langchain_messages(messages)
    response = await get_llm_with_tools().ainvoke(lc_messages)
    # 没有 SystemMessage 注入
```

**改进方案：**
在 `llm_call_node` 中注入 System Prompt，约束模型行为：
- 不确定时明确说"我不确定"，而不是编造
- 涉及文件内容时必须先调用 `read_file` 验证
- 基于提供的上下文回答，不要凭参数记忆猜测

---

### 1.3 缺少输出校验机制

**问题描述：**
模型生成的内容没有经过任何事实性验证。例如模型说"文件 X 的内容是 Y"，但没有去实际读取文件验证。`tool_executor_node` 只在模型主动调用工具时才执行，没有自动校验机制。

**改进方案：**
- 对于涉及文件内容的回答，自动触发 `read_file` 做交叉验证
- 对于涉及代码执行结果的回答，自动触发 `bash` 做验证
- 或者在 System Prompt 中强制要求模型在回答前先调用工具确认

---

## 二、上下文压缩策略问题

### 2.1 Attention Sink 丢失

**问题描述：**
Attention Sink 是 Transformer 的固有特性。由于 softmax 归一化需要一个"注意力垃圾桶"，模型会将序列最开头的几个 token 赋予异常高的注意力权重，无论这些 token 的语义内容是什么。这些初始 token 承担了吸收冗余注意力的角色，保证了后续 token 的注意力分布正常。

```
Attention Score 分布（示意）:

Token位置:  [0]   [1]   [2]   [3]  ...  [n-2] [n-1]
             ↑     ↑                            ↑
           初始token                        最近token
           (极高权重)                       (较高权重)

             └─────┘                         └────┘
            Attention Sink              Recent Context
            不管内容是什么                语义上真正相关
            都会被高度关注
```

当压缩上下文时如果把这些初始 token 删掉，模型的注意力分布会重新校准，导致生成质量下降、连贯性变差。

**当前状态：**
`auto_compact` 执行全量压缩，用一条新的 system message 替换所有历史消息。原始的 system prompt、初始消息全部丢失，Attention Sink 被重置。

**当前代码：**
```python
# context.py:217
async def auto_compact(self, messages, session_id=None):
    # 存原文到文件
    transcript_path = self.transcript_manager.save(messages, session_id)

    # 截断到 CONTEXT_SUMMARY_TRIGGER_CHARS 字符
    messages_text = json.dumps(messages, default=str)
    if len(messages_text) > settings.CONTEXT_SUMMARY_TRIGGER_CHARS:
        messages_text = messages_text[-settings.CONTEXT_SUMMARY_TRIGGER_CHARS:]
        # ↑ 从末尾截断，前面全丢了，包括 Attention Sink

    # LLM 做摘要
    summary_prompt = "Summarize the following conversation..."
    response = await self.llm.ainvoke([{"role": "user", "content": summary_prompt}])

    # 用单条 system message 替换所有消息
    return {
        "compressed_messages": [
            {"role": "system", "content": f"Previous conversation summary:\n{summary}"}
        ]
    }
```

**改进方案 — 保留首尾、压缩中间：**

```
压缩前: [system_prompt] [msg1] [msg2] ... [msg_n-2] [msg_n-1] [msg_n]
             ↑                                                  ↑
         保留(Sink)                                        保留(Recent)

压缩后: [system_prompt] [摘要: msg1~msg_n-6] [msg_n-5] ... [msg_n]
             ↑                ↑                              ↑
         Attention Sink   层次化摘要                     近期上下文
```

- `SINK_COUNT = 2`：保留前 2 条消息（通常是 system prompt 和用户首条消息）
- `RECENT_COUNT = 6`：保留最近 6 条消息（维护近期语义连贯）
- 中间部分做层次化摘要，而非一次性全量压缩
- 这样既压缩了 token，又保持了注意力分布的稳定性

---

### 2.2 microcompact 硬删除导致信息丢失

**问题描述：**
microcompact 对旧的 tool 输出做硬删除（直接替换为 `[cleared]`），这些信息完全丢失。如果后续对话需要引用之前 tool 输出中的某个细节（如某个文件路径、某个错误信息），就找不回来了。

**当前代码：**
```python
# context.py:174
for idx, part in tool_results[:-keep_last]:
    if isinstance(part.get("content"), str) and len(part.get("content", "")) > 100:
        part["content"] = "[cleared - see transcript for full output]"
```

**改进方案 — 软压缩：**
保留 tool 输出的前几百字符作为"记忆锚点"，细节部分指向 transcript 文件：

```python
def soft_microcompact(self, messages, keep_last=3, anchor_chars=200):
    """保留消息结构和关键信息，只压缩细节"""
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool" and i < len(messages) - keep_last:
            content = msg.get("content", "")
            if len(content) > anchor_chars:
                msg["content"] = (
                    content[:anchor_chars]
                    + f"\n[...{len(content) - anchor_chars} more chars, see transcript]"
                )
    return messages
```

---

### 2.3 auto_compact 字符截断可能破坏 JSON 结构

**问题描述：**
`auto_compact` 在截断 messages 时按字符数截断（`messages_text[-CONTEXT_SUMMARY_TRIGGER_CHARS:]`），但 `messages_text` 是 `json.dumps` 的结果。按字符截断可能截断在 JSON 结构中间（比如一个 key 被截成两半），导致后续 LLM 收到的是损坏的 JSON 片段。

**当前代码：**
```python
# context.py:240
messages_text = json.dumps(messages, default=str)
if len(messages_text) > settings.CONTEXT_SUMMARY_TRIGGER_CHARS:
    messages_text = messages_text[-settings.CONTEXT_SUMMARY_TRIGGER_CHARS:]
    # ↑ 可能截断在 JSON key/value 中间
```

**改进方案：**
按消息粒度截断，而非按字符截断：

```python
def truncate_by_messages(self, messages, max_chars):
    """按消息粒度截断，保证 JSON 结构完整"""
    result = []
    total = 0
    for msg in reversed(messages):
        msg_len = len(json.dumps(msg, default=str))
        if total + msg_len > max_chars:
            break
        result.insert(0, msg)
        total += msg_len
    return result
```

---

## 三、长期记忆未接入工作流

### 3.1 Chroma 存储/检索从未被调用

**问题描述：**
`ChromaLongTermMemory` 实现了 `store_conversation`、`search_conversations`、`store_pattern`、`search_patterns` 等方法，但在整个 agent 工作流中**从未被调用**。`AgentState` 中原来定义了 `long_term_memory_refs` 字段，但在最近的重构中已被移除。

**当前状态：**
- `chat.py`：只传了 `messages`、`session_id`、`user_id`，没有调用长期记忆
- `nodes.py` 的 `llm_call_node`：没有检索历史记忆注入上下文
- `nodes.py` 的 `save_memory_node`：只做了 TodoWrite nag reminder，没有存入 Chroma
- Chroma 的 `asyncio.to_thread` 包装和 per-user 缓存已就绪，但上层未调用

**改进方案：**

**存入时机 — save_memory_node 中：**
```python
async def save_memory_node(state: AgentState) -> Dict[str, Any]:
    from enterprise_agent.memory.long_term import get_long_term_memory
    memory = get_long_term_memory(user_id=state["user_id"])

    # 把最近的对话存入长期记忆
    for msg in state["messages"][-2:]:
        if msg.get("role") in ("user", "assistant"):
            await memory.store_conversation(
                session_id=state["session_id"],
                role=msg["role"],
                content=msg["content"]
            )
    # ... 原有 nag reminder 逻辑
```

**检索时机 — init_context_node 中：**
```python
async def init_context_node(state: AgentState) -> Dict[str, Any]:
    from enterprise_agent.memory.long_term import get_long_term_memory
    memory = get_long_term_memory(user_id=state["user_id"])

    # 语义检索相关历史记忆
    last_msg = state["messages"][-1]["content"] if state["messages"] else ""
    related = await memory.search_conversations(query=last_msg, n_results=3)

    if related:
        memory_context = "\n".join([r["content"] for r in related])
        # 注入到上下文
        return {
            "messages": [{"role": "system", "content": f"<relevant_history>\n{memory_context}\n</relevant_history>"}],
        }
    return { ... }
```

---

## 四、多用户文件系统隔离缺失

### 4.1 工具层没有用户隔离

**问题描述：**
`file_ops.py` 和 `shell.py` 中的工具直接操作服务器文件系统，没有根据 `user_id` 隔离工作空间。所有用户共享同一个文件系统，存在数据泄露和误操作风险。用户 A 说"读 main.py"和用户 B 说"读 main.py"读的是同一个文件。

**当前代码：**
```python
# file_ops.py
@tool
def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
    # 没有 user_id 参数，所有用户读同一个文件
```

**改进方案：**
工具层根据 `user_id` 将文件操作限定在用户自己的工作空间内：

```python
@tool
def read_file(path: str, user_id: int) -> str:
    workspace = f"/home/agent_workspaces/user_{user_id}/"
    full_path = os.path.join(workspace, path)
    # 安全检查：防止路径穿越
    if not os.path.abspath(full_path).startswith(os.path.abspath(workspace)):
        raise ValueError("Path traversal detected")
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()
```

### 4.2 缺少路径穿越防护

**问题描述：**
即使实现了用户隔离，如果不对 `path` 做安全检查，用户可以通过 `../../etc/passwd` 之类的路径穿越读取服务器上的任意文件。

**改进方案：**
- 对所有文件路径做 `os.path.abspath` 校验，确保在用户工作空间内
- 对 `bash` 工具做命令白名单/黑名单过滤
- 记录所有文件操作的审计日志

---

## 五、服务端部署模式下的架构问题

### 5.1 Agent 操作的是服务器文件系统

**问题描述：**
项目通过 FastAPI 提供 API 服务，`file_ops` 和 `shell` 工具操作的是服务器上的文件系统，不是用户本地电脑。用户通过前端提交任务后，agent 在服务器上读写代码，用户本地什么都没发生。

**这不是缺陷，而是架构选择。** 但需要明确使用流程：

```
用户本地 → 浏览器/前端 → FastAPI 服务器 → Agent 操作服务器上的代码仓库
                              ↓
                         git push → 用户 git pull 拉取结果
```

**改进方案：**
- 支持 git 集成：agent 修改完代码后自动 commit + push，用户 pull 获取结果
- 或者提供文件下载 API，让用户直接下载修改后的文件
- 长期考虑：支持 SSH 连接用户指定的机器，或提供本地部署模式

---

## 六、LLM 调用健壮性

### 6.1 API 调用无重试机制

**问题描述：**
`llm_call_node` 直接调用 `get_llm_with_tools().ainvoke()`，没有重试逻辑。当 LLM API 出现临时性错误（如 rate limit、网络抖动）时，整个请求直接失败。

**改进方案：**
- 添加指数退避重试（exponential backoff）
- 区分可重试错误（rate limit、timeout）和不可重试错误（auth failed、invalid request）
- 添加 fallback provider（如 Anthropic 失败时切换到 DeepSeek）

### 6.2 无 System Prompt 的工具使用引导

**问题描述：**
模型不知道何时应该调用工具 vs 直接回答。没有 System Prompt 引导，模型可能在应该读文件验证时直接编造文件内容，或者在不需要工具时频繁调用。

**改进方案：**
在 System Prompt 中明确工具使用策略：
- "当用户询问文件内容时，必须先调用 read_file"
- "当用户要求修改代码时，必须先 read_file 确认当前内容，再 edit_file"
- "不要猜测文件内容，始终使用工具验证"

---

## 七、Token 估算不准确

### 7.1 字符数 / 4 的估算方式对中文严重低估

**问题描述：**
`estimate_tokens` 使用 `total_chars // 4` 来估算 token 数。这种方式对英文还比较接近，但对中文严重低估（中文一个字通常 2-3 个 token，而非 0.25 个）。这会导致压缩时机判断不准确——实际 token 数可能已经超过阈值，但估算值还没触发压缩。

**当前代码：**
```python
# context.py:122
def estimate_tokens(self, messages):
    total_chars = 0
    for msg in messages:
        if isinstance(msg, dict):
            total_chars += len(json.dumps(msg, default=str))
        # ...
    return total_chars // 4  # 对中文严重低估
```

**改进方案：**
- 使用 tiktoken 库做精确 token 计数
- 或者针对中文内容调整估算系数（中文约 `chars * 0.7`）
- 或者直接使用 LLM API 返回的 usage_metadata 中的真实 token 数

---

## 八、优先级排序

| 优先级 | 问题 | 影响 | 改动量 |
|--------|------|------|--------|
| **P0** | 长期记忆未接入工作流 | 核心功能缺失，记忆能力为零 | 中 |
| **P0** | 缺少 System Prompt | 幻觉高发，工具使用策略不明 | 小 |
| **P1** | Attention Sink 丢失 | 上下文压缩后生成质量下降 | 中 |
| **P1** | 文件系统隔离缺失 | 安全风险，多用户数据泄露 | 中 |
| **P2** | microcompact 硬删除 | 信息丢失，无法回溯历史 tool 输出 | 小 |
| **P2** | JSON 截断问题 | 数据损坏风险 | 小 |
| **P2** | 缺少 RAG | 知识检索能力缺失 | 大 |
| **P2** | Token 估算不准 | 压缩时机不准确 | 小 |
| **P3** | 无重试机制 | 偶发失败 | 小 |
| **P3** | 缺少输出校验 | 幻觉无法被自动发现 | 中 |
