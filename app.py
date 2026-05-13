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
    insert_ai_query_log,
    escalate_ticket as db_escalate_ticket,
    resolve_ticket_escalation,
    add_handling_record,
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
    insert_wiki_page,
    get_wiki_page,
    get_wiki_page_by_slug,
    update_wiki_page,
    delete_wiki_page,
    search_wiki_pages,
    list_pending_review_pages,
    submit_for_review,
    approve_page,
    reject_page,
    list_approved_d1_pages,
)
from agent import query_ai
from desensitizer import desensitize
from knowledge_store import add_to_ai_knowledge as chroma_add_ai, add_to_rd_knowledge as chroma_add_rd
from auth import create_session, destroy_session, get_current_session, require_role, get_session
from ws_manager import clients as ws_clients
from wiki import build_wiki_tree

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
    from auth import get_session
    sess = get_session(session_id)
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=86400)
    return {
        "success": True, "role": data.role,
        "username": data.username,
        "display_name": sess.get("display_name", data.username) if sess else data.username,
        "user_id": sess.get("user_id") if sess else None,
        "session_id": session_id,
    }


@app.get("/api/auth/me")
async def me(request: Request):
    session = await get_current_session(request)
    if not session:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "role": session["role"],
        "username": session["username"],
        "display_name": session.get("display_name", session["username"]),
        "user_id": session.get("user_id"),
    }


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

    # If a ticket_id was provided, persist AI result (status unchanged, escalation handled by frontend)
    if query.ticket_id:
        ticket = get_ticket(query.ticket_id)
        if ticket:
            public_refs = json.dumps([c.model_dump() for c in response.citations], ensure_ascii=False)
            insert_ai_query_log(
                query.ticket_id, query.query_text, response.answer_text,
                public_refs, response.confidence_score,
                response.confidence_label.value if hasattr(response.confidence_label, 'value') else str(response.confidence_label),
                response.d2_match_found,
            )

    return QueryResponse(success=True, data=response)


# ==================== P2: 沉淀知识 → wiki_pages (D2) ====================

@app.post("/api/knowledge/rd")
async def submit_rd_knowledge(data: dict, request: Request):
    """R&D submits solution knowledge to D2 (Process 2)."""
    session = await require_role(request, ["rd"])

    page_data = {
        "title": data["title"],
        "content": data["content"],
        "knowledge_type": "d2",
        "status": "draft",
        "owner": session["username"],
        "keywords": data.get("keywords", ""),
        "version": data.get("version", ""),
        "release_note": data.get("release_note"),
        "source_ticket_id": data.get("source_ticket_id"),
        "entry_type": data.get("entry_type", "solution"),
    }
    db_id = insert_wiki_page(page_data)

    # Also add to ChromaDB D2 collection (best-effort)
    chroma_msg = ""
    try:
        chroma_add_rd(
            title=data["title"], content=data["content"],
            entry_type=page_data["entry_type"], version=page_data["version"],
            keywords=page_data["keywords"], source_ticket_id=page_data["source_ticket_id"],
            release_note=page_data["release_note"], wiki_page_id=db_id,
        )
    except Exception as e:
        chroma_msg = f" (向量存储同步失败: {e})"

    return {"success": True, "id": db_id, "message": "知识已沉淀至研发知识库 (D2)" + chroma_msg}


# ==================== P3: 发布Release Notes → wiki_pages (D2) ====================

@app.post("/api/knowledge/release-notes")
async def publish_release_notes(data: dict, request: Request):
    """R&D publishes release notes to D2 (Process 3)."""
    session = await require_role(request, ["rd"])

    page_data = {
        "title": data["title"],
        "content": data["content"],
        "knowledge_type": "d2",
        "status": "draft",
        "owner": session["username"],
        "keywords": data.get("keywords", ""),
        "version": data.get("version", ""),
        "release_note": data.get("release_note", ""),
        "source_ticket_id": data.get("source_ticket_id"),
        "entry_type": "release_note",
    }
    db_id = insert_wiki_page(page_data)

    chroma_msg = ""
    try:
        chroma_add_rd(
            title=data["title"], content=data["content"],
            entry_type="release_note", version=page_data["version"],
            keywords=page_data["keywords"], release_note=page_data["release_note"],
            wiki_page_id=db_id,
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
    from database import get_conn as _gc
    esc = _gc().execute(
        "SELECT 1 FROM escalations WHERE ticket_id = ? AND resolved_at IS NULL",
        (ticket_id,)
    ).fetchone()
    if not esc:
        raise HTTPException(status_code=400, detail="该工单未被升级")
    ok = resolve_ticket_escalation(ticket_id, data.solution, data.version)
    return {"success": ok, "message": "升级工单已解决"}


# ==================== P6: 脱敏、审查 → wiki_pages ====================

@app.post("/api/knowledge/submit")
async def submit_knowledge(data: KnowledgeSubmit, request: Request):
    """Doc team submits knowledge for review. Auto-desensitized (Process 6)."""
    session = await require_role(request, ["doc"])

    cleaned, changes = desensitize(data.content)

    page_data = {
        "title": data.title,
        "content": cleaned,
        "category": data.category or "",
        "keywords": data.keywords or "",
        "status": "pending_review",
        "knowledge_type": "d1",
        "owner": session["username"],
    }
    db_id = submit_for_review(page_data)
    return {"success": True, "id": db_id, "desensitized_changes": changes,
            "message": "知识已提交，等待审核 (D1)"}


@app.post("/api/knowledge/review/{page_id}")
async def review_knowledge(page_id: int, data: KnowledgeReview, request: Request):
    """Doc team reviews pending knowledge. Approved → D1 ChromaDB (Process 6)."""
    session = await require_role(request, ["doc"])

    page = get_wiki_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    if data.review_status == "approved":
        approve_page(page_id)
        # Sync to ChromaDB D1 (best-effort)
        try:
            chroma_add_ai(
                title=page["title"], content=page["content"],
                category=page.get("category", ""), keywords=page.get("keywords", ""),
                wiki_page_id=page_id,
            )
        except Exception:
            pass
    elif data.review_status == "rejected":
        reject_page(page_id)
    else:
        raise HTTPException(status_code=400, detail="无效的审核状态")

    return {"success": True, "message": f"知识已{data.review_status}"}


@app.get("/api/knowledge/pending")
async def get_pending_knowledge(request: Request):
    """List pending-review entries (Doc only)."""
    await require_role(request, ["doc"])
    items = list_pending_review_pages()
    return {"success": True, "data": items}


@app.get("/api/knowledge/ai")
async def get_ai_knowledge_list(request: Request):
    """List approved D1 entries (all roles)."""
    await require_role(request, ["cs", "rd", "doc", "manager"])
    items = list_approved_d1_pages()
    return {"success": True, "data": items}


@app.get("/api/knowledge/rd")
async def get_rd_knowledge_list(request: Request):
    """List D2 entries (RD/Doc only)."""
    await require_role(request, ["rd", "doc"])
    from database import list_wiki_pages as _list_wp
    items = _list_wp(knowledge_type="d2")
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ==================== Wiki ====================

@app.get("/api/wiki/tree")
async def get_wiki_tree(request: Request):
    """Get wiki document tree. Doc sees drafts; RD/Doc see D2 section."""
    session = await require_role(request, ["cs", "rd", "doc", "manager"])
    role = session["role"]
    include_d2 = role in ("rd", "doc")
    is_doc = role == "doc"
    tree = build_wiki_tree(include_d2=include_d2, is_doc=is_doc)
    return {"success": True, "data": tree}


@app.get("/api/wiki/search")
async def search_wiki(q: str, request: Request):
    """Search wiki pages. CS/Manager see D1 only, RD/Doc see D1+D2."""
    session = await require_role(request, ["cs", "rd", "doc", "manager"])
    if not q.strip():
        return {"success": True, "data": []}
    query = q.strip()
    # CS/Manager: D1 only; RD/Doc: both D1 and D2
    kt = None if session["role"] in ("rd", "doc") else "d1"
    results = search_wiki_pages(query, knowledge_type=kt)
    for r in results:
        r["source"] = r.get("knowledge_type", "d1")
    return {"success": True, "data": results[:20]}


@app.get("/api/wiki/{slug}")
async def get_wiki_page_by_slug_route(slug: str, request: Request):
    """Get a wiki page by slug. D2 pages restricted to RD/Doc."""
    session = await require_role(request, ["cs", "rd", "doc", "manager"])

    page = get_wiki_page_by_slug(slug)
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    # D2 pages: only RD/Doc can view
    if page.get("knowledge_type") == "d2" and session["role"] not in ("rd", "doc"):
        raise HTTPException(status_code=403, detail="无权访问研发知识库")

    page["source"] = page.get("knowledge_type", "d1")
    return {"success": True, "data": page}


@app.post("/api/wiki")
async def create_wiki_page_route(data: dict, request: Request):
    """Create a new wiki page (doc, rd)."""
    await require_role(request, ["doc", "rd"])
    title = (data.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    page_data = {
        "title": title,
        "content": data.get("content", ""),
        "parent_id": data.get("parent_id"),
        "owner": data.get("owner", "doc"),
        "status": data.get("status", "draft"),
        "knowledge_type": data.get("knowledge_type", "d1"),
        "version": data.get("version", ""),
        "entry_type": data.get("entry_type", ""),
        "release_note": data.get("release_note", ""),
        "keywords": data.get("keywords", ""),
    }
    page_id = insert_wiki_page(page_data)
    page = get_wiki_page(page_id)
    return {"success": True, "id": page_id, "slug": page["slug"] if page else ""}


@app.put("/api/wiki/{page_id}")
async def update_wiki_page_route(page_id: int, data: dict, request: Request):
    """Update a wiki page (doc, rd). Pages under review are read-only."""
    await require_role(request, ["doc", "rd"])

    page = get_wiki_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    # Block edits on pages under review (unless changing status)
    is_status_change = set(data.keys()) == {"status"}
    if page.get("status") == "pending_review" and not is_status_change:
        raise HTTPException(status_code=423, detail="审核中的页面无法编辑，请先通过或拒绝审核")

    # Editing an approved page → force back to draft for re-review
    if page.get("status") == "approved" and not is_status_change:
        data["status"] = "draft"

    update_data = {}
    for field in ("title", "content", "parent_id", "status", "category", "keywords",
                   "version", "entry_type", "release_note", "source_ticket_id",
                   "knowledge_type"):
        if field in data:
            val = data[field]
            if field in ("title", "category", "keywords", "version", "entry_type",
                         "release_note") and isinstance(val, str):
                val = val.strip()
            update_data[field] = val
    if not update_data:
        raise HTTPException(status_code=400, detail="无更新字段")
    ok = update_wiki_page(page_id, update_data)
    if not ok:
        raise HTTPException(status_code=404, detail="页面不存在")
    return {"success": True}


@app.delete("/api/wiki/{page_id}")
async def delete_wiki_page_route(page_id: int, request: Request):
    """Delete a wiki page (doc, rd). Children become root pages."""
    await require_role(request, ["doc", "rd"])
    ok = delete_wiki_page(page_id)
    if not ok:
        raise HTTPException(status_code=404, detail="页面不存在")
    return {"success": True}


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

    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    # CS must have accepted the ticket
    if session["role"] == "cs" and not ticket.get("assigned_cs_id"):
        raise HTTPException(status_code=403, detail="请先处理工单")
    # RD must have accepted the escalated ticket
    if session["role"] == "rd" and not ticket.get("assigned_rd_id"):
        raise HTTPException(status_code=403, detail="请先接管工单")

    await ws_clients.handle_agent_message(ticket_id, content, session["role"], session["username"])
    return {"success": True}


# ==================== Service Lifecycle ====================

@app.post("/api/tickets/{ticket_id}/accept")
async def accept_ticket(ticket_id: int, request: Request):
    """RD accepts an escalated ticket."""
    session = await require_role(request, ["rd"])
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    from database import get_conn as _gc
    esc = _gc().execute(
        "SELECT 1 FROM escalations WHERE ticket_id = ? AND resolved_at IS NULL",
        (ticket_id,)
    ).fetchone()
    if not esc:
        raise HTTPException(status_code=400, detail="该工单未被升级")
    await ws_clients.handle_rd_accept(ticket_id, session["username"])
    return {"success": True, "message": "已接管工单"}


@app.post("/api/tickets/{ticket_id}/handle")
async def handle_ticket(ticket_id: int, request: Request):
    """CS accepts a ticket for handling."""
    session = await require_role(request, ["cs"])
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    await ws_clients.handle_cs_accept(ticket_id, session["username"])
    return {"success": True, "message": "已开始处理工单"}


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

    await ws_clients.register_customer(customer_id, websocket)

    # Find active ticket for this customer via DB
    active_ticket_id = None
    history = []
    from database import get_conn as _gc, get_or_create_user as _gcu
    user = _gcu(customer_id, customer_id, "customer")
    rows = _gc().execute(
        "SELECT id FROM tickets WHERE customer_user_id = ? "
        "AND status != 'closed' AND service_ended = 0 "
        "ORDER BY created_at DESC LIMIT 1",
        (user["id"],)
    ).fetchall()
    if rows:
        active_ticket_id = rows[0]["id"]
        ws_clients.ticket_map[active_ticket_id] = customer_id
        msgs = get_messages(active_ticket_id)
        history = [
            MessageOut(
                id=m["id"], ticket_id=m["ticket_id"],
                sender_type=m["sender_type"], sender_name=m["sender_name"] or "",
                content=m["content"], created_at=m["created_at"],
            ) for m in msgs
        ]

    await websocket.send_json({
        "type": "connected",
        "payload": {
            "customer_id": customer_id,
            "ticket_id": active_ticket_id,
            "history": [m.model_dump() for m in history],
        },
    })

    try:
        ticket_id = None
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            if msg_type == "customer_message":
                content = payload.get("content", "")
                if content.strip():
                    ticket_id = await ws_clients.handle_customer_message(
                        ticket_id or payload.get("ticket_id") or 0,
                        content, customer_id,
                    )
                    # Send ticket_id back on first message
                    if ticket_id:
                        await websocket.send_json({
                            "type": "ticket_assigned",
                            "payload": {"ticket_id": ticket_id},
                        })

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
        user_id = sess.get("user_id", 0)
        if role == "cs":
            await ws_clients.register_cs(username, websocket, user_id)
        else:
            await ws_clients.register_rd(username, websocket, user_id)
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
                    ticket = get_ticket(ticket_id)
                    if role == "cs" and ticket and not ticket.get("assigned_cs_id"):
                        await websocket.send_json({"type": "error", "payload": {"message": "请先处理工单"}})
                    elif role == "rd" and ticket and not ticket.get("assigned_rd_id"):
                        await websocket.send_json({"type": "error", "payload": {"message": "请先接管工单"}})
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
                    # Log AI query
                    citations_json = json.dumps([c.model_dump() for c in response.citations], ensure_ascii=False)
                    insert_ai_query_log(
                        ticket_id, customer_msg or "", response.answer_text,
                        citations_json, response.confidence_score,
                        response.confidence_label.value if hasattr(response.confidence_label, 'value') else str(response.confidence_label),
                        response.d2_match_found,
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
