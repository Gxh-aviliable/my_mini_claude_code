# Enterprise Agent System

企业级多用户AI Agent系统，基于LangGraph构建，支持用户认证、分层记忆管理（Redis短期 + Chroma向量长期记忆）。

## 技术栈

- **Agent引擎**: LangGraph + LangChain
- **API**: FastAPI (异步)
- **短期记忆**: Redis（会话状态、分布式锁、工具缓存）
- **长期记忆**: Chroma 向量数据库（语义搜索、用户行为模式）
- **状态持久化**: LangGraph RedisSaver checkpointer
- **数据库**: MySQL（用户认证、会话管理）
- **认证**: JWT + 角色权限
- **LLM Provider**: Anthropic / GLM / DeepSeek / OpenAI / MiMo（5个provider）
- **部署**: Docker
- **包管理**: uv

## 快速启动

```bash
# 1. 克隆项目
git clone https://github.com/Gxh-aviliable/my_mini_claude_code.git
cd my_mini_claude_code

# 2. 安装依赖 (使用 uv)
uv sync

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API keys 和数据库配置

# 4. Docker启动数据库
cd docker
docker compose up -d mysql redis

# 5. 初始化数据库
uv run python scripts/init_db.py

# 6. 启动服务
uv run serve
# 或
uv run uvicorn enterprise_agent.api.main:app --reload

# 7. 访问API
# http://localhost:8000/docs (Swagger UI)
```

## API接口

### 认证
- POST `/auth/register` - 用户注册
- POST `/auth/login` - 登录获取JWT
- POST `/auth/refresh` - 刷新Token（支持Token轮换）

### 对话
- POST `/chat/completions` - 非流式对话
- POST `/chat/stream` - 流式对话(SSE)

### 会话管理
- GET `/sessions` - 列出会话
- POST `/sessions` - 创建会话
- DELETE `/sessions/{id}` - 删除会话

## 架构

```
enterprise_agent/
├── api/
│   ├── main.py              # FastAPI 应用入口、全局异常处理
│   ├── middleware/auth.py    # JWT 认证中间件
│   └── routes/
│       ├── auth.py          # 认证路由（注册/登录/刷新Token）
│       └── chat.py          # 对话路由（补全/流式/会话管理）
├── core/agent/
│   ├── graph.py             # LangGraph 工作流定义、RedisSaver checkpointer
│   ├── nodes.py             # Agent 节点（init/LLM/工具执行/压缩）
│   ├── state.py             # AgentState TypedDict 定义
│   ├── context.py           # 上下文管理、自动压缩
│   ├── llm_factory.py       # 多 LLM Provider 工厂
│   └── tools/
│       ├── shell.py         # Shell 命令执行（安全校验）
│       ├── background.py    # 后台任务管理
│       ├── subagent.py      # 子代理工具
│       ├── team.py          # 多 Agent 协作
│       ├── task.py          # 任务/TODO 管理
│       ├── skills.py        # 技能加载器
│       ├── file_ops.py      # 文件操作工具
│       ├── context_tools.py # 上下文压缩工具
│       └── __init__.py      # 工具注册表
├── memory/
│   ├── base.py              # MemoryBase 抽象接口
│   ├── short_term.py        # Redis 短期记忆（锁/缓存/状态）
│   └── long_term.py         # Chroma 向量长期记忆
├── auth/
│   ├── jwt_handler.py       # JWT 生成/验证（支持 Token 轮换）
│   └── permissions.py       # 角色权限定义
├── models/
│   ├── user.py              # 用户模型
│   ├── session.py           # 会话模型
│   ├── api_key.py           # API Key 模型
│   └── tool_usage.py        # 工具使用日志
├── db/
│   ├── mysql.py             # MySQL 连接（SQLAlchemy async）
│   ├── redis.py             # Redis 连接池
│   └── chroma.py            # Chroma 向量数据库初始化
├── config/
│   └── settings.py          # Pydantic 配置（环境变量验证）
└── utils/
    └── __init__.py
```

## LLM Provider 配置

支持 5 个 LLM Provider，在 `.env` 中配置：

```bash
LLM_PROVIDER=mimo          # anthropic / glm / deepseek / openai / mimo
LLM_API_KEY=your-api-key
LLM_BASE_URL=              # 自定义 base URL（可选）
MODEL_ID=mimo-v2.5-pro     # 模型标识符
```

## 简历亮点

1. **架构设计**: 多层架构，清晰的模块边界，LangGraph 有状态 AI 工作流
2. **多 LLM 支持**: 工厂模式支持 5 个 LLM Provider（Anthropic/GLM/DeepSeek/OpenAI/MiMo）
3. **企业特性**: 多用户隔离、JWT 认证授权、Token 轮换、角色权限
4. **分层记忆**: RedisSaver 自动状态持久化 + Chroma 向量语义搜索 + Redis 锁/缓存
5. **生产部署**: Docker 容器化、全局异常处理、异步高性能
6. **安全加固**: Shell 命令白名单、JWT 密钥启动校验、CORS 配置化

## License

MIT
