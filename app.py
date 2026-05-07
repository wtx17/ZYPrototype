"""智云科技 AI 知识库系统 — FastAPI 主应用

Matches DFD processes:
  POST /api/query           → P1 AI处理
  POST /api/query/{id}/feedback → P2 知识沉淀
  POST /api/knowledge/sync  → P3 发布 Release Notes
  POST /api/tickets/{id}/escalate → P4 工单升级
  POST /api/escalations/{id}/resolve → P5 反馈升级工单
  POST /api/desensitize     → P6 脱敏处理
  GET  /api/tickets         → P7 记录工单处理情况
  GET  /api/metrics         → P8 汇总系统指标
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

# App-level debug logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import SQLITE_PATH, CHROMA_PERSIST_DIR
from models import (
    Ticket,
    AIQuery,
    AIResponse,
    Escalation,
    Feedback,
    DesensitizeRequest,
    DesensitizeResponse,
    MetricsResponse,
    SystemMetrics,
    TicketStatus,
    AgentRole,
    QueryResponse,
)
from database import (
    insert_ticket,
    get_ticket,
    list_tickets,
    update_ticket_status,
    insert_ai_log,
    get_ai_logs_for_ticket,
    insert_escalation,
    resolve_escalation,
    insert_feedback,
    get_metrics,
)
from agent import query_ai
from desensitizer import desensitize
from knowledge_store import sync_from_gitlab

app = FastAPI(title="智云科技 AI 知识库系统", version="0.1.0")

# --- Static files ---
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "智云科技 AI 知识库系统 API", "docs": "/docs"}


# --- Ticket CRUD ---

@app.post("/api/tickets")
async def create_ticket(ticket: Ticket):
    """Create a new support ticket."""
    data = ticket.model_dump()
    insert_ticket(data)
    return {"success": True, "ticket_id": data["id"]}


@app.get("/api/tickets")
async def get_tickets():
    """List all tickets (Process 7: 记录工单处理情况)."""
    tickets = list_tickets()
    return {"success": True, "data": tickets, "count": len(tickets)}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket_detail(ticket_id: str):
    """Get a single ticket with its AI interaction history."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    logs = get_ai_logs_for_ticket(ticket_id)
    ticket["ai_logs"] = logs
    return {"success": True, "data": ticket}


# --- Core AI Query (Process 1: AI处理) ---

@app.post("/api/query")
async def ai_query(query: AIQuery):
    """Process a customer query through the AI pipeline (Process 1)."""
    ticket = get_ticket(query.ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    # Update ticket status
    update_ticket_status(query.ticket_id, TicketStatus.AI_PROCESSING.value)

    # Run RAG pipeline (LLM always invoked)
    response: AIResponse = query_ai(query.query_text, query.ticket_id)

    # Persist AI log
    log_data = {
        "id": response.log_id,
        "ticket_id": response.ticket_id,
        "query_text": response.query_text,
        "answer_text": response.answer_text,
        "citations": [c.model_dump() for c in response.citations],
        "confidence_score": response.confidence_score,
        "confidence_label": response.confidence_label.value,
        "is_blocked": 1 if response.is_blocked else 0,
        "block_reason": response.block_reason,
        "escalation_required": 1 if response.escalation_required else 0,
        "created_at": datetime.now().isoformat(),
    }
    insert_ai_log(log_data)

    # Always set to pending_review — agent decides whether to escalate
    update_ticket_status(query.ticket_id, TicketStatus.PENDING_REVIEW.value)

    return QueryResponse(success=True, data=response)


# --- Feedback (Process 2: 知识沉淀) ---

@app.post("/api/query/{log_id}/feedback")
async def submit_feedback(log_id: str, feedback: Feedback):
    """Submit feedback on an AI answer for knowledge improvement (Process 2)."""
    feedback.id = str(uuid.uuid4())[:8]
    feedback.log_id = log_id
    feedback.created_at = datetime.now().isoformat()
    insert_feedback(feedback.model_dump())
    return {"success": True, "feedback_id": feedback.id}


# --- GitLab Sync (Process 3: 发布 Release Notes) ---

@app.post("/api/knowledge/sync")
async def sync_release_note(note: dict):
    """Sync a new release note from GitLab into the knowledge base (Process 3)."""
    doc_id = sync_from_gitlab(note)
    return {"success": True, "doc_id": doc_id, "message": "Release note 已同步至知识库"}


# --- Escalation (Process 4: 工单升级) ---

@app.post("/api/tickets/{ticket_id}/escalate")
async def escalate_ticket(ticket_id: str, reason: str = "客服主动升级"):
    """Escalate a ticket to L2 R&D (Process 4)."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    esc = {
        "id": str(uuid.uuid4())[:8],
        "ticket_id": ticket_id,
        "log_id": None,
        "reason": reason,
        "from_role": AgentRole.L1_AGENT.value,
        "to_role": AgentRole.L2_ENGINEER.value,
        "created_at": datetime.now().isoformat(),
        "resolved": 0,
        "resolution_notes": None,
    }
    insert_escalation(esc)
    update_ticket_status(ticket_id, TicketStatus.ESCALATED.value)
    return {"success": True, "escalation_id": esc["id"]}


# --- Escalation Resolution (Process 5: 反馈升级工单) ---

@app.post("/api/escalations/{esc_id}/resolve")
async def resolve_escalation_endpoint(esc_id: str, resolution: dict):
    """Resolve an escalated ticket with solution notes (Process 5)."""
    notes = resolution.get("notes", "")
    ok = resolve_escalation(esc_id, notes)
    if not ok:
        raise HTTPException(status_code=404, detail="升级记录不存在")
    # Update the linked ticket
    # In a real system we'd look up the ticket_id from the escalation record
    return {"success": True, "message": "升级工单已解决"}


# --- Desensitization (Process 6: 脱敏处理) ---

@app.post("/api/desensitize")
async def desensitize_text(req: DesensitizeRequest):
    """Desensitize text by removing PII and credentials (Process 6)."""
    cleaned, changes = desensitize(req.text)
    return DesensitizeResponse(
        original=req.text,
        desensitized=cleaned,
        changes=changes,
    )


# --- Metrics (Process 7+8: 汇总系统指标) ---

@app.get("/api/metrics")
async def system_metrics():
    """Get system performance metrics dashboard (Process 8)."""
    data = get_metrics()
    return MetricsResponse(success=True, data=SystemMetrics(**data))


# --- Health check ---

@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
