# Enterprise Agent 项目优化计划

> 本文档记录项目当前存在的问题及改进方案，来源于代码审计和面试准备中的深度分析。

---

## 一、幻觉防控机制缺失

### 1.1 System Prompt 缺少防幻觉约束 `[未完成]`

**问题描述：**
大模型本质是概率分布模型，不是知识库。幻觉的根本原因是模型优化目标（next token prediction）与"生成正确事实"之间的错位。当模型对某个知识点不确定时，它仍然会自信地生成流畅但错误的内容。具体技术层面：

- **解码策略**：temperature > 0 时采样引入随机性，top-p/top-k 截断可能跳过正确 token
- **注意力机制**：长上下文中注意力分散，关键信息被"淹没"
- **知识参数化**：事实知识被编码在 FFN 权重中，是隐式的、不可靠的，无法像数据库一样精确检索
- **校准缺失**：模型缺乏"知道自己不知道"的能力，对不确定的内容仍然给出高置信度回答

**当前状态：**
`llm_call_node` 已经注入了 `MAIN_SYSTEM_PROMPT`（nodes.py:37-53），但该 Prompt 只描述了工具能力和操作指南，**没有防幻觉约束**。模型不知道自己应该"不确定时说不知道"、"用工具验证事实"。

**当前代码：**
```python
# nodes.py:37-53
MAIN_SYSTEM_PROMPT = """You are an enterprise-grade AI assistant with access to powerful tools.

## Capabilities
- **Shell execution**: Run commands via `bash` tool
- **File operations**: Read, write, and edit files
...

## Guidelines
1. Use tools when needed to accomplish tasks — don't just describe what to do
2. Manage your work with TODO items for multi-step tasks
3. Be concise and direct in your responses
...
"""
# 只有能力描述和操作指南，没有防幻觉约束

# nodes.py:235
lc_messages.insert(0, SystemMessage(content=MAIN_SYSTEM_PROMPT))
```

**改进方案：**
在 `MAIN_SYSTEM_PROMPT` 中增加防幻觉和工具使用策略约束：

```
## Anti-Hallucination Rules
- 涉及文件内容时，必须先调用 read_file 验证，不要凭记忆猜测
- 不确定时明确说"我不确定"，不要编造
- 基于提供的上下文回答，不要凭参数记忆猜测
- 代码引用必须来自实际读取的文件

## Tool Usage Strategy
- 当用户询问文件内容时，必须先调用 read_file
- 当用户要求修改代码时，必须先 read_file 确认当前内容，再 edit_file
- 不要猜测文件内容，始终使用工具验证
```

> 注：本项目是类 Claude Code 的代码助手，不使用 RAG 外部知识库。信息获取完全依赖工具调用（read_file、bash 等），这与 Claude Code 的设计一致。

---

### 1.2 缺少输出校验机制 `[未完成]`

**问题描述：**
模型生成的内容没有经过任何事实性验证。例如模型说"文件 X 的内容是 Y"，但没有去实际读取文件验证。`tool_executor_node`（nodes.py:271）只在模型**主动**调用工具时才执行，没有自动校验机制。

**改进方案：**
- 对于涉及文件内容的回答，自动触发 `read_file` 做交叉验证
- 对于涉及代码执行结果的回答，自动触发 `bash` 做验证
- 或者在 System Prompt 中强制要求模型在回答前先调用工具确认（已在 1.1 中体现）

---

## 二、上下文压缩策略问题 `[未完成]`

### 2.1 当前方案总览

当前采用两层压缩：

```
第一层：microcompact（每次 LLM 调用前，pre_llm_microcompact_node）
  旧 tool 输出 → "[cleared]"  ← 硬删除，信息全丢

第二层：auto_compact（token_count > 100000 时，compress_context_node）
  所有消息 → LLM 摘要 → 单条 system message  ← 核弹级压缩
```

**存在三个问题：**

| 问题 | 位置 | 影响 |
|------|------|------|
| **microcompact 硬删除** | context.py:173-175 | tool 输出中的错误信息、文件路径全丢 |
| **auto_compact 全量替换** | context.py:257-267 | Attention Sink 丢失、近期上下文丢失 |
| **字符截断破坏 JSON** | context.py:240-242 | json.dumps 后按字符截断可能切在 key/value 中间 |

### 2.2 Attention Sink 问题

Attention Sink 是 Transformer 的固有特性。模型会将序列最开头的几个 token 赋予异常高的注意力权重，无论语义内容是什么。这些初始 token 吸收冗余注意力，保证后续 token 的注意力分布正常。

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

当前 `auto_compact` 用单条 system message 替换所有消息，Attention Sink 被重置。

### 2.3 改进方案 — 三层压缩架构

```
压缩前:
  [system_prompt] [msg1] [msg2] ... [msg_n-8] [msg_n-7] ... [msg_n]
       ↑                                                        ↑
   Attention Sink                                          最近 N 轮

压缩后:
  [system_prompt] [旧对话摘要] [最近 6 轮完整消息]
       ↑              ↑                ↑
   保留(Sink)    LLM 生成摘要     不压缩，完整保留
```

#### 第一层：tool 输出软压缩（替代 microcompact）

```python
def soft_microcompact(self, messages, keep_last=3, anchor_chars=300):
    """旧 tool 输出软压缩：保留前 N 字符作为记忆锚点"""
    tool_indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            tool_indices.append(i)

    for i in tool_indices[:-keep_last]:
        content = messages[i].get("content", "")
        if len(content) > anchor_chars:
            messages[i]["content"] = (
                content[:anchor_chars]
                + f"\n[...共 {len(content)} 字符，完整输出见 transcript]"
            )
    return messages
```

**与当前方案对比：**
- 当前：`"[cleared - see transcript for full output]"` → 信息全丢
- 改进：保留前 300 字符 → LLM 还能看到错误类型、文件名、返回值摘要

#### 第二层：N 轮滚动摘要（替代 auto_compact）

```python
async def rolling_compact(self, messages, keep_recent=6):
    """滚动压缩：旧消息做摘要，最近 N 轮完整保留"""

    if len(messages) <= keep_recent + 2:
        return messages  # 太短，不压缩

    recent = messages[-keep_recent:]        # 最近 6 条，完整保留
    to_summarize = messages[:-keep_recent]  # 之前的，做摘要

    # 按消息粒度截断（避免 JSON 结构被破坏）
    summary_text = json.dumps(to_summarize, default=str)
    if len(summary_text) > 30000:
        # 按消息粒度截断，而非按字符
        to_summarize = self._truncate_by_messages(to_summarize, 30000)
        summary_text = json.dumps(to_summarize, default=str)

    summary_prompt = f"""将以下对话压缩为结构化摘要，保留：
- 用户的核心需求和决策
- 修改了哪些文件，做了什么改动
- 遇到的错误和解决方案
- 当前任务的进度状态

对话内容：
{summary_text}"""

    response = await self.llm.ainvoke([{"role": "user", "content": summary_prompt}])

    return [
        {"role": "system", "content": f"[对话历史摘要]\n{response.content}"},
        *recent
    ]

def _truncate_by_messages(self, messages, max_chars):
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

**与当前方案对比：**
- 当前：`messages_text[-80000:]` 按字符截断 → 可能破坏 JSON，然后全量替换为单条摘要
- 改进：按消息粒度截断 → JSON 完整；摘要 + 最近 6 轮 → 保留近期上下文

#### 第三层：长期记忆存储（已有，不变）

压缩时将摘要存入 Chroma（`compress_context_node` 已实现），供未来会话检索。

### 2.4 改进后的完整压缩流程

```
每次 LLM 调用前（pre_llm_microcompact_node）：
  └─ soft_microcompact：旧 tool 输出保留前 300 字符

token_count > 100000 时（compress_context_node）：
  ├─ 保存 transcript 到文件
  ├─ rolling_compact：旧消息做摘要 + 最近 6 轮完整保留
  └─ 存摘要到 Chroma 长期记忆

最终消息结构：
  [MAIN_SYSTEM_PROMPT]     ← Attention Sink，始终保留
  [旧对话摘要]              ← LLM 生成的结构化摘要
  [最近 6 轮消息]           ← 完整保留，不压缩
  [旧 tool 输出(软压缩)]    ← 前 300 字符 + 截断提示
```

---

## 三、长期记忆未接入工作流

### 3.1 Chroma 长期记忆接入 `[大部分已完成]`

**问题描述：**
`ChromaLongTermMemory` 实现了 `store_conversation`、`search_conversations`、`store_pattern`、`search_patterns` 等方法，需要接入 agent 工作流。

**当前状态：**
- ✅ `init_context_node`（nodes.py:158-204）：新会话首条消息时检索 Chroma，注入 `<long_term_memory>` 上下文
- ✅ `compress_context_node`（nodes.py:393-406）：压缩时将摘要存入 Chroma
- ✅ `manual_compress_node`（nodes.py:432-445）：手动压缩时将摘要存入 Chroma
- ❌ `save_memory_node`（nodes.py:343-368）：**没有**逐条存入对话，只做了 TodoWrite nag reminder
- ❌ `chat.py`：没有在请求级别调用长期记忆

**剩余改进 — save_memory_node 中增加逐条存储：**
```python
async def save_memory_node(state: AgentState) -> Dict[str, Any]:
    from enterprise_agent.memory.long_term import get_long_term_memory
    memory = get_long_term_memory(user_id=state["user_id"])

    # 把最近的对话存入长期记忆（当前缺失）
    for msg in state["messages"][-2:]:
        if msg.get("role") in ("user", "assistant"):
            await memory.store_conversation(
                session_id=state["session_id"],
                role=msg["role"],
                content=msg["content"]
            )
    # ... 原有 nag reminder 逻辑
```

> 注：`init_context_node` 的检索注入和 `compress_context_node` 的摘要存储已实现。

---

## 四、多用户文件系统隔离缺失

### 4.1 工具层没有用户隔离 `[未完成]`

**问题描述：**
`file_ops.py` 和 `shell.py` 中的工具直接操作服务器文件系统，没有根据 `user_id` 隔离工作空间。所有用户共享同一个文件系统，存在数据泄露和误操作风险。用户 A 说"读 main.py"和用户 B 说"读 main.py"读的是同一个文件。

**当前代码：**
```python
# file_ops.py
WORKDIR = Path.cwd()  # 全局共享，没有 user_id 隔离

@tool
def read_file(path: str, limit: Optional[int] = None) -> str:
    validator = SafePathValidator(path)  # 有路径穿越防护
    fp = validator.validate_path(WORKDIR)  # 但 WORKDIR 是全局的
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

### 4.2 路径穿越防护 `[部分完成]`

**问题描述：**
即使实现了用户隔离，如果不对 `path` 做安全检查，用户可以通过 `../../etc/passwd` 之类的路径穿越读取服务器上的任意文件。

**当前状态：**
- ✅ `file_ops.py`：已有 `SafePathValidator`（line 11-21），通过 `is_relative_to` 检查路径穿越
- ✅ `shell.py`：已有 `BLOCKED_PATTERNS` 和 `BLOCKED_BINARIES` 黑名单（line 10-17），拦截危险命令
- ❌ `shell.py`：`bash` 工具没有路径限制，可以通过 `cat ../../etc/passwd` 读取任意文件
- ❌ 没有审计日志

**改进方案：**
- 对 `bash` 工具的工作目录做限制，或对输出内容做过滤
- 记录所有文件操作的审计日志

---

## 五、服务端部署模式下的架构问题

### 5.1 Agent 操作的是服务器文件系统 `[N/A - 架构选择]`

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

### 6.1 API 调用无重试机制 `[未完成]`

**问题描述：**
`llm_call_node` 直接调用 `get_llm_with_tools().ainvoke()`，没有重试逻辑。当 LLM API 出现临时性错误（如 rate limit、网络抖动）时，整个请求直接失败。

**改进方案：**
- 添加指数退避重试（exponential backoff）
- 区分可重试错误（rate limit、timeout）和不可重试错误（auth failed、invalid request）
- 添加 fallback provider（如 Anthropic 失败时切换到 DeepSeek）

---

## 七、Token 估算不准确

### 7.1 字符数 / 4 的估算方式对中文严重低估 `[部分完成]`

**问题描述：**
`estimate_tokens` 使用 `total_chars // 4` 来估算 token 数。这种方式对英文还比较接近，但对中文严重低估（中文一个字通常 2-3 个 token，而非 0.25 个）。这会导致压缩时机判断不准确——实际 token 数可能已经超过阈值，但估算值还没触发压缩。

**当前状态：**
- ✅ `llm_call_node`（nodes.py:253-259）：优先使用 `usage_metadata` 中的真实 token 数，仅在 API 不返回时 fallback 到估算
- ❌ `estimate_tokens`（context.py:122-146）：fallback 仍使用 `chars // 4`，未改进

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

# nodes.py:253-259（已改进：优先用真实 token 数）
usage = getattr(response, "usage_metadata", {})
if usage:
    token_count += usage.get("total_tokens", 0)
else:
    ctx_mgr = get_context_manager()
    token_count += ctx_mgr.estimate_tokens([response])
```

**改进方案：**
- 使用 tiktoken 库做精确 token 计数
- 或者针对中文内容调整估算系数（中文约 `chars * 0.7`）

---

## 八、优先级排序与完成状态

| 优先级 | 问题 | 状态 | 影响 | 改动量 |
|--------|------|------|------|--------|
| **P0** | 长期记忆接入工作流 | 🟡 大部分已完成 | 核心功能 | 中 |
| **P0** | System Prompt 缺少防幻觉约束 | 🔴 未完成 | 幻觉高发 | 小 |
| **P1** | 上下文压缩策略重构（三层压缩） | 🔴 未完成 | 压缩后质量下降、信息丢失 | 中 |
| **P1** | 文件系统隔离缺失 | 🔴 未完成 | 安全风险 | 中 |
| **P2** | Token 估算不准 | 🟡 部分完成 | 压缩时机 | 小 |
| **P2** | 路径穿越防护 | 🟡 部分完成 | 安全风险 | 小 |
| **P3** | 无重试机制 | 🔴 未完成 | 偶发失败 | 小 |
| **P3** | 缺少输出校验 | 🔴 未完成 | 幻觉 | 中 |
