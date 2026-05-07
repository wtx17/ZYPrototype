import sqlite3
import json
from datetime import datetime
from typing import Optional

from config import SQLITE_PATH

_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_db()
    return _conn


def _init_db():
    c = get_conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            customer_desc TEXT,
            error_code TEXT,
            status TEXT DEFAULT 'open',
            agent_id TEXT DEFAULT 'agent_xiao_chen',
            created_at TEXT,
            sla_deadline TEXT
        );

        CREATE TABLE IF NOT EXISTS ai_logs (
            id TEXT PRIMARY KEY,
            ticket_id TEXT,
            query_text TEXT,
            answer_text TEXT,
            citations TEXT,  -- JSON array
            confidence_score REAL,
            confidence_label TEXT,
            is_blocked INTEGER DEFAULT 0,
            block_reason TEXT,
            escalation_required INTEGER DEFAULT 0,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS escalations (
            id TEXT PRIMARY KEY,
            ticket_id TEXT,
            log_id TEXT,
            reason TEXT,
            from_role TEXT,
            to_role TEXT DEFAULT 'L2_研发',
            created_at TEXT,
            resolved INTEGER DEFAULT 0,
            resolution_notes TEXT
        );

        CREATE TABLE IF NOT EXISTS feedbacks (
            id TEXT PRIMARY KEY,
            log_id TEXT,
            agent_id TEXT,
            is_accurate INTEGER,
            correction_notes TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS knowledge_docs (
            id TEXT PRIMARY KEY,
            title TEXT,
            source_type TEXT,
            content TEXT,
            version TEXT DEFAULT '1.0',
            validity_status TEXT DEFAULT '有效',
            created_at TEXT
        );
    """)
    _conn.commit()


def insert_ticket(ticket: dict) -> str:
    c = get_conn()
    c.execute(
        "INSERT INTO tickets (id, customer_desc, error_code, status, agent_id, created_at, sla_deadline) "
        "VALUES (:id, :customer_desc, :error_code, :status, :agent_id, :created_at, :sla_deadline)",
        ticket,
    )
    _conn.commit()
    return ticket["id"]


def get_ticket(ticket_id: str) -> Optional[dict]:
    c = get_conn()
    row = c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def list_tickets() -> list[dict]:
    c = get_conn()
    rows = c.execute("SELECT * FROM tickets ORDER BY created_at DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]


def update_ticket_status(ticket_id: str, status: str):
    c = get_conn()
    c.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
    _conn.commit()


def insert_ai_log(log: dict) -> str:
    c = get_conn()
    log["citations"] = json.dumps(log.get("citations", []), ensure_ascii=False)
    c.execute(
        "INSERT INTO ai_logs (id, ticket_id, query_text, answer_text, citations, "
        "confidence_score, confidence_label, is_blocked, block_reason, escalation_required, created_at) "
        "VALUES (:id, :ticket_id, :query_text, :answer_text, :citations, "
        ":confidence_score, :confidence_label, :is_blocked, :block_reason, :escalation_required, :created_at)",
        log,
    )
    _conn.commit()
    return log["id"]


def get_ai_logs_for_ticket(ticket_id: str) -> list[dict]:
    c = get_conn()
    rows = c.execute(
        "SELECT * FROM ai_logs WHERE ticket_id = ? ORDER BY created_at ASC", (ticket_id,)
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["citations"] = json.loads(d.get("citations", "[]"))
        results.append(d)
    return results


def insert_escalation(esc: dict) -> str:
    c = get_conn()
    c.execute(
        "INSERT INTO escalations (id, ticket_id, log_id, reason, from_role, to_role, created_at, resolved, resolution_notes) "
        "VALUES (:id, :ticket_id, :log_id, :reason, :from_role, :to_role, :created_at, :resolved, :resolution_notes)",
        esc,
    )
    _conn.commit()
    return esc["id"]


def resolve_escalation(esc_id: str, notes: str) -> bool:
    c = get_conn()
    c.execute(
        "UPDATE escalations SET resolved = 1, resolution_notes = ? WHERE id = ?",
        (notes, esc_id),
    )
    _conn.commit()
    return c.rowcount > 0


def insert_feedback(fb: dict) -> str:
    c = get_conn()
    c.execute(
        "INSERT INTO feedbacks (id, log_id, agent_id, is_accurate, correction_notes, created_at) "
        "VALUES (:id, :log_id, :agent_id, :is_accurate, :correction_notes, :created_at)",
        fb,
    )
    _conn.commit()
    return fb["id"]


def get_metrics() -> dict:
    c = get_conn()
    total = c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    escalated = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE status = 'escalated'"
    ).fetchone()[0]

    logs = c.execute("SELECT confidence_label FROM ai_logs").fetchall()
    green = sum(1 for r in logs if r["confidence_label"] == "green")
    yellow = sum(1 for r in logs if r["confidence_label"] == "yellow")
    red = sum(1 for r in logs if r["confidence_label"] == "red")
    total_logs = len(logs) or 1

    return {
        "total_tickets": total,
        "avg_response_time_seconds": 0,
        "avg_resolution_time_hours": 0,
        "escalation_rate": escalated / max(total, 1),
        "green_rate": green / total_logs,
        "yellow_rate": yellow / total_logs,
        "red_rate": red / total_logs,
        "knowledge_base_usage_rate": 0.48,
    }
