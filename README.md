# Enterprise Agent System

企业级多用户AI Agent系统，基于LangGraph构建，支持用户认证、分层记忆管理（Redis短期+MySQL长期）。

## 技术栈

- **Agent引擎**: LangGraph + LangChain
- **API**: FastAPI (异步)
- **短期记忆**: Redis
- **长期记忆**: MySQL + SQLAlchemy 2.0
- **认证**: JWT + 角色权限
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
docker-compose up -d mysql redis

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
- POST `/auth/refresh` - 刷新Token

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
├── api/           # FastAPI路由、中间件
├── core/agent/    # LangGraph图、工具
├── memory/        # 短期/长期记忆
├── auth/          # JWT认证、权限
├── models/        # SQLAlchemy模型
├── db/            # Redis/MySQL连接
└── config/        # Pydantic配置
```

## 简历亮点

1. **架构设计**: 多层架构，清晰的模块边界
2. **技术栈现代化**: LangGraph有状态AI工作流
3. **企业特性**: 多用户隔离、认证授权、分层记忆
4. **生产部署**: Docker容器化、异步高性能

## License

MIT