import os

# --- 阿里百炼 (OpenAI 兼容模式) ---
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-your-key-here")
BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = "qwen-plus"
EMBEDDING_MODEL = "text-embedding-v2"

# --- Confidence Thresholds ---
CONFIDENCE_GREEN = 0.8   # >= 0.8: safe to send directly
CONFIDENCE_YELLOW = 0.6  # >= 0.6: needs manual review
# < 0.6: RED → blocked, forced escalation

# --- Retrieval ---
RETRIEVAL_TOP_K = 5
SIMILARITY_THRESHOLD = 0.3  # minimum relevance score

# --- Five forbidden answer categories (BR-02) ---
FORBIDDEN_PATTERNS = [
    # 1. Security incident response
    (r"(安全事件|安全漏洞|入侵检测|DDoS|被攻击|数据泄露)", "安全事件响应"),
    # 2. Known vulnerability details
    (r"(已知漏洞|CVE-\d+|漏洞细节|exploit|攻击载荷)", "已知漏洞细节"),
    # 3. Customer sensitive config / credentials
    (r"(客户.{0,5}(密钥|密码|token|凭证|AKIA|AccessKey|SecretKey|私钥|证书))", "客户敏感配置与密钥"),
    (r"(数据库密码|root密码|admin密码|API.{0,3}(key|密钥|密码))", "客户敏感配置与密钥"),
    # 4. Legal compliance
    (r"(法律合规|GDPR|数据保护|隐私政策|合同条款|合规审查)", "法律合规"),
    # 5. Unreleased product features
    (r"(未发布.{0,3}(功能|特性|产品)|内测功能|beta.{0,3}(功能|特性))", "未发布产品功能"),
]

# --- Sensitive Info Desensitization Patterns (Process 6) ---
DESENSITIZE_PATTERNS = [
    (r'sk-[A-Za-z0-9]+', '[REDACTED_API_KEY]'),
    (r'(?:AKIA|ASIA)[A-Z0-9]{16}', '[REDACTED_AWS_KEY]'),
    (r'(?:password|passwd|pwd)\s*[:=]\s*\S+', '[REDACTED_PASSWORD]'),
    (r'(?:token|secret)\s*[:=]\s*\S+', '[REDACTED_TOKEN]'),
    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[REDACTED_IP]'),
    (r'\b1[3-9]\d{9}\b', '[REDACTED_PHONE]'),
    (r'\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b', '[REDACTED_ID]'),
]

# --- Vector Store ---
CHROMA_PERSIST_DIR = "./chroma_db"

# --- Database ---
SQLITE_PATH = "./knowledge_system.db"
