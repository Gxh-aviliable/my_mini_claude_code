# Enterprise Agent System

企业级多用户AI Agent系统，基于LangGraph构建，支持用户认证、分层记忆管理（Redis短期 + Chroma向量长期记忆）、Web前端界面。

## 技术栈

- **Agent引擎**: LangGraph + LangChain（有状态工作流）
- **API**: FastAPI（异步）+ SSE流式响应
- **前端**: Vue 3 + Vite
- **短期记忆**: Redis（会话状态、分布式锁、工具缓存、LangGraph RedisSaver）
- **长期记忆**: Chroma向量数据库（语义搜索、用户行为模式、重要性评估、衰减清理）
- **数据库**: MySQL（用户认证、会话管理）
- **认证**: JWT + 角色权限 + Token轮换
- **LLM Provider**: Anthropic / GLM / DeepSeek / OpenAI / MiMo（5个provider）
- **可观测性**: LangSmith tracing（可选）
- **部署**: Docker Compose
- **包管理**: uv（Python）+ npm（前端）

## 快速启动

### 方式一：完整启动（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/Gxh-aviliable/my_mini_claude_code.git
cd my_mini_claude_code

# 2. 启动数据库服务（MySQL + Redis）
cd docker
docker compose up -d mysql redis
cd ..

# 3. 安装 Python 依赖
uv sync

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入：
#   - LLM_API_KEY（必填）
#   - JWT_SECRET_KEY（必填，生产环境需更换）
#   - 其他配置按需修改

# 5. 启动后端 API
uv run serve
# 或开发模式（热重载）
uv run uvicorn enterprise_agent.api.main:app --reload

# 6. 启动前端（新终端）
cd frontend
npm install
npm run dev

# 7. 访问应用
# - 前端界面: http://localhost:3000
# - API文档: http://localhost:8000/docs
# - 健康检查: http://localhost:8000/health
```

### 方式二：Docker一键部署

```bash
cd docker
docker compose up -d
# 所有服务一键启动（API + MySQL + Redis）
# API: http://localhost:8000
```

### 方式三：仅后端（开发测试）

```bash
# 仅启动数据库
cd docker && docker compose up -d mysql redis && cd ..

# 启动后端
uv run serve
```

## 项目结构

```
enterprise_agent/
├── api/
│   ├── main.py              # FastAPI应用入口、全局异常处理、生命周期管理
│   ├── middleware/
│   │   └── auth.py          # JWT认证中间件
│   ├── routes/
│   │   ├── auth.py          # 认证路由（注册/登录/Token刷新）
│   │   ├── chat.py          # 对话路由（补全/流式SSE/会话管理）
│   │   └── workspace.py     # 工作区路由（文件树/文件读写）
│   └── schemas/
│       ├── auth.py          # 认证请求/响应模型
│       └── chat.py          # 对话请求/响应模型
├── core/agent/
│   ├── graph.py             # LangGraph工作流定义、RedisSaver checkpointer
│   ├── nodes.py             # Agent节点（init/LLM/工具执行/压缩/microcompact）
│   ├── state.py             # AgentState TypedDict定义
│   ├── context.py           # 上下文管理、自动压缩、token阈值监控
│   ├── llm_factory.py       # 多LLM Provider工厂（Anthropic/GLM/DeepSeek/OpenAI/MiMo）
│   └── tools/
│       ├── __init__.py      # 工具注册表（动态加载）
│       ├── shell.py         # Shell命令执行（白名单安全校验）
│       ├── file_ops.py      # 文件读写操作（Edit/Write）
│       ├── background.py    # 后台任务管理（异步执行/状态追踪）
│       ├── subagent.py      # 子代理工具（独立任务执行）
│       ├── team.py          # 多Agent协作（spawn_teammate/send_message/broadcast）
│       ├── task.py          # 任务/TODO管理（TodoWrite协议）
│       ├── skills.py        # 技能加载器（动态skill发现）
│       ├── context_tools.py # 上下文压缩工具
│       └── workspace.py     # 工作区管理工具
├── memory/
│   ├── base.py              # MemoryBase抽象接口
│   ├── short_term.py        # Redis短期记忆（锁/缓存/状态）
│   ├── long_term.py         # Chroma向量长期记忆（语义存储/检索）
│   ├── importance.py        # 重要性评估（LLM评估+启发式规则）
│   ├── decay.py             # 记忆衰减机制（自动清理低价值记忆）
│   └── pattern_extractor.py # 用户行为模式提取
├── auth/
│   ├── jwt_handler.py       # JWT生成/验证（支持Token轮换）
│   └── permissions.py       # 角色权限定义
├── models/
│   ├── user.py              # 用户模型
│   ├── session.py           # 会话模型
│   ├── api_key.py           # API Key模型
│   └── tool_usage.py        # 工具使用日志
├── db/
│   ├── mysql.py             # MySQL连接（SQLAlchemy async）
│   ├── redis.py             # Redis连接池
│   └── chroma.py            # Chroma向量数据库初始化
├── config/
│   └── settings.py          # Pydantic配置（环境变量验证、启动安全校验）
└── utils/
    └── __init__.py

frontend/
├── src/
│   ├── App.vue              # 主应用组件
│   ├── main.js              # Vue入口
│   ├── api/
│   │   └── client.js        # API客户端（axios封装、SSE处理）
│   ├── components/
│   │   ├── ChatPanel.vue    # 聊天面板（消息展示、输入、流式渲染）
│   │   ├── FileManager.vue  # 文件管理器（编辑/预览）
│   │   ├── FileTree.vue     # 文件树组件
│   │   ├── LoginForm.vue    # 登录表单
│   │   ├── SessionList.vue  # 会话列表
│   │   ├── Sidebar.vue      # 侧边栏导航
│   │   └── TreeNode.vue     # 树节点组件
│   └── stores/
│       └── auth.js          # 认证状态管理
├── package.json
└── vite.config.js           # Vite配置（API代理）

tests/
├── conftest.py              # pytest配置、fixtures
├── core/
│   ├── test_nodes.py        # Agent节点测试
│   ├── test_state.py        # 状态模型测试
│   └── tools/               # 工具测试套件
│       ├── test_shell.py
│       ├── test_file_ops.py
│       ├── test_background.py
│       ├── test_subagent.py
│       ├── test_team.py
│       ├── test_task.py
│       └── test_skills.py
└── memory/
    └── test_memory.py       # 记忆系统测试

docker/
├── Dockerfile               # API服务镜像
└── docker-compose.yml       # 完整服务编排
```

## API接口

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 用户注册 |
| POST | `/auth/login` | 登录获取JWT |
| POST | `/auth/refresh` | 刷新Token（支持Token轮换） |

### 对话
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/completions` | 非流式对话 |
| POST | `/chat/stream` | 流式对话（SSE） |

### 会话管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions` | 列出用户会话 |
| POST | `/sessions` | 创建新会话 |
| DELETE | `/sessions/{id}` | 删除会话 |

### 工作区
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workspace/tree` | 获取文件树 |
| GET | `/workspace/file` | 读取文件内容 |
| PUT | `/workspace/file` | 写入文件 |

## 配置说明

### 环境变量（.env）

```bash
# 应用配置
DEBUG=false
CORS_ORIGINS=http://localhost:3000

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3307
MYSQL_USER=agent_user
MYSQL_PASSWORD=agent_password
MYSQL_DATABASE=enterprise_agent

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# JWT认证（生产环境必须更换！）
JWT_SECRET_KEY=your-secret-key

# LLM配置（支持5个Provider）
LLM_PROVIDER=deepseek              # anthropic / glm / deepseek / openai / mimo
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.deepseek.com/anthropic  # 可选，自定义endpoint
MODEL_ID=deepseek-v4-pro

# LangSmith tracing（可选，可视化Agent执行）
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=enterprise-agent

# 向量数据库
CHROMA_PERSIST_DIR=./chroma_data
EMBEDDING_MODEL=all-MiniLM-L6-v2

# HuggingFace离线模式（使用缓存模型）
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

### LLM Provider配置

| Provider | API Key | Base URL（默认） |
|----------|---------|------------------|
| anthropic | ANTHROPIC_API_KEY | - |
| glm | LLM_API_KEY | https://open.bigmodel.cn/api/paas/v4 |
| deepseek | LLM_API_KEY | https://api.deepseek.com |
| openai | LLM_API_KEY | https://api.openai.com/v1 |
| mimo | LLM_API_KEY | https://api.xiaomimomo.com/anthropic |

DeepSeek支持Anthropic兼容endpoint（`/anthropic`）和OpenAI兼容endpoint（`/v1`）。

### Agent行为配置（settings.py）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| TOKEN_THRESHOLD | 500000 | Token阈值触发压缩 |
| MAX_AGENT_ROUNDS | 50 | 最大LLM→工具循环轮数 |
| COMMAND_TIMEOUT_SECONDS | 120 | Shell命令超时 |
| AGENT_INVOKE_TIMEOUT_SECONDS | 600 | 单次graph调用超时 |
| ENABLE_TOOL_CONFIRMATION | true | 敏感工具人工确认 |
| ENABLE_EDIT_VERIFICATION | true | Edit后自动验证 |
| ENABLE_WRITE_VERIFICATION | true | Write后自动验证 |

## 测试

```bash
# 运行所有测试
uv run pytest

# 运行指定模块测试
uv run pytest tests/core/test_nodes.py
uv run pytest tests/memory/

# 带覆盖率
uv run pytest --cov=enterprise_agent
```

## 核心特性

### 1. 有状态Agent工作流（LangGraph）
- RedisSaver自动状态持久化（支持暂停/恢复）
- 流式执行（SSE + interrupt支持人工确认）
- 多轮对话上下文管理
- Token阈值自动压缩

### 2. 分层记忆系统
- **短期记忆**：Redis存储会话状态、分布式锁、工具缓存
- **长期记忆**：Chroma向量语义存储、重要性评估、衰减清理
- **模式提取**：自动识别用户行为偏好

### 3. 多LLM Provider支持
- 工厂模式统一接口
- Anthropic/GLM/DeepSeek/OpenAI/MiMo无缝切换
- 支持自定义Base URL

### 4. 企业级安全
- JWT认证 + Token轮换
- Shell命令白名单
- 敏感工具人工确认（write/edit/bash等）
- 操作后自动验证（防止幻觉）
- 启动时JWT密钥校验

### 5. 多Agent协作
- spawn_teammate：创建协作Agent
- send_message：点对点消息
- broadcast：广播消息
- 独立context隔离

### 6. 可观测性
- LangSmith tracing（可视化执行流程）
- 结构化日志
- 健康检查endpoint

### 7. Web前端
- Vue 3响应式界面
- SSE流式消息渲染
- 文件管理器集成
- 会话列表导航

## 简历亮点

1. **架构设计**：多层架构、清晰模块边界、LangGraph有状态AI工作流、RedisSaver持久化
2. **多LLM支持**：工厂模式支持5个Provider，Anthropic兼容协议
3. **企业特性**：多用户隔离、JWT认证授权、Token轮换、角色权限
4. **分层记忆**：RedisSaver状态持久化 + Chroma向量语义搜索 + 重要性评估 + 衰减清理
5. **安全加固**：Shell白名单、敏感工具确认、操作验证、JWT密钥启动校验
6. **多Agent协作**：spawn_teammate创建队友、消息传递、独立context隔离
7. **可观测性**：LangSmith tracing可视化、结构化日志、健康检查
8. **生产部署**：Docker Compose容器化、全局异常处理、异步高性能
9. **Web界面**：Vue 3前端、SSE流式渲染、文件管理器集成

## 开发指南

```bash
# 安装开发依赖
uv sync --group dev

# 代码格式检查
uv run ruff check .

# 运行测试
uv run pytest
```

## License

MIT