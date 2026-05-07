"""Seed data for D1 (public) and D2 (restricted) knowledge bases."""

AI_KNOWLEDGE_ENTRIES = [
    {
        "title": "BGP 震荡排查标准流程",
        "category": "网络故障排查",
        "keywords": "BGP,震荡,邻居,路由器,MTU",
        "content": (
            "BGP 震荡排查标准流程：\n"
            "1. 登录核心路由器，执行 show bgp summary 检查邻居状态。重点关注 State 列是否为 Established，"
            "以及 Up/Down 时间是否频繁变化。\n"
            "2. 若发现邻居反复 Up/Down，检查物理链路：show interface 查看 CRC 错误和接口 flapping 计数。\n"
            "3. 若物理链路正常，检查 BGP 配置：show run | section bgp 确认 AS 号、邻居 IP、"
            "keepalive/hold timer 设置是否与对端一致。\n"
            "4. 常见根因：MTU 不匹配（检查路径 MTU Discovery）、链路质量劣化（丢包 > 1%）、"
            "对端设备重启导致 TCP session 重建。\n"
            "5. 临时规避：在确认非配置错误后，可适当调大 hold timer（建议 30s → 60s）降低震荡频率。\n"
            "6. 永久修复需定位根因后提交变更窗口执行，变更前务必通知客户。"
        ),
    },
    {
        "title": "ERR-5043 数据库连接池耗尽 — 标准处理步骤",
        "category": "故障排查",
        "keywords": "ERR-5043,数据库,连接池,慢查询",
        "content": (
            "ERR-5043：数据库连接池耗尽 (Connection Pool Exhausted)\n"
            "触发条件：应用服务器数据库连接池使用率达到 100%，新请求无法获取连接。\n"
            "处理步骤：\n"
            "1. [紧急] 登录应用服务器，执行 show pool status 确认当前活跃连接数和等待队列长度。\n"
            "2. [紧急] 检查是否有慢查询阻塞：SELECT pid, query, state, age(now(), query_start) as duration "
            "FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 10;\n"
            "3. [紧急] 若存在超过 30 秒未完成的查询，经研发确认后可执行 pg_terminate_backend(pid) 终止。\n"
            "4. [临时] 临时增大连接池上限：在 application.yml 中修改 db.pool.max-size 从 20 → 40，重启应用。\n"
            "5. [永久] 定位慢查询根因，优化 SQL 或添加索引。检查 ORM N+1 查询问题。\n"
            "6. 处理完成后记录工单，标注触发原因和最终解决方案。"
        ),
    },
    {
        "title": "常见错误码速查表",
        "category": "参考文档",
        "keywords": "错误码,ERR,速查",
        "content": (
            "常见错误码速查表：\n"
            "ERR-1024：API 密钥无效或已过期 → 检查密钥是否在有效期内，确认未达到调用次数上限。\n"
            "ERR-2048：请求频率超限 (Rate Limit Exceeded) → 默认限制 1000 req/min，建议客户端实现指数退避重试。\n"
            "ERR-3072：数据格式校验失败 → 检查请求体 JSON 结构是否与 API 文档一致，特别注意必填字段和枚举值。\n"
            "ERR-4096：资源不存在或已被删除 → 确认资源 ID 是否正确，检查是否被软删除（deleted_at 字段非空）。\n"
            "ERR-5043：数据库连接池耗尽 → 参见《ERR-5043 标准处理步骤》文档。\n"
            "ERR-6144：第三方服务超时 → 检查上游服务健康状态，确认防火墙白名单是否变更。"
        ),
    },
    {
        "title": "客户问题分类与响应模板",
        "category": "客服规范",
        "keywords": "分类,模板,回复,客服",
        "content": (
            "客户问题分类与响应模板：\n"
            "A 类 — 查询类（约 40%）：客户询问功能使用方法、配置参数含义、API 文档位置等。\n"
            "  标准回复模板：「您好，关于 [功能名称] 的使用方法，请参考 [文档链接] 第 [页数] 页。"
            "简要说明如下：[一句话概述]。如有细节需要确认，欢迎继续沟通。」\n"
            "B 类 — 故障类（约 35%）：客户报告服务不可用、报错、性能下降等。\n"
            "  标准回复模板：「您好，我们已收到您关于 [问题描述] 的反馈，当前正在进行初步排查。"
            "根据现有文档，该问题可能与 [可能原因] 相关。我们将在 [SLA时间] 内给出明确结论。」\n"
            "C 类 — 配置变更类（约 15%）：客户请求修改配置、扩容、白名单变更等。\n"
            "  需要走变更审批流程，回复模板：「您好，您的 [变更类型] 请求已收到，"
            "我们将在确认变更窗口后与您沟通具体执行时间。预计窗口：下一个工作日 02:00-04:00。」\n"
            "D 类 — 投诉/紧急类（约 10%）：客户表达不满，或报告严重影响业务的故障。\n"
            "  标准回复需包含明确负责人和升级路径，同时抄送林总。"
        ),
    },
    {
        "title": "服务 SLA 承诺与违约条款",
        "category": "参考文档",
        "keywords": "SLA,承诺,违约,响应时间",
        "content": (
            "智云科技客户服务 SLA 承诺：\n"
            "响应时间：P0 级故障 ≤ 1 小时 / P1 级故障 ≤ 4 小时 / P2 级问题 ≤ 8 小时 / P3 级咨询 ≤ 24 小时。\n"
            "解决时间：P0 ≤ 4 小时 / P1 ≤ 24 小时 / P2 ≤ 72 小时 / P3 ≤ 5 个工作日。\n"
            "可用性承诺：核心服务 ≥ 99.9%（月度），不含计划内维护窗口。\n"
            "违约条款：\n"
            "1. 月度 SLA 达标率 < 95%，客户有权扣减当月服务费的 5%。\n"
            "2. 月度 SLA 达标率 < 80%，扣减 15%。\n"
            "3. 单次 P0 故障响应超时 ≥ 2 小时，需提交根因分析报告 (RCA) 并在 5 个工作日内完成整改。\n"
            "4. 连续两月 SLA 不达标，客户有权无条件终止合约。"
        ),
    },
    {
        "title": "工单升级判断标准",
        "category": "客服规范",
        "keywords": "升级,工单,二线,判断标准",
        "content": (
            "工单升级判断标准（一线 → 二线研发）：\n"
            "必须升级的情况：\n"
            "1. 问题涉及客户密钥、权限配置、安全漏洞等敏感领域 — 此类问题禁止 AI 回答。\n"
            "2. 知识库中无匹配结果，或所有匹配文档的相似度 < 0.3。\n"
            "3. AI 综合置信度 < 0.6（红色标签），禁止客服发送给客户。\n"
            "4. 客服在同一个工单上连续 3 次请求 AI 重新生成答案但均未采纳。\n"
            "5. 客户明确要求与工程师直接沟通。\n"
            "可选升级的情况：\n"
            "6. AI 置信度为黄色（0.6-0.8），客服核查后仍不确定。\n"
            "7. 问题超出知识库覆盖范围（如涉及第三方产品兼容性）。\n"
            "8. 客户要求的 SLA 等级较高（P0/P1）且客服无法自主决断。"
        ),
    },
    {
        "title": "敏感信息脱敏处理规范",
        "category": "安全规范",
        "keywords": "脱敏,敏感信息,安全,正则",
        "content": (
            "敏感信息脱敏处理规范：\n"
            "脱敏范围：客户工单中的以下信息在进入 AI 知识库前必须自动脱敏：\n"
            "1. API 密钥（包括 AWS AKIA/ASIA 前缀的 Access Key、以 sk- 开头的 OpenAI 风格密钥）。\n"
            "2. 密码类信息（包括数据库密码、服务账号密码、SSH 私钥）。\n"
            "3. Token 与凭证（JWT token、OAuth refresh token、Session cookie）。\n"
            "4. 网络地址信息（公网 IPv4/IPv6 地址、内网 IP 网段、域名）。\n"
            "5. 个人身份信息（手机号、身份证号、邮箱地址）。\n"
            "脱敏方式：正则匹配 + 占位符替换（如 [REDACTED_IP]），保留数据类型标识以便人工审核。\n"
            "合规要求：脱敏后的数据仍受数据保护政策约束，审计日志需记录脱敏操作的时间与范围。"
        ),
    },
]

RD_KNOWLEDGE_ENTRIES = [
    {
        "title": "内部缓存刷新 API 使用说明",
        "version": "v1.8.0",
        "keywords": "缓存,API,Redis,内部",
        "entry_type": "solution",
        "release_note": None,
        "source_ticket_id": None,
        "content": (
            "内部缓存刷新 API：POST /internal/api/v1/cache/refresh\n"
            "用途：当知识库内容更新后，调用此 API 刷新 Redis 缓存层，使新内容立即生效。\n"
            "权限要求：需要 Service Account Token（联系王工获取）。\n"
            "调用示例：curl -X POST https://internal-api.zycloud.com/internal/api/v1/cache/refresh "
            "-H 'Authorization: Bearer <service_token>' -H 'Content-Type: application/json' "
            "-d '{\"scope\": \"knowledge_base\", \"force\": false}'\n"
            "注意：force=true 会清空全部缓存并重新预热，耗时约 2-5 分钟，仅在紧急修复时使用。\n"
            "安全说明：此 API 需要通过安全审查后方可授权给支持团队使用，目前仅研发团队有权限。"
        ),
    },
    {
        "title": "Release Notes v5.1.0 — 数据库连接池优化",
        "version": "v5.1.0",
        "keywords": "Release Notes,数据库,连接池,优化",
        "entry_type": "release_note",
        "release_note": "数据库连接池从固定大小改为动态调整，新增连接池监控指标",
        "source_ticket_id": None,
        "content": (
            "Release Notes v5.1.0 (2026-03-15)\n"
            "变更类型：性能优化\n"
            "变更内容：\n"
            "1. 数据库连接池从固定大小改为动态调整，默认 min=5 / max=20，空闲 10 分钟后自动收缩。\n"
            "2. 新增连接池监控指标导出（Prometheus endpoint: /metrics/db-pool），可对接 Grafana 告警。\n"
            "3. 修复了之前版本中连接泄漏问题：事务未正确关闭导致连接无法归还池中。\n"
            "升级影响：需要更新 application.yml 配置文件，移除旧的 db.pool.fixed-size 参数。\n"
            "回滚方案：若升级后出现连接数不足，可临时设置环境变量 DB_POOL_MIN=10, DB_POOL_MAX=30 覆盖默认配置。"
        ),
    },
    {
        "title": "知识库文档版本管理规范",
        "version": "v2.1.0",
        "keywords": "版本管理,文档,SemVer,规范",
        "entry_type": "solution",
        "release_note": None,
        "source_ticket_id": None,
        "content": (
            "知识库文档版本管理规范：\n"
            "1. 所有公开发布的技术手册必须遵循语义化版本号 (SemVer)：主版本.次版本.修订号。\n"
            "2. 文档更新必须通过 GitLab Merge Request 流程，至少需要一位 Reviewer 审批。\n"
            "3. 旧版本文档应标记为「过期」而非删除，保留历史版本至少 12 个月。\n"
            "4. Release Notes 必须在每个版本发布前 24 小时完成，并由文档团队审核术语一致性。\n"
            "5. 紧急修复类文档（如安全补丁说明）走快速发布通道，审批时间 ≤ 4 小时。\n"
            "6. 文件名规范：禁止使用 'final'、'最终版' 等模糊后缀，必须以产品名+版本号命名。"
        ),
    },
]
