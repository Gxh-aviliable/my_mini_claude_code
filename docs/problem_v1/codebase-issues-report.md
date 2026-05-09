# Enterprise Agent 代码框架问题报告

> 生成日期: 2026-05-07
> 范围: 全代码库审查
> 优先级: P0（关键） > P1（高优） > P2（中优） > P3（低优）

---

## P0 — 关键问题（必须立即修复）

### P0-1: Microcompact 机制失效 — 核心防令牌膨胀机制不可用

**文件:** `enterprise_agent/core/agent/context.py:153-182`

**描述:**
`microcompact()` 方法寻找 `msg.get("role") == "user"` 消息中 `type == "tool_result"` 的 content block。但在 LangChain/LangGraph 重构版本中，工具结果是独立的 `role: "tool"` 消息（即 ToolMessage），而不是 user 消息的 content 列表中的 block。因此 microcompact 永远不会匹配到任何内容，整个机制形同虚设。

**影响:**
每次 LLM 调用都会携带所有历史工具输出，令牌消耗持续增长直到触发 auto-compact，极大降低效率。

**修复方向:**
需要重写 `microcompact` 逻辑，改为清理旧的 `role: "tool"` 消息内容，保留最近 N 条。

---

### P0-2: 测试覆盖率为零

**文件:** `tests/` 目录完全为空

**描述:**
整个项目没有一行测试代码。无单元测试、无集成测试、无端到端测试。

**影响:**
任何修改都无法验证正确性；重构风险极高；无法做 CI/CD。

**修复方向:**
至少为以下核心模块添加测试：
- `auth/jwt_handler.py` — JWT 生成与验证
- `core/agent/llm_factory.py` — LLM 工厂多 provider 逻辑
- `core/agent/context.py` — 压缩与微压缩逻辑
- `core/agent/tools/file_ops.py` — 文件操作
- `core/agent/tools/task.py` — 任务管理

---

### P0-3: Streaming 端点可能完全不工作

**文件:** `enterprise_agent/api/routes/chat.py:104-142`

**描述:**
`/chat/stream` 端点使用 `astream_events()` 并监听 `on_chain_stream` 事件。但图内部在 `llm_call_node` 中使用 `ainvoke` 调用 LLM（非流式），因此 `on_chain_stream` 事件可能永远不会被触发。前端 SSE 连接可能永远收不到数据。

```python
# 期望: 流式 LLM 调用产生 on_chain_stream
# 实际: ainvoke 是批式调用，不会产生流式事件
response = await get_llm_with_tools().ainvoke(lc_messages)
```

**影响:**
用户无法使用流式对话功能。

**修复方向:**
需要使用 LangGraph 的流式支持，或单独实现 SSE 流式响应。

---

### P0-4: `.env` 包含真实生产级密钥

**文件:** `.env`

**描述:**
`.env` 文件中包含了真实的 `LLM_API_KEY` 和 `JWT_SECRET_KEY`（非占位符值）。虽然 `.env` 在 `.gitignore` 中，但在开发/演示环境中密钥已经暴露。

```
JWT_SECRET_KEY=3XDP0vouXLpgTdgyoCd_ELydaPMhgYPiaBajFPP8dmc
LLM_API_KEY=tp-s89ex04qi65lk41q8o17gxeel3a1jnp9qs5clyrd5ovc3t1u
```

**影响:**
密钥泄露可能导致未授权使用 LLM API 或伪造 JWT 令牌。

**修复方向:**
立即轮换这两个密钥。`.env` 应只包含占位符值，实际密钥通过安全渠道分发。

---

## P1 — 高优先级问题（尽快修复）

### P1-1: 架构不一致 — BackgroundManager 使用全局单例

**文件:** `enterprise_agent/core/agent/tools/background.py:28-29, 141-150`

**描述:**
大多数管理器都使用按用户实例化的模式（如 TaskManager、TodoManager、ContextManager），但 `BackgroundManager` 使用了全局单例模式。这意味着用户 A 启动的背景任务可以在用户 B 的会话中查阅。

```python
# ContextManager: 按用户隔离
_context_managers: Dict[int, ContextManager] = {}

# BackgroundManager: 全局单例
_bg_manager = None
```

**影响:**
多用户环境下背景任务信息会跨用户泄露。

**修复方向:**
改为与 ContextManager 一致的用户隔离模式。

---

### P1-2: 架构不一致 — SkillLoader 使用全局单例

**文件:** `enterprise_agent/core/agent/tools/skills.py:110-118`

**描述:**
与 BackgroundManager 相同的问题，SkillLoader 是全局单例，但理论上加载的技能内容可能是用户特定的。

**影响:**
技能加载逻辑无法按用户差异化。

**修复方向:**
改为按用户实例化，或确认可以安全保持全局单例并明确记录。

---

### P1-3: 长时记忆注入行为与预期不符

**文件:** `enterprise_agent/core/agent/nodes.py:206-214`

**描述:**
`init_context_node` 在找到相关长时记忆时返回 `{"messages": [system_msg]}`。由于 `AgentState.messages` 配置了 `add_messages` reducer（Annotated），这会 **追加** 一条系统消息，而不是替换或前置插入。

```python
# 当前行为：追加一条系统消息到消息列表末尾
# 预期行为：可能希望前置插入作为上下文
result["messages"] = [{"role": "system", "content": "...<long_term_memory>..."}]
```

**影响:**
长时记忆被追加到消息末尾，LLM 可能在生成回应后才"看到"记忆，导致记忆无法影响当前回答。

**修复方向:**
明确期望行为并修正消息插入位置。

---

### P1-4: Redis checkpointer 与业务 Redis 共用 db 0

**文件:** `enterprise_agent/core/agent/graph.py:44-51` vs `enterprise_agent/db/redis.py:6-14`

**描述:**
LangGraph 的 AsyncRedisSaver checkpointer 使用独立的 Redis 连接池但未指定 `db` 编号，默认使用 db 0。同时，业务 Redis 客户端（`redis_client`）也使用 db 0。两者的 key 可能冲突。

```python
# 业务 Redis - db 0（默认）
redis_pool = redis.ConnectionPool(host=..., port=..., decode_responses=True)

# Checkpointer Redis - 也是 db 0（默认），且 decode_responses=False
_checkpointer_pool = redis_async.ConnectionPool(host=..., port=..., decode_responses=False)
```

**影响:**
可能导致状态管理 key 与业务 key 冲突。

**修复方向:**
为 checkpointer 指定独立的 db 编号（如 db 1）。

---

### P1-5: 令牌黑名单 TTL 硬编码

**文件:** `enterprise_agent/api/routes/auth.py:136-137`

**描述:**
刷新令牌的黑名单过期时间使用了硬编码的 `7 * 24 * 3600`，而不是从设置中读取 `settings.REFRESH_TOKEN_EXPIRE_DAYS`。

```python
ttl_seconds = 7 * 24 * 3600  # 硬编码
# 应该为:
# ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
```

**影响:**
如果将来修改 `REFRESH_TOKEN_EXPIRE_DAYS`，黑名单 TTL 不会同步更新。

---

### P1-6: `import logging` 放在函数体内

**文件:** `enterprise_agent/api/routes/chat.py:60`

**描述:**
`import logging` 被放在 `chat_completion()` 函数内部而非文件顶部，不符合 Python 惯例，且每次请求都会重新 import。

**修复方向:**
将 import 移到文件顶部。

---

### P1-7: 多处过度宽泛的异常捕获

**文件:**
- `enterprise_agent/core/agent/nodes.py:216` — `except:` 捕获所有异常包括 `KeyboardInterrupt`
- `enterprise_agent/core/agent/nodes.py:418` — `except Exception: pass`
- `enterprise_agent/core/agent/nodes.py:457` — `except Exception: pass`

**描述:**
为了确保"Chroma 故障不影响主流程"，多处使用了空 `except Exception: pass`。其中第 216 行甚至使用了裸 `except:`。

**影响:**
调试困难，真正的错误会被静默吞掉。

**修复方向:**
至少应添加 `logging.warning` 记录异常，避免完全静默。

---

### P1-8: Teammate 默认使用 CWD 而非用户工作区

**文件:**
- `enterprise_agent/core/agent/tools/team.py:89` — `Path.cwd()`
- `enterprise_agent/core/agent/tools/team.py:194` — `Path.cwd()`

**描述:**
`AsyncMessageBus` 和 `TeammateConfig` 的默认工作目录使用 `Path.cwd()`，而不是统一的 `get_user_workspace()`。虽然 `TeammateManager` 传入正确的工作区路径，但 fallback 行为不一致。

**影响:**
如果直接使用 `AsyncMessageBus()` 或 `TeammateConfig()` 而非通过 Manager，会使用错误的目录。

---

### P1-9: Repeated `ALL_TOOLS` import

**文件:** `enterprise_agent/core/agent/nodes.py:290`

**描述:**
`tool_executor_node` 函数体内部重新导入了 `ALL_TOOLS`，但该变量已在文件顶部（第 34 行）通过 `from enterprise_agent.core.agent.tools import ALL_TOOLS` 导入了。

```python
# 第 290 行（冗余）
from enterprise_agent.core.agent.tools import ALL_TOOLS
```

---

### P1-10: Dockerfile 入口点不一致

**文件:** `docker/Dockerfile:28` vs `pyproject.toml:43`

**描述:**
pyproject.toml 定义入口为 `serve = "enterprise_agent.api.main:run"`（即 `uv run serve`），但 Dockerfile 使用 `python -m enterprise_agent.api.main`。两者应该统一。

---

### P1-11: Docker Compose 不加载 `.env` 文件

**文件:** `docker/docker-compose.yml:13-14`

**描述:**
docker-compose 只手动传递了 `ANTHROPIC_API_KEY` 和 `JWT_SECRET_KEY` 两个变量，但 `.env` 中的 `LLM_PROVIDER=mimo`、`LLM_BASE_URL`、`MODEL_ID` 等配置在容器中会丢失。

```yaml
environment:
  - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
  - JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production}
  # LLM_PROVIDER, LLM_BASE_URL, MODEL_ID 等缺失
```

---

### P1-12: Docker Compose Redis 使用不安全配置

**文件:** `docker/docker-compose.yml:46`

**描述:**
Redis 服务使用 `--protected-mode no` 且加载了 4 个额外模块（redisearch, rejson, redisbloom, redistimeseries），但实际只用到了基础 Redis 操作。这是安全风险和不必要的依赖膨胀。

---

### P1-13: `get_tools_for_permissions()` 已定义但未使用

**文件:** `enterprise_agent/core/agent/tools/__init__.py:120-169`

**描述:**
这个权限过滤函数定义完整，但没有任何地方调用。所有工具总是全部绑定到 LLM，空有权限体系但未实施。

**影响:**
"free"、"pro"、"admin" 角色实际上没有区分，所有用户都能使用全部工具。

---

### P1-14: `CORS_ORIGINS` 环境变量处理不健壮

**文件:** `enterprise_agent/api/main.py:40`

**描述:**
CORS origins 用逗号分割处理，但如果有尾随空格或空字符串，会产生空 origin。而且如果设置为 `*`，代码不会识别为通配符。

---

## P2 — 中等优先级

### P2-1: `.env.example` 与当前配置不一致
缺少 `CORS_ORIGINS`、`CHROMA_PERSIST_DIR`、`EMBEDDING_MODEL` 等新的配置项，且默认的 `LLM_PROVIDER=anthropic` 与实际使用的 `mimo` 不一致。

### P2-2: `ShortTermMemory` 类完全未被使用
文件 `memory/short_term.py` 实现了会话锁、工具缓存等功能，但没有任何代码 import 或使用它。

### P2-3: `utils/` 模块为空
`enterprise_agent/utils/__init__.py` 只有一个 docstring，没有任何工具函数。

### P2-4: `ToolUsageLog` 模型定义了但从未写入
模型定义完整但实际没有代码写日志。`ADMIN_ANALYTICS` 权限定义了但没有对应的分析端点。

### P2-5: AIOMySQL 在 Windows 上的潜在问题
`aiomysql` 依赖 MySQL 客户端 C 库，在 Windows 上安装经常失败，且开发环境使用 3307 端口映射。

### P2-6: `ChatResponse.message_id` 和 `SessionResponse.message_count` 永远为空
这两个字段在 Pydantic schema 中定义了但从未被赋值。

---

## P3 — 低优先级 / 建议

### P3-1: 没有管理员 API 路由
定义了 `Permission.ADMIN_USERS` 但没有对应的管理员端点。

### P3-2: Ruff 配置过于宽松
只启用了 `E, F, I, N` 规则，缺少复杂度检查（C90）、bug 检查（B）和安全检查（S）。

### P3-3: 缺少 Session 更新逻辑
`Session` 模型有 `updated_at` 字段但没有代码在消息交互后更新它。

### P3-4: `model_config` 中的 `extra: "ignore"` 可能隐藏配置错误
Settings 的 Pydantic 配置设为 `extra = "ignore"`，如果打错了环境变量名，不会报错而是静默忽略。

---

## 总结

| 优先级 | 数量 | 关键修复项 |
|--------|------|-----------|
| **P0** | 4 | Microcompact 失效、零测试覆盖、Streaming 不工作、密钥泄露 |
| **P1** | 14 | 架构不一致（全局 vs 用户隔离）、记忆注入逻辑、Redis db 冲突、配置问题等 |
| **P2** | 6 | 废弃代码、空模块、未使用特性 |
| **P3** | 4 | 缺失功能、代码质量改进 |

**建议修复顺序:**
1. P0-1 Microcompact 失效（核心功能）
2. P0-3 Streaming 修复（API 功能）
3. P1-1 ~ P1-5 架构一致性
4. P0-2 开始建立测试基础
5. 其余 P1 项
