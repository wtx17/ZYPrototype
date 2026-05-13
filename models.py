from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---

class TicketStatus(str, Enum):
    PENDING = "pending"
    AI_PROCESSING = "ai_processing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ConfidenceLabel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class Role(str, Enum):
    CS = "cs"
    RD = "rd"
    DOC = "doc"
    MANAGER = "manager"


class EntryType(str, Enum):
    SOLUTION = "solution"
    RELEASE_NOTE = "release_note"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# --- Auth Models ---

class LoginRequest(BaseModel):
    role: str
    username: str


# --- D1: AI Knowledge ---

class AIKnowledge(BaseModel):
    id: Optional[int] = None
    title: str
    content: str
    category: Optional[str] = None
    keywords: Optional[str] = None
    review_status: str = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class KnowledgeSubmit(BaseModel):
    title: str
    content: str
    category: Optional[str] = None
    keywords: Optional[str] = None


class KnowledgeReview(BaseModel):
    review_status: str  # approved | rejected


# --- D2: R&D Knowledge ---

class RDKnowledge(BaseModel):
    id: Optional[int] = None
    title: str
    content: str
    keywords: Optional[str] = None
    version: Optional[str] = None
    release_note: Optional[str] = None
    source_ticket_id: Optional[int] = None
    entry_type: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# --- D3: Ticket ---

class TicketCreate(BaseModel):
    title: str
    description: Optional[str] = None
    created_by: str = "cs"


class Ticket(BaseModel):
    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: str = "pending"
    ai_suggestion: Optional[str] = None
    ai_public_refs: Optional[str] = None  # JSON array
    ai_restricted_hint: bool = False
    escalated_to_rd: bool = False
    rd_solution: Optional[str] = None
    rd_version: Optional[str] = None
    handling_record: Optional[str] = None  # JSON array
    created_by: str = "cs"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class HandlingRecord(BaseModel):
    notes: str


class EscalationResolve(BaseModel):
    solution: str
    version: Optional[str] = None


# --- Core AI Models ---

class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class AIQuery(BaseModel):
    query_text: str
    ticket_id: Optional[int] = None
    conversation_id: Optional[str] = None
    history: list[ChatMessage] = []


class Citation(BaseModel):
    doc_title: str
    doc_version: str
    section: str = ""
    snippet: str = ""


class AIResponse(BaseModel):
    log_id: str
    ticket_id: Optional[int] = None
    query_text: str
    answer_text: str
    citations: list[Citation] = []
    confidence_score: float
    confidence_label: ConfidenceLabel
    is_blocked: bool = False
    block_reason: Optional[str] = None
    escalation_required: bool = False
    d2_match_found: bool = False
    d2_hint: Optional[str] = None


# --- Request / Response Wrappers ---

class QueryResponse(BaseModel):
    success: bool
    data: Optional[AIResponse] = None
    error: Optional[str] = None


class SystemMetrics(BaseModel):
    total_tickets: int = 0
    escalated_count: int = 0
    escalation_rate: float = 0
    green_rate: float = 0
    yellow_rate: float = 0
    red_rate: float = 0
    d1_doc_count: int = 0
    d2_doc_count: int = 0


# --- WebSocket Messaging ---

class WSPacket(BaseModel):
    type: str
    payload: dict = {}


class CustomerTokenRequest(BaseModel):
    customer_name: str = "游客"


class CustomerTokenResponse(BaseModel):
    token: str
    customer_id: str


class SatisfactionSubmit(BaseModel):
    resolved: str  # "yes" | "no" | "feedback"
    feedback_text: str = ""


class MessageOut(BaseModel):
    id: int
    ticket_id: int
    sender_type: str
    sender_name: str
    content: str
    created_at: str


class EndServiceRequest(BaseModel):
    pass
