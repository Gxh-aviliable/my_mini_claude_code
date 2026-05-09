# File Manager — Web 文件管理器设计

## 问题

多用户 AI Agent 部署到服务器后，AI 生成的文件全部存在服务器 workspace 内，用户只能通过聊天文本交互，无法获取实际文件。

## 方案选择

选择方案二：**Web 文件管理器**。在现有聊天系统旁新增完整的文件浏览/上传/下载/管理界面。

## 架构

```
Browser (Vue Frontend)
    ├── /chat/*        →  聊天（已有）
    ├── /sessions/*    →  会话管理（已有）
    ├── /auth/*        →  认证（已有）
    └── /workspace/*   →  文件管理（NEW）
            │
            ▼
    FastAPI Workspace Router (NEW)
    复用 workspace.py: get_user_workspace() + resolve_path()
            │
            ▼
    /workspaces/user_{id}/
```

## 后端 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /workspace/tree | 获取目录树 (?path=&depth=2&type=all) |
| GET | /workspace/read | 读取文件内容 (?path=&encoding=utf-8&offset=0&limit=200) |
| GET | /workspace/download | 下载单个文件 (?path=) |
| GET | /workspace/download-zip | 批量下载打包zip |
| POST | /workspace/upload | 上传文件 (FormData) |
| POST | /workspace/mkdir | 创建目录 |
| DELETE | /workspace/delete | 删除文件/目录 |
| PUT | /workspace/move | 移动/重命名 |

安全：所有端点通过 JWT 认证，路径经过 resolve_path() 校验。

## 前端设计

### 组件树

```
App.vue
├── LoginForm.vue
├── Sidebar.vue (NEW)
│   ├── SessionListView (已有)
│   └── FileTree.vue (NEW)
└── ContentArea.vue (NEW)
    ├── ChatPanel.vue (已有)
    └── FileManager.vue (NEW)
        ├── PathBar.vue
        ├── FileTable.vue
        └── FilePreview.vue
```

### 布局

Sidebar 带 Tab 切换（会话/文件），ContentArea 带 Tab 切换（Chat/Files）。

### 新增 API Client 方法

fetchTree, readFile, downloadFile, downloadZip, uploadFile, createDir, deleteItem, moveItem
