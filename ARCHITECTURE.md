# 智云科技 AI 知识库系统 — 架构介绍

## 一、系统定位

面向智云科技客服支持场景的 AI 辅助客服系统。客户通过聊天窗口发起问题，系统自动创建工单并分配给在线客服。客服可调用 RAG 流水线获取 AI 生成的回答（带引用来源与置信度），编辑后发送给客户。复杂问题可升级至二线研发处理。

## 二、技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | 异步 HTTP + WebSocket |
| AI 编排 | LangChain | RAG pipeline（检索→生成→置信度） |
| LLM | 阿里百炼 qwen-plus | OpenAI 兼容接口 |
| Embedding | 阿里百炼 text-embedding-v2 | DashScope API |
| 向量库 | ChromaDB | 本地持久化，D1/D2 双集合隔离 |
| 关系库 | SQLite | 工单、消息、反馈、知识库 |
| 前端 | Vanilla JS (ES Modules) | 无构建工具，毛玻璃 UI |
| 实时通讯 | FastAPI WebSocket | 客户-坐席双向消息 |

## 三、系统架构

```
                         ┌──────────────────────────────┐
                         │     static/customer.html      │
                         │     客户聊天页面 (微信风格)      │
                         └──────────────┬───────────────┘
                                        │ WebSocket
                         ┌──────────────▼───────────────┐
                         │         app.py                │
                         │   FastAPI (REST + WebSocket)  │
                         │   /ws/customer  /ws/agent     │
                         └──────────────┬───────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
  ┌───────▼────────┐  ┌────────────────▼──────────┐  ┌───────────────▼──┐
  │  ws_manager.py │  │       agent.py             │  │  database.py    │
  │  WS 连接管理     │  │  RAG Pipeline             │  │  SQLite CRUD    │
  │  消息路由        │  │  检索→脱敏→LLM→置信度      │  │  5 张表          │
  │  工单分配        │  └────────────┬──────────────┘  └──────────────────┘
  │  升级流转        │               │
  └────────────────┘  ┌──────────────┼──────────────┐
                      │              │              │
              ┌───────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐
              │knowledge_store│ │desensitizer│ │ escalation │
              │ ChromaDB D1/D2│ │ 7条正则脱敏 │ │ 升级决策     │
              └──────────────┘ └───────────┘ └────────────┘

                         ┌──────────────────────────────┐
                         │     static/index.html         │
                         │     坐席工台 (CS/RD/Doc/管理)  │
                         │     30/70 分屏 + AI 面板       │
                         └──────────────┬───────────────┘
                                        │ WebSocket + REST
                         ┌──────────────▼───────────────┐
                         │   /cs  /rd  /doc  /manager   │
                         │   独立 URL, sessionStorage 隔离│
                         └──────────────────────────────┘
```

## 四、核心 Pipeline（agent.py）

```
用户查询
  │
  ├─ Step 1: 脱敏 (desensitizer)
  │   移除密钥/密码/IP/手机号/身份证
  │
  ├─ Step 2: 禁止类别检查 (6 类)
  │   安全事件 / CVE 漏洞 / 客户密钥 / 数据库密码 / 法律合规 / 未发布功能
  │   命中 → 标记警告，继续执行
  │
  ├─ Step 3: D1 向量检索 (knowledge_store)
  │   ChromaDB similarity_search → top-5, 相似度阈值 > 0.3
  │
  ├─ Step 4: D2 角色隔离检查
  │   CS/管理层 → 仅存在性检查（不泄露内容）
  │   RD/文档 → 获取完整内容
  │
  ├─ Step 5: LLM 生成 (百炼 qwen-plus, temperature=0.1)
  │   System prompt + 检索上下文 → JSON 输出
  │   强制: answer / citations / confidence
  │
  ├─ Step 6: JSON 解析 + 引用验证
  │
  └─ Step 7: 置信度计算
     有知识库: blended = 检索相似度 × 0.4 + LLM自评 × 0.6
     无知识库: blended = LLM自评 × 0.8 (上限 0.5)
     → GREEN(≥0.8) / YELLOW(0.6-0.8) / RED(<0.6)
```

## 五、API 路由表

### REST 端点

| 方法 | 路由 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `/` | - | 角色选择页 |
| `GET` | `/cs` `/rd` `/doc` `/manager` | - | 角色坐席页（自动登录） |
| `GET` | `/customer` | - | 客户聊天页 |
| `POST` | `/api/auth/login` | - | 登录 |
| `GET` | `/api/auth/me` | - | 会话检查 |
| `POST` | `/api/auth/logout` | - | 登出 |
| `POST` | `/api/customer/token` | - | 生成客户匿名 token |
| `POST` | `/api/query` | CS/RD/Doc/Manager | AI 查询 (P1) |
| `POST` | `/api/knowledge/rd` | RD | 沉淀知识至 D2 (P2) |
| `POST` | `/api/knowledge/release-notes` | RD | 发布 Release Notes (P3) |
| `POST` | `/api/tickets/{id}/escalate` | CS | 升级工单至研发 (P4) |
| `POST` | `/api/escalations/{id}/resolve` | RD | 解决升级工单 (P5) |
| `POST` | `/api/knowledge/submit` | Doc | 提交知识待审核 (P6) |
| `POST` | `/api/knowledge/review/{id}` | Doc | 审核知识 (P6) |
| `GET` | `/api/knowledge/pending` | Doc | 待审核列表 |
| `GET` | `/api/knowledge/ai` | 所有角色 | D1 公开知识列表 |
| `GET` | `/api/knowledge/rd` | RD/Doc | D2 研发知识列表 |
| `GET` | `/api/tickets` | CS/RD/Manager | 工单列表 (P7) |
| `POST` | `/api/tickets` | - | 创建工单 |
| `GET` | `/api/tickets/{id}` | CS/RD/Manager | 工单详情 |
| `POST` | `/api/tickets/{id}/handling` | CS | 记录处理情况 (P7) |
| `GET` | `/api/metrics` | Manager | 系统指标 (P8) |
| `POST` | `/api/desensitize` | - | 脱敏测试 |
| `GET` | `/api/health` | - | 健康检查 |

### 实时通信端点（新增）

| 方法 | 路由 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `/api/cs/sessions` | CS | CS 活跃会话列表 |
| `GET` | `/api/rd/sessions` | RD | RD 升级工单列表 |
| `GET` | `/api/sessions/{ticket_id}` | CS/RD | 会话详情 + 消息 |
| `GET` | `/api/tickets/{id}/messages` | - | 消息历史 |
| `POST` | `/api/tickets/{id}/send-message` | CS/RD | 坐席发送消息（RD 需工单已升级） |
| `POST` | `/api/tickets/{id}/end-service` | CS/RD | 结束服务 |
| `POST` | `/api/tickets/{id}/satisfaction` | - | 客户提交满意度 |
| `WS` | `/ws/customer?token=` | - | 客户 WebSocket |
| `WS` | `/ws/agent?session_id=` | CS/RD | 坐席 WebSocket |

## 六、WebSocket 协议

所有消息统一 JSON：`{"type": "<类型>", "payload": { ... }}`

| type | 方向 | 说明 |
|---|---|---|
| `customer_message` | 客户→坐席 | 客户发送消息 |
| `agent_message` | 坐席→客户 | 坐席回复 |
| `system_message` | 服务器→双方 | 自动问候、升级通知 |
| `ai_request` | 坐席→服务器 | 请求 AI 协助 |
| `ai_response` | 服务器→坐席 | AI 生成结果 |
| `escalate` | 坐席→服务器 | 升级工单 |
| `escalation_transfer` | 服务器→坐席 | 通知 CS 退出 |
| `new_escalation` | 服务器→RD | 通知 RD 新升级 |
| `accept_escalation` | RD→服务器 | RD 接管工单 |
| `new_session` | 服务器→CS | 新客户会话通知 |
| `service_end` | 服务器→客户 | 服务结束，触发满意度 |
| `satisfaction` | 客户→服务器 | 客户提交反馈 |
| `ticket_closed` | 服务器→坐席 | 工单已关闭 |
| `ping` / `pong` | 双向 | 心跳 |

## 七、数据模型

### 5 张表

| 表 | 说明 |
|---|---|
| `ai_knowledge` | D1 公开知识库（审核后进入 ChromaDB） |
| `rd_knowledge` | D2 研发内部知识库 |
| `tickets` | 工单（含分配、升级、满意度状态） |
| `messages` | 会话消息（客户/坐席/系统） |
| `satisfaction_feedback` | 满意度反馈 |

### ER 关系

```
Customer ──▶ Ticket 1 ──* Message
                 │
                 ├── assigned_cs (客服)
                 ├── assigned_rd (研发)
                 ├── escalated_to_rd (升级标记)
                 └── 0..1 SatisfactionFeedback
```

## 八、前端模块结构

```
static/
├── index.html              # 坐席工台 (CS/RD/Doc/Manager)
├── customer.html           # 客户聊天页
├── app.css                 # 主样式（毛玻璃设计系统 + 坐席工台）
├── customer.css            # 客户页面样式（微信风格气泡）
└── js/
    ├── main.js             # 应用入口、路由、自动登录
    ├── auth.js             # 登录/登出、sessionStorage 管理
    ├── api.js              # REST API 客户端（session_id 注入）
    ├── state.js            # 全局状态管理
    ├── config.js           # 角色/标签页配置
    ├── utils.js            # 工具函数
    ├── websocket.js        # WebSocket 客户端封装
    ├── agent-workspace.js  # 坐席工台核心（会话列表/30:70分屏/AI面板）
    ├── agent-chat.js       # 坐席侧消息渲染
    ├── customer.js         # 客户侧 WebSocket 逻辑
    ├── tabs/
    │   ├── cs.js           # 客服：在线服务 + 脱敏 + 工单
    │   ├── rd.js           # 研发：升级工单 + 知识沉淀
    │   ├── doc.js          # 文档：知识提交 + 审核
    │   └── manager.js      # 管理：仪表盘 + 全部工单
    └── features/
        └── tickets.js      # 工单列表/详情
```

## 九、关键业务规则

| 规则 | 实现 |
|---|---|
| D1/D2 知识隔离（CS 不可见 D2 内容） | `agent.py` Step 4 + `knowledge_store.py` |
| 6 类禁止回答 | `config.py` `FORBIDDEN_PATTERNS` |
| 7 种敏感信息脱敏 | `config.py` `DESENSITIZE_PATTERNS` |
| 置信度三级分色 | `agent.py` Step 7 |
| 回答必须带引用来源 | System Prompt 强制要求 |
| RD 只能回复已升级工单 | `app.py` send-message 端点 + WebSocket 双重校验 |
| 工单由系统自动创建（客户发起会话时） | `ws_manager.py` `register_customer` |
| 多角色 sessionStorage 隔离 | `auth.js` + URL 路由 |

## 十、配置项

```bash
# 必须设置
export DASHSCOPE_API_KEY="sk-xxxxxxxx"

# config.py 可调参数
LLM_MODEL = "qwen-plus"
EMBEDDING_MODEL = "text-embedding-v2"
RETRIEVAL_TOP_K = 5
SIMILARITY_THRESHOLD = 0.3
CONFIDENCE_GREEN = 0.8
CONFIDENCE_YELLOW = 0.6
CS_ASSIGN_TIMEOUT = 30
MAX_MESSAGE_HISTORY = 100
```
