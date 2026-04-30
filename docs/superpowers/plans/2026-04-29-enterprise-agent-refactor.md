# 企业级多用户Agent系统重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将单用户REPL式Agent系统重构为支持多用户认证、分层记忆管理（Redis短期+MySQL长期）的企业级LangGraph Agent系统，适合作为暑期实习简历展示项目。

**Architecture:**
- 分层架构：API Gateway(FastAPI) → Service Layer → Agent Engine(LangGraph) → Memory Layer(Redis+MySQL)
- 用户认证：JWT token + 角色权限控制
- 记忆隔离：基于user_id的session管理，短期对话存Redis，长期模式存MySQL
- 工作流：LangGraph有状态图，支持中断恢复和检查点

**Tech Stack:** LangGraph + LangChain + FastAPI + Redis + MySQL + SQLAlchemy 2.0 + JWT + Docker

---

## Context

**现有系统分析：**
- 单用户REPL循环（mini_claude_code.py约740行）
- 工具系统：22个工具（bash/read/write/edit/task/skills等）
- 无用户认证、无多用户隔离、无持久化记忆
- 会话结束数据丢失

**重构目标：**
1. 企业级多用户支持
2. 用户认证系统（推荐实现）
3. 短期记忆Redis存储（对话历史、会话状态）
4. 长期记忆MySQL存储（用户配置、历史会话、学习模式）
5. LangGraph替代原有agent_loop
6. 生产级部署能力（Docker）
7. 简历展示价值

---

## Phase 1: 项目初始化与数据层（Week 1-2）

### Task 1: 项目结构搭建

**Files:**
- Create: `enterprise_agent/__init__.py`
- Create: `enterprise_agent/api/__init__.py`
- Create: `enterprise_agent/core/__init__.py`
- Create: `enterprise_agent/memory/__init__.py`
- Create: `enterprise_agent/auth/__init__.py`
- Create: `enterprise_agent/models/__init__.py`
- Create: `enterprise_agent/db/__init__.py`
- Create: `enterprise_agent/utils/__init__.py`
- Create: `enterprise_agent/config/__init__.py`
- Create: `requirements.txt`
- Create: `pyproject.toml`

- [ ] **Step 1: 创建项目目录结构**

```bash
mkdir -p enterprise_agent/api/routes enterprise_agent/api/middleware enterprise_agent/api/schemas
mkdir -p enterprise_agent/core/agent/tools enterprise_agent/core/workflow
mkdir -p enterprise_agent/memory enterprise_agent/auth enterprise_agent/models
mkdir -p enterprise_agent/db enterprise_agent/utils enterprise_agent/config
mkdir -p tests/test_api tests/test_core tests/test_memory
mkdir -p docker scripts
```

- [ ] **Step 2: 创建requirements.txt**

```text
# Core
langgraph>=0.2.0
langchain>=0.3.0
langchain-anthropic>=0.3.0

# API
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
python-multipart>=0.0.20

# Database
sqlalchemy[asyncio]>=2.0.0
aiomysql>=0.2.0
redis[asyncio]>=5.0.0
alembic>=1.14.0

# Auth
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
pydantic[email]>=2.10.0

# Utils
python-dotenv>=1.0.0
pyyaml>=6.0.0
structlog>=25.0.0

# Testing
pytest>=8.0.0
pytest-asyncio>=0.25.0
httpx>=0.28.0
```

- [ ] **Step 3: 创建pyproject.toml**

```toml
[project]
name = "enterprise-agent"
version = "0.1.0"
description = "Enterprise-level multi-user AI Agent system with LangGraph"
requires-python = ">=3.11"

[project.scripts]
serve = "enterprise_agent.api.main:run"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 120
select = ["E", "F", "I", "N"]
```

- [ ] **Step 4: 创建各模块__init__.py**

每个__init__.py添加基本导出，例如：
```python
# enterprise_agent/__init__.py
"""Enterprise Agent System - Multi-user LangGraph-based AI Agent"""

__version__ = "0.1.0"
```

- [ ] **Step 5: Commit**

```bash
git add enterprise_agent/ requirements.txt pyproject.toml
git commit -m "feat: initialize enterprise agent project structure"
```

---

### Task 2: 配置管理

**Files:**
- Create: `enterprise_agent/config/settings.py`
- Create: `enterprise_agent/utils/config.py`
- Create: `.env.example`

- [ ] **Step 1: 创建settings.py**

```python
# enterprise_agent/config/settings.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Enterprise Agent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Database - MySQL
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "agent_user"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "enterprise_agent"

    # Database - Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM
    ANTHROPIC_API_KEY: str = ""
    MODEL_ID: str = "claude-sonnet-4-6"

    # Memory
    SHORT_TERM_TTL_HOURS: int = 24
    MAX_MESSAGES_PER_SESSION: int = 100
    TOKEN_THRESHOLD: int = 100000

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

- [ ] **Step 2: 创建.env.example**

```text
# App
DEBUG=false

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=agent_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=enterprise_agent

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Auth
JWT_SECRET_KEY=your-secret-key-change-in-production

# LLM
ANTHROPIC_API_KEY=your-api-key
MODEL_ID=claude-sonnet-4-6
```

- [ ] **Step 3: Commit**

```bash
git add enterprise_agent/config/ enterprise_agent/utils/config.py .env.example
git commit -m "feat: add configuration management with Pydantic settings"
```

---

### Task 3: MySQL数据库模型

**Files:**
- Create: `enterprise_agent/models/user.py`
- Create: `enterprise_agent/models/session.py`
- Create: `enterprise_agent/models/conversation.py`
- Create: `enterprise_agent/models/tool_usage.py`
- Create: `enterprise_agent/models/user_pattern.py`
- Create: `enterprise_agent/models/api_key.py`
- Create: `enterprise_agent/db/mysql.py`
- Create: `scripts/init_db.py`

- [ ] **Step 1: 创建MySQL连接池**

```python
# enterprise_agent/db/mysql.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from enterprise_agent.config.settings import settings

class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    f"mysql+aiomysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@"
    f"{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}",
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
```

- [ ] **Step 2-8:** 详细代码见计划文档

---

### Task 4: Redis连接与短期记忆

**Files:**
- Create: `enterprise_agent/db/redis.py`
- Create: `enterprise_agent/memory/base.py`
- Create: `enterprise_agent/memory/short_term.py`

详细实现见计划文档。

---

## Phase 2: 认证系统（Week 2-3）

### Task 5: JWT认证实现

**Files:**
- Create: `enterprise_agent/auth/jwt_handler.py`
- Create: `enterprise_agent/auth/permissions.py`
- Create: `enterprise_agent/api/schemas/auth.py`

### Task 6: 认证API路由

**Files:**
- Create: `enterprise_agent/api/routes/auth.py`
- Create: `enterprise_agent/api/middleware/auth.py`

---

## Phase 3: Agent引擎核心（Week 3-5）

### Task 7: LangGraph状态定义

### Task 8: 工具迁移

### Task 9: LangGraph图构建

---

## Phase 4: API完善（Week 5-6）

### Task 10: 对话API

### Task 11: FastAPI主入口

---

## Phase 5: 部署与文档（Week 6-7）

### Task 12: Docker配置

### Task 13: README文档

---

## Verification

端到端测试流程见计划文档。

---

## 需要补充的内容

### 知识补充

1. **LangGraph深入** - 有状态工作流设计、Checkpointer持久化、子图嵌套
2. **异步Python** - async/await模式、SQLAlchemy异步操作、Redis异步客户端
3. **生产实践** - 日志结构化、监控指标、错误追踪

### 功能扩展建议

1. 长期记忆优化 - 用户模式学习、智能上下文检索
2. API增强 - WebSocket实时通信、后台任务管理、速率限制
3. 安全加固 - HTTPS配置、API密钥管理、输入验证增强
4. 监控运维 - 健康检查端点、性能指标收集、告警配置

---

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ENTERPRISE AGENT SYSTEM                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │
│  │   Web UI    │    │  CLI Client │    │  API Client │                    │
│  │  (React)    │    │  (Typer)    │    │  (SDK)      │                    │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                    │
│         │                  │                  │                            │
│         └──────────────────┼──────────────────┘                            │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        API Gateway (FastAPI)                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐    │   │
│  │  │  Auth    │  │  Rate    │  │  Router  │  │  WebSocket       │    │   │
│  │  │  (JWT)   │  │  Limiter │  │  (REST)  │  │  (Streaming)    │    │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    LangGraph Agent Engine                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐       │   │
│  │  │  Graph State │  │  Node Graph  │  │  Tool Registry       │       │   │
│  │  │  (Memory)    │  │  (Workflow)  │  │  (22+ Tools)         │       │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                            │                                                │
│         ┌──────────────────┼──────────────────┐                            │
│         │                  │                  │                            │
│         ▼                  ▼                  ▼                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │
│  │   Redis     │    │   MySQL     │    │  LLM APIs   │                    │
│  │ (短期记忆)  │    │ (长期记忆)  │    │ (Claude等) │                    │
│  │ - Sessions  │    │ - Users     │    └─────────────┘                    │
│  │ - Cache    │    │ - Conversations                                  │
│  │ - Pub/Sub  │    │ - Preferences                                    │
│  │ - Locks    │    │ - Analytics                                      │
│  └─────────────┘    └─────────────┘                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 简历展示要点

1. **架构能力** - 设计并实现多用户企业级AI代理系统，分层架构清晰
2. **技术栈现代化** - LangGraph有状态AI工作流、FastAPI异步高性能
3. **企业特性** - 多用户数据隔离、JWT认证授权、分层记忆管理
4. **生产级实现** - Docker容器化部署、完整的API文档、端到端测试

---

## 完整计划文件位置

详细实施步骤请查看：`docs/superpowers/plans/2026-04-29-enterprise-agent-refactor.md`