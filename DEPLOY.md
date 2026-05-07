# 智云科技 AI 知识库系统 — 服务器部署指南

## 一、环境要求

| 项目 | 最低 | 推荐 |
|---|---|---|
| OS | Linux (Ubuntu 20.04+ / CentOS 7+) | Ubuntu 22.04 LTS |
| Python | 3.10+ | 3.12 |
| 内存 | 2 GB | 4 GB+ |
| 磁盘 | 5 GB | 20 GB+ (ChromaDB 随知识库增长) |
| 网络 | 可访问 dashscope.aliyuncs.com | 低延迟到阿里云杭州 |

## 二、部署步骤

### 2.1 获取代码

```bash
# 将整个 prototype/ 目录上传至服务器
scp -r prototype/ user@server:/opt/zhiyun-kb/
# 或使用 git
git clone <repo> /opt/zhiyun-kb/
```

### 2.2 安装 Python 环境

```bash
cd /opt/zhiyun-kb/prototype

# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2.3 配置环境变量

```bash
# 方式一：直接 export（临时）
export DASHSCOPE_API_KEY="sk-xxxxxxxxxxxxxxxx"

# 方式二：写入 .env 文件（推荐，配合 systemd）
cat > /opt/zhiyun-kb/prototype/.env << 'EOF'
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
EOF
```

### 2.4 初始化知识库

首次启动时会自动从 `seed_data.py` 的 10 条种子知识构建 ChromaDB 向量库：

```bash
source .venv/bin/activate
python3 -c "from knowledge_store import get_vector_store; get_vector_store()"
```

看到类似输出表示成功：
```
[Embedding] model=text-embedding-v2 | batch_size=10 | preview=BGP 震荡排查标准流程...
[Embedding] done | dims=1536 | count=10
```

### 2.5 启动服务

#### 方式 A：直接运行（开发/测试）

```bash
source .venv/bin/activate
python3 app.py
# 或
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
```

#### 方式 B：systemd 托管（推荐生产）

```bash
sudo tee /etc/systemd/system/zhiyun-kb.service << 'EOF'
[Unit]
Description=智云科技 AI 知识库系统
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/zhiyun-kb/prototype
EnvironmentFile=/opt/zhiyun-kb/prototype/.env
ExecStart=/opt/zhiyun-kb/prototype/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now zhiyun-kb
sudo systemctl status zhiyun-kb
```

### 2.6 Nginx 反向代理（可选）

```nginx
server {
    listen 80;
    server_name kb.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;  # LLM 调用可能需要较长时间
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 2.7 添加 HTTPS（推荐）

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d kb.your-domain.com
```

## 三、目录结构（服务器上）

```
/opt/zhiyun-kb/prototype/
├── .venv/                  # Python 虚拟环境
├── .env                    # 环境变量（敏感，权限 600）
├── chroma_db/              # ChromaDB 持久化向量数据
├── knowledge_system.db     # SQLite 数据库
├── app.py                  # FastAPI 入口
├── agent.py                # RAG Pipeline
├── knowledge_store.py      # 向量存储 & 百炼 Embedding
├── desensitizer.py         # 脱敏模块
├── escalation.py           # 升级逻辑
├── config.py               # 配置中心
├── models.py               # 数据模型
├── database.py             # SQLite CRUD
├── seed_data.py            # 种子知识库
├── requirements.txt
├── static/
│   └── index.html          # 前端
├── ARCHITECTURE.md         # 架构说明
└── DEPLOY.md               # 本文件
```

## 四、运维 Checklist

### 日常
- `systemctl status zhiyun-kb` — 检查服务运行状态
- `journalctl -u zhiyun-kb -f` — 实时查看日志（含 debug 日志）
- 定期备份 `knowledge_system.db` 和 `chroma_db/` 目录

### 更新知识库
- 通过前端「管理仪表盘 → 知识库同步」粘贴 Release Note JSON
- 或通过 API：`POST /api/knowledge/sync`
- 批量导入：修改 `seed_data.py` 后删除 `chroma_db/` 目录重启

### 切换模型
编辑 `config.py`：
```python
LLM_MODEL = "qwen-max"          # 更强，更贵
LLM_MODEL = "qwen-turbo"        # 更快，更便宜
EMBEDDING_MODEL = "text-embedding-v3"  # 更新一代
```

### 调整阈值
编辑 `config.py`：
```python
CONFIDENCE_GREEN = 0.85   # 更严格
CONFIDENCE_YELLOW = 0.65
RETRIEVAL_TOP_K = 8       # 检索更多文档
```

### 备份
```bash
# 备份数据库和向量库
tar czf backup-$(date +%Y%m%d).tar.gz \
  /opt/zhiyun-kb/prototype/knowledge_system.db \
  /opt/zhiyun-kb/prototype/chroma_db/
```

### 恢复
```bash
systemctl stop zhiyun-kb
tar xzf backup-20260501.tar.gz -C /opt/zhiyun-kb/prototype/
systemctl start zhiyun-kb
```

## 五、常见问题

### Q: 启动后 401 错误
`DASHSCOPE_API_KEY` 未设置或无效。检查：
```bash
sudo cat /opt/zhiyun-kb/prototype/.env
# 确认 key 格式为 sk-xxxxxxxx
```

### Q: Embedding 返回 400 InvalidParameter
ChromaDB 持久化数据是用旧 embedding 模型生成的，与当前模型不兼容。解决：
```bash
rm -rf /opt/zhiyun-kb/prototype/chroma_db/
systemctl restart zhiyun-kb  # 自动重建
```

### Q: LLM 响应时间过长
- 检查服务器到阿里云的网络延迟
- 将 `LLM_MODEL` 切换为 `qwen-turbo`
- Nginx `proxy_read_timeout` 适当加大

### Q: 如何添加更多知识文档
```python
# 方式一：通过 API
curl -X POST http://localhost:8000/api/knowledge/sync \
  -H "Content-Type: application/json" \
  -d '{"title":"新功能说明","version":"v1.0","content":"详细内容...","source_type":"GitLab"}'

# 方式二：修改 seed_data.py 后重建
rm -rf chroma_db/ && systemctl restart zhiyun-kb
```

### Q: 生产环境性能建议
- 使用 `gunicorn` + `uvicorn.workers` 多 worker 模式
- ChromaDB 在单进程下工作最好，多 worker 时需切换到 client/server 模式
- SQLite 并发写入有限，高并发场景考虑迁移到 PostgreSQL
