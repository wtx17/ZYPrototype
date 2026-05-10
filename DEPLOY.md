# 智云科技 AI 知识库系统 — 部署指南

## 一、环境要求

| 项目 | 最低 | 推荐 |
|---|---|---|
| OS | Linux (Ubuntu 20.04+) | Ubuntu 22.04 LTS |
| Python | 3.10+ | 3.12 |
| 内存 | 2 GB | 4 GB+ |
| 磁盘 | 2 GB | 10 GB+ |
| 网络 | 可访问 dashscope.aliyuncs.com | 低延迟到阿里云 |

## 二、部署步骤

### 2.1 获取代码

```bash
git clone <repo> /opt/zhiyun-kb/
cd /opt/zhiyun-kb
```

### 2.2 安装依赖

```bash
pip3 install --break-system-packages -r requirements.txt
# 或使用虚拟环境：
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.3 配置环境变量

```bash
export DASHSCOPE_API_KEY="sk-xxxxxxxxxxxxxxxx"
```

### 2.4 初始化知识库

首次启动自动从 `seed_data.py` 构建 ChromaDB 向量库（7 条 D1 + 3 条 D2）。

### 2.5 启动服务

```bash
python3 app.py
# 访问 http://localhost:8000
```

#### systemd 托管

```bash
sudo tee /etc/systemd/system/zhiyun-kb.service << 'EOF'
[Unit]
Description=智云科技 AI 知识库系统
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/zhiyun-kb
Environment="DASHSCOPE_API_KEY=sk-xxxxxxxx"
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now zhiyun-kb
```

## 三、目录结构

```
/opt/zhiyun-kb/
├── app.py                  # FastAPI 入口 (REST + WebSocket)
├── agent.py                # RAG Pipeline
├── ws_manager.py           # WebSocket 连接管理、消息路由
├── knowledge_store.py      # ChromaDB 向量存储
├── desensitizer.py         # 脱敏模块
├── escalation.py           # 升级决策
├── config.py               # 配置中心
├── models.py               # Pydantic 模型
├── database.py             # SQLite CRUD (5 张表)
├── auth.py                 # 会话认证
├── seed_data.py            # 种子知识
├── requirements.txt
├── knowledge_system.db     # SQLite 数据库
├── chroma_db/              # ChromaDB 持久化目录
├── static/
│   ├── index.html          # 坐席工台
│   ├── customer.html       # 客户聊天页
│   ├── app.css / customer.css
│   └── js/
│       ├── main.js         # 入口
│       ├── auth.js / api.js / state.js / config.js / utils.js
│       ├── websocket.js / agent-workspace.js / agent-chat.js
│       ├── customer.js
│       ├── tabs/           # cs.js / rd.js / doc.js / manager.js
│       └── features/       # tickets.js
├── ARCHITECTURE.md
├── DEPLOY.md
└── README.md
```

## 四、备份与恢复

```bash
# 备份
tar czf backup-$(date +%Y%m%d).tar.gz knowledge_system.db chroma_db/

# 恢复
systemctl stop zhiyun-kb
tar xzf backup-20260501.tar.gz
systemctl start zhiyun-kb
```

## 五、常见问题

### Q: 启动后 AI 调用失败
确认 `DASHSCOPE_API_KEY` 已正确设置。

### Q: Embedding 报错
ChromaDB 数据与当前模型不兼容，清除后重建：
```bash
rm -rf chroma_db/
systemctl restart zhiyun-kb
```

### Q: WebSocket 连接失败
检查防火墙是否放行端口 8000。Nginx 反向代理需配置 WebSocket 支持：
```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```
