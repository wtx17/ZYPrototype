"""智云科技 AI 知识库系统 — FastAPI 主应用 (DFD v2 refactor)

DFD process mapping:
  POST /api/query                    → P1  AI处理
  POST /api/knowledge/rd             → P2  沉淀知识
  POST /api/knowledge/release-notes  → P3  发布Release notes
  POST /api/tickets/{id}/escalate    → P4  升级工单
  POST /api/escalations/{id}/resolve → P5  反馈升级工单
  POST /api/knowledge/submit         → P6  脱敏、审查 (提交)
  POST /api/knowledge/review/{id}    → P6  脱敏、审查 (审核)
  POST /api/tickets/{id}/handling    → P7  记录工单处理情况
  GET  /api/metrics                  → P8  汇总
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime
from urllib.parse import parse_qs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import SQLITE_PATH, CHROMA_PERSIST_DIR
from models import (
    TicketCreate,
    TicketStatus,
    AIQuery,
    AIResponse,
    LoginRequest,
    KnowledgeSubmit,
    KnowledgeReview,
    HandlingRecord,
    EscalationResolve,
    DesensitizeRequest,
    DesensitizeResponse,
    SystemMetrics,
    QueryResponse,
    CustomerTokenRequest,
    CustomerTokenResponse,
    SatisfactionSubmit,
    MessageOut,
    ChatMessage,
)
from database import (
    insert_ticket,
    get_ticket,
    list_tickets,
    update_ticket_status,
    update_ticket_ai_response,
    escalate_ticket as db_escalate_ticket,
    resolve_ticket_escalation,
    add_handling_record,
    insert_ai_knowledge,
    insert_rd_knowledge,
    list_ai_knowledge,
    list_approved_ai_knowledge,
    list_pending_ai_knowledge,
    update_ai_knowledge_review,
    get_ai_knowledge,
    list_rd_knowledge,
    get_metrics,
    insert_message,
    get_messages,
    get_last_message_id,
    insert_satisfaction_feedback,
    get_satisfaction_feedback,
    assign_ticket_cs,
    assign_ticket_rd,
    update_ticket_customer,
    end_ticket_service,
    list_active_tickets_for_agent,
    update_ticket_status as db_update_ticket_status,
)
from agent import query_ai
from desensitizer import desensitize
from knowledge_store import add_to_ai_knowledge as chroma_add_ai, add_to_rd_knowledge as chroma_add_rd
from auth import create_session, destroy_session, get_current_session, require_role, get_session
from ws_manager import clients as ws_clients

app = FastAPI(title="智云科技 AI 知识库系统", version="0.3.0")

# In-memory customer token store
_customer_tokens: dict[str, str] = {}  # token -> customer_id

# --- Static files ---
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "智云科技 AI 知识库系统 API", "docs": "/docs"}


@app.get("/cs")
async def cs_page():
    return await _serve_index()


@app.get("/rd")
async def rd_page():
    return await _serve_index()


@app.get("/doc")
async def doc_page():
    return await _serve_index()


@app.get("/manager")
async def manager_page():
    return await _serve_index()


async def _serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Page not found"}, 404


@app.get("/customer")
async def customer_page():
    customer_path = os.path.join(os.path.dirname(__file__), "static", "customer.html")
    if os.path.exists(customer_path):
        return FileResponse(customer_path)
    return {"message": "Customer chat page not found"}, 404


# ==================== Auth ====================

@app.post("/api/auth/login")
async def login(data: LoginRequest, response: Response):
    if data.role not in ("cs", "rd", "doc", "manager"):
        raise HTTPException(status_code=400, detail="无效的角色")
    session_id = create_session(data.role, data.username)
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=86400)
    return {"success": True, "role": data.role, "username": data.username, "session_id": session_id}


@app.get("/api/auth/me")
async def me(request: Request):
    session = await get_current_session(request)
    if not session:
        return {"authenticated": False}
    return {"authenticated": True, "role": session["role"], "username": session["username"]}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id:
        destroy_session(session_id)
    response.delete_cookie("session_id")
    return {"success": True}


# ==================== P1: AI处理 ====================

@app.post("/api/query")
async def ai_query(query: AIQuery, request: Request):
    """CS submits a customer query through the AI pipeline.

    This is a standalone query function. It does NOT create or update tickets.
    CS can manually create tickets from query results if needed.
    """
    session = await require_role(request, ["cs", "rd", "doc", "manager"])
    role = session["role"]

    # Convert ChatMessage objects to dicts for agent
    history = [{"role": h.role, "content": h.content} for h in query.history] if query.history else []

    response: AIResponse = query_ai(
        query.query_text,
        ticket_id=query.ticket_id,
        role=role,
        history=history,
    )

    # If a ticket_id was provided, persist AI result to that ticket
    if query.ticket_id:
        ticket = get_ticket(query.ticket_id)
        if ticket:
            update_ticket_status(query.ticket_id, TicketStatus.AI_PROCESSING.value)
            public_refs = json.dumps([c.model_dump() for c in response.citations], ensure_ascii=False)
            update_ticket_ai_response(
                query.ticket_id, response.answer_text, public_refs, response.d2_match_found,
            )
            if response.escalation_required and not ticket.get("escalated_to_rd"):
                reason = response.d2_hint or "AI 建议升级"
                db_escalate_ticket(query.ticket_id, reason)
            update_ticket_status(query.ticket_id, TicketStatus.RESOLVED.value)

    return QueryResponse(success=True, data=response)


# ==================== P2: 沉淀知识 ====================

@app.post("/api/knowledge/rd")
async def submit_rd_knowledge(data: dict, request: Request):
    """R&D submits solution knowledge to D2 (Process 2)."""
    session = await require_role(request, ["rd"])

    entry = {
        "title": data["title"],
        "content": data["content"],
        "keywords": data.get("keywords", ""),
        "version": data.get("version", ""),
        "release_note": data.get("release_note"),
        "source_ticket_id": data.get("source_ticket_id"),
        "entry_type": data.get("entry_type", "solution"),
        "created_at": datetime.now().isoformat(),
    }
    db_id = insert_rd_knowledge(entry)

    # Also add to ChromaDB D2 collection (best-effort)
    chroma_msg = ""
    try:
        chroma_add_rd(
            title=data["title"], content=data["content"],
            entry_type=entry["entry_type"], version=entry["version"],
            keywords=entry["keywords"], source_ticket_id=entry["source_ticket_id"],
            release_note=entry["release_note"],
        )
    except Exception as e:
        chroma_msg = f" (向量存储同步失败: {e})"

    return {"success": True, "id": db_id, "message": "知识已沉淀至研发知识库 (D2)" + chroma_msg}


# ==================== P3: 发布Release Notes ====================

@app.post("/api/knowledge/release-notes")
async def publish_release_notes(data: dict, request: Request):
    """R&D publishes release notes to D2 (Process 3)."""
    session = await require_role(request, ["rd"])

    entry = {
        "title": data["title"],
        "content": data["content"],
        "keywords": data.get("keywords", ""),
        "version": data.get("version", ""),
        "release_note": data.get("release_note", ""),
        "source_ticket_id": data.get("source_ticket_id"),
        "entry_type": "release_note",
        "created_at": datetime.now().isoformat(),
    }
    db_id = insert_rd_knowledge(entry)

    chroma_msg = ""
    try:
        chroma_add_rd(
            title=data["title"], content=data["content"],
            entry_type="release_note", version=entry["version"],
            keywords=entry["keywords"], release_note=entry["release_note"],
        )
    except Exception as e:
        chroma_msg = f" (向量存储同步失败: {e})"

    return {"success": True, "id": db_id, "message": "Release note 已发布至研发知识库 (D2)" + chroma_msg}


# ==================== P4: 升级工单 ====================

@app.post("/api/tickets/{ticket_id}/escalate")
async def escalate_ticket(ticket_id: int, request: Request, data: dict = None):
    """CS escalates a ticket to R&D (Process 4)."""
    session = await require_role(request, ["cs"])
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    reason = (data or {}).get("reason", "客服主动升级")
    ok = db_escalate_ticket(ticket_id, reason)
    return {"success": ok, "message": "工单已升级至二线研发"}


# ==================== P5: 反馈升级工单 ====================

@app.post("/api/escalations/{ticket_id}/resolve")
async def resolve_escalation(ticket_id: int, data: EscalationResolve, request: Request):
    """R&D resolves an escalated ticket (Process 5)."""
    session = await require_role(request, ["rd"])
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    if not ticket.get("escalated_to_rd"):
        raise HTTPException(status_code=400, detail="该工单未被升级")
    ok = resolve_ticket_escalation(ticket_id, data.solution, data.version)
    return {"success": ok, "message": "升级工单已解决"}


# ==================== P6: 脱敏、审查 ====================

@app.post("/api/knowledge/submit")
async def submit_knowledge(data: KnowledgeSubmit, request: Request):
    """Doc team submits knowledge for review. Auto-desensitized (Process 6)."""
    session = await require_role(request, ["doc"])

    cleaned, changes = desensitize(data.content)

    entry = {
        "title": data.title,
        "content": cleaned,
        "category": data.category or "",
        "keywords": data.keywords or "",
        "review_status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    db_id = insert_ai_knowledge(entry)
    return {"success": True, "id": db_id, "desensitized_changes": changes,
            "message": "知识已提交，等待审核 (D1)"}


@app.post("/api/knowledge/review/{knowledge_id}")
async def review_knowledge(knowledge_id: int, data: KnowledgeReview, request: Request):
    """Doc team reviews pending knowledge. Approved → D1 ChromaDB (Process 6)."""
    session = await require_role(request, ["doc"])

    entry = get_ai_knowledge(knowledge_id)
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    ok = update_ai_knowledge_review(knowledge_id, data.review_status)
    if not ok:
        raise HTTPException(status_code=500, detail="审核更新失败")

    if data.review_status == "approved":
        try:
            chroma_add_ai(
                title=entry["title"], content=entry["content"],
                category=entry.get("category", ""), keywords=entry.get("keywords", ""),
            )
        except Exception as e:
            pass  # vector sync is best-effort; SQL already updated

    return {"success": True, "message": f"知识已{data.review_status}"}


@app.get("/api/knowledge/pending")
async def get_pending_knowledge(request: Request):
    """List pending-review D1 entries (Doc only)."""
    await require_role(request, ["doc"])
    items = list_pending_ai_knowledge()
    return {"success": True, "data": items}


@app.get("/api/knowledge/ai")
async def get_ai_knowledge_list(request: Request):
    """List approved D1 entries (all roles)."""
    session = await require_role(request, ["cs", "rd", "doc", "manager"])
    items = list_approved_ai_knowledge()
    return {"success": True, "data": items}


@app.get("/api/knowledge/rd")
async def get_rd_knowledge_list(request: Request):
    """List D2 entries (RD/Doc only)."""
    await require_role(request, ["rd", "doc"])
    items = list_rd_knowledge()
    return {"success": True, "data": items}


# ==================== P7: 记录工单处理情况 ====================

@app.get("/api/tickets")
async def get_tickets(request: Request):
    """List tickets with role-based filtering (Process 7)."""
    session = await require_role(request, ["cs", "rd", "manager"])

    if session["role"] == "rd":
        tickets = list_tickets(escalated_only=True)
    elif session["role"] == "cs":
        tickets = list_tickets(created_by="cs")
    else:
        tickets = list_tickets()

    return {"success": True, "data": tickets, "count": len(tickets)}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket_detail(ticket_id: int, request: Request):
    """Get ticket detail (Process 7)."""
    await require_role(request, ["cs", "rd", "manager"])
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    return {"success": True, "data": ticket}


@app.post("/api/tickets")
async def create_ticket(ticket: TicketCreate):
    """Create a new support ticket."""
    data = {
        "title": ticket.title,
        "description": ticket.description or "",
        "status": "pending",
        "created_by": ticket.created_by,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    tid = insert_ticket(data)
    return {"success": True, "ticket_id": tid}


@app.post("/api/tickets/{ticket_id}/handling")
async def record_handling(ticket_id: int, data: HandlingRecord, request: Request):
    """CS records handling notes (Process 7)."""
    session = await require_role(request, ["cs"])
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    ok = add_handling_record(ticket_id, data.notes)
    return {"success": ok, "message": "处理记录已保存"}


# ==================== P8: 汇总 ====================

@app.get("/api/metrics")
async def system_metrics(request: Request):
    """System metrics dashboard (Process 8)."""
    await require_role(request, ["manager"])
    data = get_metrics()
    return {"success": True, "data": SystemMetrics(**data)}


# ==================== Utility ====================

@app.post("/api/desensitize")
async def desensitize_text(req: DesensitizeRequest):
    """Test desensitization (Process 6 utility)."""
    cleaned, changes = desensitize(req.text)
    return DesensitizeResponse(original=req.text, desensitized=cleaned, changes=changes)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ==================== Customer Token ====================

@app.post("/api/customer/token")
async def generate_customer_token(data: CustomerTokenRequest = None):
    """Generate an anonymous customer token for WebSocket connection."""
    token = secrets.token_urlsafe(16)
    customer_id = f"customer_{token[:8]}"
    name = data.customer_name if data else "游客"
    _customer_tokens[token] = customer_id
    return CustomerTokenResponse(token=token, customer_id=customer_id)


# ==================== Messages ====================

@app.get("/api/tickets/{ticket_id}/messages")
async def get_ticket_messages(ticket_id: int, after: int = 0, request: Request = None):
    """Get messages for a ticket (used by agents and customers)."""
    msgs = get_messages(ticket_id, after_id=after, limit=100)
    return {
        "success": True,
        "data": [
            MessageOut(
                id=m["id"],
                ticket_id=m["ticket_id"],
                sender_type=m["sender_type"],
                sender_name=m["sender_name"] or "",
                content=m["content"],
                created_at=m["created_at"],
            ) for m in msgs
        ],
        "last_id": msgs[-1]["id"] if msgs else after,
    }


# ==================== Agent Message (REST fallback) ====================

@app.post("/api/tickets/{ticket_id}/send-message")
async def send_agent_message(ticket_id: int, data: dict, request: Request):
    """CS or RD sends a message via REST (WebSocket fallback)."""
    session = await require_role(request, ["cs", "rd"])
    content = data.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    # RD can only message escalated tickets
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    if session["role"] == "rd" and not ticket.get("escalated_to_rd"):
        raise HTTPException(status_code=403, detail="该工单未升级，无法回复")

    await ws_clients.handle_agent_message(ticket_id, content, session["role"], session["username"])
    return {"success": True}


# ==================== Service Lifecycle ====================

@app.post("/api/tickets/{ticket_id}/end-service")
async def end_service(ticket_id: int, request: Request):
    """CS or RD ends service. Triggers satisfaction survey on customer side."""
    session = await require_role(request, ["cs", "rd"])
    await ws_clients.handle_service_end(ticket_id)
    return {"success": True, "message": "服务已结束"}


@app.post("/api/tickets/{ticket_id}/satisfaction")
async def submit_satisfaction(ticket_id: int, data: SatisfactionSubmit):
    """Customer submits satisfaction feedback."""
    await ws_clients.handle_satisfaction(ticket_id, data.resolved, data.feedback_text)
    return {"success": True, "message": "感谢您的反馈"}


# ==================== Agent Session Lists ====================

@app.get("/api/cs/sessions")
async def get_cs_sessions(request: Request):
    """CS gets their active ticket/session list."""
    session = await require_role(request, ["cs"])
    tickets = list_active_tickets_for_agent(session["username"], "cs")
    return {"success": True, "data": tickets, "count": len(tickets)}


@app.get("/api/rd/sessions")
async def get_rd_sessions(request: Request):
    """RD gets escalated ticket/session list."""
    session = await require_role(request, ["rd"])
    tickets = list_active_tickets_for_agent(session["username"], "rd")
    return {"success": True, "data": tickets, "count": len(tickets)}


@app.get("/api/sessions/{ticket_id}")
async def get_session_detail(ticket_id: int, request: Request):
    """Get full session detail including messages."""
    session = await require_role(request, ["cs", "rd"])
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    msgs = get_messages(ticket_id)
    return {
        "success": True,
        "data": {
            "ticket": ticket,
            "messages": [
                MessageOut(
                    id=m["id"],
                    ticket_id=m["ticket_id"],
                    sender_type=m["sender_type"],
                    sender_name=m["sender_name"] or "",
                    content=m["content"],
                    created_at=m["created_at"],
                ) for m in msgs
            ],
        },
    }


# ==================== WebSocket ====================

@app.websocket("/ws/customer")
async def ws_customer(websocket: WebSocket, token: str = ""):
    """Customer WebSocket connection."""
    if not token or token not in _customer_tokens:
        await websocket.close(code=4001, reason="Invalid token")
        return

    customer_id = _customer_tokens[token]
    await websocket.accept()

    try:
        ticket_id = await ws_clients.register_customer(customer_id, websocket)
    except Exception as e:
        await websocket.close(code=4002, reason=str(e))
        return

    # Send welcome with ticket_id
    await websocket.send_json({
        "type": "connected",
        "payload": {"customer_id": customer_id, "ticket_id": ticket_id},
    })

    # Auto-greeting: check if CS is assigned
    cs_name = ws_clients.ticket_cs.get(ticket_id)
    if cs_name:
        greeting = f"客服 {cs_name} 为您服务，正在查询解决方案"
        insert_message(ticket_id, "system", "系统", greeting)
        await websocket.send_json({
            "type": "system_message",
            "payload": {"ticket_id": ticket_id, "content": greeting},
        })

        # Notify CS about new session
        ticket = get_ticket(ticket_id)
        await ws_clients.send_to_cs(ticket_id, {
            "type": "new_session",
            "payload": {
                "ticket_id": ticket_id,
                "title": ticket.get("title", "") if ticket else "",
                "customer_id": customer_id,
            },
        })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            if msg_type == "customer_message":
                content = payload.get("content", "")
                if content.strip():
                    await ws_clients.handle_customer_message(ticket_id, content, customer_id)

            elif msg_type == "satisfaction":
                resolved = payload.get("resolved", "")
                feedback_text = payload.get("feedback_text", "")
                await ws_clients.handle_satisfaction(ticket_id, resolved, feedback_text)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "payload": {}})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_clients.unregister_customer(customer_id)


@app.websocket("/ws/agent")
async def ws_agent(websocket: WebSocket, session_id: str = ""):
    """CS/RD agent WebSocket connection. Auth via session_id query param."""
    if not session_id:
        await websocket.close(code=4001, reason="Missing session_id")
        return

    sess = get_session(session_id)
    if not sess:
        await websocket.close(code=4001, reason="Invalid session")
        return

    role = sess["role"]
    username = sess["username"]

    if role not in ("cs", "rd"):
        await websocket.close(code=4003, reason="Unauthorized role")
        return

    await websocket.accept()

    try:
        if role == "cs":
            await ws_clients.register_cs(username, websocket)
        else:
            await ws_clients.register_rd(username, websocket)
    except Exception as e:
        await websocket.close(code=4002, reason=str(e))
        return

    await websocket.send_json({
        "type": "connected",
        "payload": {"role": role, "username": username},
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            if msg_type == "agent_message":
                ticket_id = payload.get("ticket_id")
                content = payload.get("content", "")
                if ticket_id and content.strip():
                    # RD can only message escalated tickets
                    ticket = get_ticket(ticket_id)
                    if role == "rd" and ticket and not ticket.get("escalated_to_rd"):
                        await websocket.send_json({"type": "error", "payload": {"message": "该工单未升级，无法回复"}})
                    else:
                        await ws_clients.handle_agent_message(ticket_id, content, role, username)

            elif msg_type == "ai_request":
                ticket_id = payload.get("ticket_id")
                if ticket_id:
                    ticket = get_ticket(ticket_id)
                    customer_msg = ""
                    if ticket:
                        msgs = get_messages(ticket_id)
                        for m in msgs:
                            if m["sender_type"] == "customer":
                                customer_msg = m["content"]
                                break
                        if not customer_msg:
                            customer_msg = ticket.get("description", "")

                    response: AIResponse = query_ai(
                        customer_msg or payload.get("query_text", ""),
                        ticket_id=ticket_id,
                        role=role,
                        history=[],
                    )
                    ai_payload = {
                        "ticket_id": ticket_id,
                        "answer_text": response.answer_text,
                        "confidence_score": response.confidence_score,
                        "confidence_label": response.confidence_label.value if hasattr(response.confidence_label, 'value') else response.confidence_label,
                        "citations": [c.model_dump() for c in response.citations],
                        "d2_match_found": response.d2_match_found,
                        "d2_hint": response.d2_hint,
                        "escalation_required": response.escalation_required,
                    }
                    await websocket.send_json({"type": "ai_response", "payload": ai_payload})

            elif msg_type == "escalate":
                ticket_id = payload.get("ticket_id")
                reason = payload.get("reason", "")
                if ticket_id:
                    await ws_clients.handle_escalate(ticket_id, reason)

            elif msg_type == "accept_escalation":
                ticket_id = payload.get("ticket_id")
                if ticket_id and role == "rd":
                    await ws_clients.handle_rd_accept(ticket_id, username)

            elif msg_type == "service_end":
                ticket_id = payload.get("ticket_id")
                if ticket_id:
                    await ws_clients.handle_service_end(ticket_id)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "payload": {}})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if role == "cs":
            await ws_clients.unregister_cs(username)
        else:
            await ws_clients.unregister_rd(username)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
