# 智云科技 AI 知识库系统 — 架构介绍与使用说明

## 一、系统定位

面向智云科技客服支持场景，用 RAG（检索增强生成）架构将散落在 PDF、GitLab、Excel 中的知识统一检索，AI 生成带引用来源的客服可复用回答，降低 60% 的工单升级率。

## 二、技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | 异步高性能，自动生成 OpenAPI 文档 |
| AI 编排 | LangChain 0.3 | RAG pipeline 编排（检索→生成→置信度） |
| LLM | 阿里百炼 qwen-plus | 通过 OpenAI 兼容接口调用 |
| Embedding | 阿里百炼 text-embedding-v2 | 原生 DashScope API（非兼容模式） |
| 向量库 | ChromaDB 0.5 | 本地嵌入存储，零运维开销 |
| 关系库 | SQLite | 工单、反馈、审计日志 |
| 前端 | 单页 HTML5 + Vanilla JS | 毛玻璃 UI，无构建工具依赖 |

## 三、系统架构

```
                            ┌──────────────────────┐
                            │   static/index.html   │
                            │   客服工作台 / 仪表盘   │
                            └──────────┬───────────┘
                                       │ HTTP
                            ┌──────────▼───────────┐
                            │      FastAPI 路由      │
                            │  app.py (9 endpoints) │
                            └──────────┬───────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
    ┌─────────▼─────────┐  ┌──────────▼──────────┐  ┌─────────▼─────────┐
    │   desensitizer.py │  │     agent.py        │  │   database.py     │
    │   P6 脱敏处理      │  │  P1 AI处理          │  │   D3 工单记录      │
    │   7 条正则脱敏      │  │  P2 知识沉淀         │  │   SQLite CRUD     │
    └───────────────────┘  └──────────┬──────────┘  └───────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼─────────┐  ┌─────────▼─────────┐  ┌─────────▼─────────┐
    │ knowledge_store.py│  │    escalation.py  │  │  config.py        │
    │ ChromaDB 向量存储   │  │  P4 升级 + P5 反馈 │  │  阈值/规则配置      │
    │ D1 AI知识库         │  │                   │  │                   │
    │ D2 研发知识库        │  │                   │  │                   │
    │ P3 发布同步         │  │                   │  │                   │
    └───────────────────┘  └───────────────────┘  └───────────────────┘
```

## 四、核心 Pipepline（agent.py）

```
用户查询
  │
  ├─ Step 1: 脱敏 (desensitizer)
  │   移除密钥/密码/IP/手机号/身份证
  │
  ├─ Step 2: 禁止类别检查
  │   5 类高危问题命中 → 标记警告，继续执行
  │
  ├─ Step 3: 向量检索 (knowledge_store)
  │   ChromaDB similarity_search → top-5 docs + 相似度分数
  │   检索异常 → 跳过，LLM 用通用知识回答
  │
  ├─ Step 4: LLM 生成 (百炼 qwen-plus)
  │   System prompt + 检索上下文 + 用户问题 → JSON 输出
  │   强制要求：answer / citations / confidence
  │
  ├─ Step 5: JSON 解析
  │   成功 → 提取结构化字段
  │   失败 → 返回原始文本, YELLOW label
  │
  ├─ Step 6: 引用验证 (软校验)
  │   有引用 → 进入置信度计算
  │   无引用 → 标记为通用知识回答
  │
  └─ Step 7: 置信度计算
     有知识库背景: blended = 检索相似度×0.4 + LLM自评×0.6
     无知识库背景: blended = LLM自评×0.8 (上限 0.5)
     → GREEN(≥0.8) / YELLOW(0.6-0.8) / RED(<0.6)
```

## 五、API 路由表

| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/` | 前端页面 |
| `GET` | `/docs` | FastAPI 自动生成的 Swagger 文档 |
| `POST` | `/api/tickets` | 创建工单 |
| `GET` | `/api/tickets` | 工单列表 (P7) |
| `GET` | `/api/tickets/{id}` | 工单详情 + AI 交互历史 |
| `POST` | `/api/query` | **核心：AI 智能查询 (P1)** |
| `POST` | `/api/query/{log_id}/feedback` | 提交回答反馈 (P2) |
| `POST` | `/api/knowledge/sync` | 同步 GitLab Release Note (P3) |
| `POST` | `/api/tickets/{id}/escalate` | 手动升级工单 (P4) |
| `POST` | `/api/escalations/{id}/resolve` | 解决升级工单 (P5) |
| `POST` | `/api/desensitize` | 脱敏测试 (P6) |
| `GET` | `/api/metrics` | 系统指标 (P8) |
| `GET` | `/api/health` | 健康检查 |

### 核心接口示例

**POST /api/query**
```json
// Request
{ "ticket_id": "abc12345", "query_text": "客户报错 ERR-5043，数据库连接池耗尽如何处理？" }

// Response
{
  "success": true,
  "data": {
    "log_id": "1a2b3c4d",
    "answer_text": "针对 ERR-5043...步骤1: 登录应用服务器...\n步骤2: 检查慢查询...",
    "citations": [
      {
        "doc_title": "ERR-5043 数据库连接池耗尽 — 标准处理步骤",
        "doc_version": "v5.1.0",
        "section": "",
        "snippet": "登录应用服务器，执行 show pool status..."
      }
    ],
    "confidence_score": 0.82,
    "confidence_label": "green",
    "escalation_required": false
  }
}
```

## 六、前端使用说明

### Tab 1: 客服工作台
1. 在文本框粘贴客户问题（口语化描述、报错代码均可）
2. 点击「提交查询」→ 自动创建工单 → 调用 AI 引擎
3. 返回结果包含：
   - **置信度标签**（绿/黄/红）及百分比
   - **AI 回答**（可直接复制）
   - **引用来源**（文档名、版本号、原文摘录）
4. 操作按钮：
   - 「复制回答」→ 粘贴到客服对话窗口
   - 「回答准确」/「回答有误」→ 反馈进知识沉淀流程 (P2)
   - 「升级至二线研发」→ 手动升级 (P4)
5. 脱敏测试区：输入含密钥/密码/IP 的文本 → 验证脱敏效果

### Tab 2: 工单管理
- 创建工单：手动输入客户问题描述 + 错误码
- 工单列表：查看所有工单的状态（待处理/AI处理中/待审核/已升级/已解决）

### Tab 3: 管理仪表盘
- 实时系统指标：总工单数、升级率、置信度分布（绿/黄/红占比）
- 知识库同步：粘贴 Release Note JSON → 同步至向量库

## 七、数据模型

### 实体关系
```
Agent(客服) 1 ──* Ticket(工单) 1 ──* AI_Interaction_Log(AI交互日志) *──1 Knowledge_Doc(知识文档)
                                                    │
                                                    └── 0..1 Feedback(反馈)
```

### 5 张核心表
- **tickets**: 工单（客户描述、错误码、状态、SLA 截止时间）
- **ai_logs**: 每次 AI 交互的完整记录（查询、回答、引用、置信度）
- **escalations**: 升级记录（原因、来源角色、是否解决）
- **feedbacks**: 人工反馈（准确/不准确、修正建议）
- **knowledge_docs**: 知识文档元数据（来源类型、版本、有效期）

## 八、关键业务规则

| 规则 | 实现位置 |
|---|---|
| 五类禁止回答（安全/漏洞/凭证/合规/未发布） | `config.py` `FORBIDDEN_PATTERNS` → `agent.py` Step 2 |
| 7 种敏感信息入库前脱敏 | `config.py` `DESENSITIZE_PATTERNS` → `desensitizer.py` |
| 置信度三级分色 (GREEN≥0.8 / YELLOW / RED<0.6) | `config.py` 阈值 → `agent.py` Step 7 |
| 回答必须携带引用来源 | `agent.py` System Prompt 强制要求 |
| 知识库无匹配时 LLM 自答但标注未覆盖 | `agent.py` Step 3→4 衔接逻辑 |
| 工单升级仅在客服手动触发时执行 | `app.py` POST `/api/tickets/{id}/escalate` |

## 九、配置项速查

```bash
# 必须设置
export DASHSCOPE_API_KEY="sk-xxxxxxxx"   # 阿里百炼 API Key

# 可选覆盖 (config.py 内修改)
LLM_MODEL = "qwen-plus"        # 也可用 qwen-max / qwen-turbo
EMBEDDING_MODEL = "text-embedding-v2"
RETRIEVAL_TOP_K = 5             # 检索返回文档数
CONFIDENCE_GREEN = 0.8          # 绿色置信度阈值
CONFIDENCE_YELLOW = 0.6         # 黄色置信度阈值
```
