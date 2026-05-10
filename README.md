# 智云科技 AI 知识库系统

基于 RAG（检索增强生成）的 AI 辅助客服系统，支持客户-客服-研发三方实时对话。

## 快速启动

```bash
export DASHSCOPE_API_KEY="sk-xxxxxxxxxxxxxxxx"  # 阿里百炼 API Key
python3 app.py
```

## 访问地址

| 页面 | URL | 说明 |
|---|---|---|
| 角色选择 | `http://localhost:8000/` | 入口页 |
| 客服坐席 | `http://localhost:8000/cs` | 一线客服工台 |
| 二线研发 | `http://localhost:8000/rd` | 升级工单处理 |
| 文档团队 | `http://localhost:8000/doc` | 知识提交与审核 |
| 管理层 | `http://localhost:8000/manager` | 仪表盘 |
| 客户页面 | `http://localhost:8000/customer` | 客户聊天窗口 |
| API 文档 | `http://localhost:8000/docs` | Swagger |

每个角色页面可在独立浏览器标签页中同时打开，互不干扰。

## 核心流程

1. **客户**在 `/customer` 发送问题 → 系统自动创建工单，分配客服
2. **客服**在 `/cs` 的「在线服务」看到会话 → 点击进入 → 点「询问 AI 助手」获取 AI 回答（含引用 + 置信度）→ 编辑后发送
3. 客服点「升级工单」→ **二线研发**在 `/rd` 看到升级工单 → 接管后直接回复客户
4. 服务结束 → 客户收到满意度调查

## 架构概览

```
客户(/customer) ──WebSocket──▶ 服务器 ◀──WebSocket── 客服(/cs)
                                                 ──WebSocket── 研发(/rd)
     │                              │
     └──── REST API ────────────────┘
                    │
            ┌───────┼───────┐
            │  agent.py     │  database.py
            │  RAG Pipeline │  SQLite
            │  ChromaDB     │
            └───────────────┘
```

详细架构见 [ARCHITECTURE.md](ARCHITECTURE.md)。
