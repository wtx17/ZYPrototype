from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---

class TicketStatus(str, Enum):
    OPEN = "open"
    AI_PROCESSING = "ai_processing"
    PENDING_REVIEW = "pending_review"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ConfidenceLabel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class AgentRole(str, Enum):
    L1_AGENT = "L1_客服"
    L2_ENGINEER = "L2_研发"
    MANAGER = "管理层"
    DOC_TEAM = "文档团队"


# --- Core Models ---

class Ticket(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    customer_desc: str
    error_code: Optional[str] = None
    status: TicketStatus = TicketStatus.OPEN
    agent_id: str = "agent_xiao_chen"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    sla_deadline: Optional[str] = None


class AIQuery(BaseModel):
    ticket_id: str
    query_text: str


class Citation(BaseModel):
    doc_title: str
    doc_version: str
    section: str
    snippet: str


class AIResponse(BaseModel):
    log_id: str
    ticket_id: str
    query_text: str
    answer_text: str
    citations: list[Citation] = []
    confidence_score: float
    confidence_label: ConfidenceLabel
    is_blocked: bool = False
    block_reason: Optional[str] = None
    escalation_required: bool = False


class Escalation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    ticket_id: str
    log_id: Optional[str] = None
    reason: str
    from_role: AgentRole
    to_role: AgentRole = AgentRole.L2_ENGINEER
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    resolved: bool = False
    resolution_notes: Optional[str] = None


class Feedback(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    log_id: str
    agent_id: str
    is_accurate: bool
    correction_notes: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class KnowledgeDoc(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    source_type: str  # PDF / GitLab / Excel
    content: str
    version: str = "1.0"
    validity_status: str = "有效"  # 有效 / 过期
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SystemMetrics(BaseModel):
    total_tickets: int = 0
    avg_response_time_seconds: float = 0
    avg_resolution_time_hours: float = 0
    escalation_rate: float = 0
    green_rate: float = 0
    yellow_rate: float = 0
    red_rate: float = 0
    knowledge_base_usage_rate: float = 0


# --- Request / Response Helpers ---

class QueryResponse(BaseModel):
    success: bool
    data: Optional[AIResponse] = None
    error: Optional[str] = None


class DesensitizeRequest(BaseModel):
    text: str


class DesensitizeResponse(BaseModel):
    original: str
    desensitized: str
    changes: int


class MetricsResponse(BaseModel):
    success: bool
    data: SystemMetrics
