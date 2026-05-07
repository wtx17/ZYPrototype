"""Database layer: SQLite CRUD for D1 (ai_knowledge), D2 (rd_knowledge), D3 (tickets)."""

import json
import sqlite3
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
        CREATE TABLE IF NOT EXISTS ai_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT,
            keywords TEXT,
            review_status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rd_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            keywords TEXT,
            version TEXT,
            release_note TEXT,
            source_ticket_id INTEGER,
            entry_type TEXT NOT NULL CHECK(entry_type IN ('solution', 'release_note')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            ai_suggestion TEXT,
            ai_public_refs TEXT,
            ai_restricted_hint INTEGER DEFAULT 0,
            escalated_to_rd INTEGER DEFAULT 0,
            rd_solution TEXT,
            rd_version TEXT,
            handling_record TEXT,
            created_by TEXT DEFAULT 'cs',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    _conn.commit()


# --- D1: AI Knowledge ---

def insert_ai_knowledge(data: dict) -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO ai_knowledge (title, content, category, keywords, review_status, created_at, updated_at) "
        "VALUES (:title, :content, :category, :keywords, :review_status, :created_at, :updated_at)",
        data,
    )
    _conn.commit()
    return cur.lastrowid


def list_ai_knowledge(status: Optional[str] = None) -> list[dict]:
    c = get_conn()
    if status:
        rows = c.execute(
            "SELECT * FROM ai_knowledge WHERE review_status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = c.execute("SELECT * FROM ai_knowledge ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def list_pending_ai_knowledge() -> list[dict]:
    return list_ai_knowledge("pending")


def list_approved_ai_knowledge() -> list[dict]:
    return list_ai_knowledge("approved")


def update_ai_knowledge_review(knowledge_id: int, status: str) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE ai_knowledge SET review_status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, knowledge_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def get_ai_knowledge(knowledge_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute("SELECT * FROM ai_knowledge WHERE id = ?", (knowledge_id,)).fetchone()
    return dict(row) if row else None


# --- D2: R&D Knowledge ---

def insert_rd_knowledge(data: dict) -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO rd_knowledge (title, content, keywords, version, release_note, "
        "source_ticket_id, entry_type, created_at) "
        "VALUES (:title, :content, :keywords, :version, :release_note, "
        ":source_ticket_id, :entry_type, :created_at)",
        data,
    )
    _conn.commit()
    return cur.lastrowid


def list_rd_knowledge(entry_type: Optional[str] = None) -> list[dict]:
    c = get_conn()
    if entry_type:
        rows = c.execute(
            "SELECT * FROM rd_knowledge WHERE entry_type = ? ORDER BY created_at DESC", (entry_type,)
        ).fetchall()
    else:
        rows = c.execute("SELECT * FROM rd_knowledge ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_rd_knowledge(knowledge_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute("SELECT * FROM rd_knowledge WHERE id = ?", (knowledge_id,)).fetchone()
    return dict(row) if row else None


# --- D3: Tickets ---

def insert_ticket(data: dict) -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO tickets (title, description, status, created_by, created_at, updated_at) "
        "VALUES (:title, :description, :status, :created_by, :created_at, :updated_at)",
        data,
    )
    _conn.commit()
    return cur.lastrowid


def get_ticket(ticket_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def list_tickets(created_by: Optional[str] = None, escalated_only: bool = False) -> list[dict]:
    c = get_conn()
    if escalated_only:
        rows = c.execute(
            "SELECT * FROM tickets WHERE escalated_to_rd = 1 AND status != 'closed' ORDER BY created_at DESC"
        ).fetchall()
    elif created_by:
        rows = c.execute(
            "SELECT * FROM tickets WHERE created_by = ? ORDER BY created_at DESC LIMIT 50",
            (created_by,),
        ).fetchall()
    else:
        rows = c.execute("SELECT * FROM tickets ORDER BY created_at DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]


def update_ticket_status(ticket_id: int, status: str):
    c = get_conn()
    c.execute(
        "UPDATE tickets SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, ticket_id),
    )
    _conn.commit()


def update_ticket_ai_response(ticket_id: int, suggestion: str, public_refs: str, restricted_hint: bool):
    c = get_conn()
    c.execute(
        "UPDATE tickets SET ai_suggestion = ?, ai_public_refs = ?, ai_restricted_hint = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (suggestion, public_refs, 1 if restricted_hint else 0, ticket_id),
    )
    _conn.commit()


def escalate_ticket(ticket_id: int, reason: str = "") -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET escalated_to_rd = 1, status = 'escalated', "
        "description = COALESCE(description, '') || ' | 升级原因: ' || ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (reason, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def resolve_ticket_escalation(ticket_id: int, solution: str, version: Optional[str] = None) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET rd_solution = ?, rd_version = ?, status = 'resolved', "
        "updated_at = datetime('now') WHERE id = ?",
        (solution, version, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def add_handling_record(ticket_id: int, notes: str) -> bool:
    c = get_conn()
    row = c.execute("SELECT handling_record FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not row:
        return False
    records = json.loads(row["handling_record"] or "[]")
    records.append({"notes": notes, "time": c.execute("SELECT datetime('now')").fetchone()[0]})
    c.execute(
        "UPDATE tickets SET handling_record = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(records, ensure_ascii=False), ticket_id),
    )
    _conn.commit()
    return True


def get_metrics() -> dict:
    c = get_conn()
    total = c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    escalated = c.execute("SELECT COUNT(*) FROM tickets WHERE escalated_to_rd = 1").fetchone()[0]
    d1_count = c.execute("SELECT COUNT(*) FROM ai_knowledge WHERE review_status = 'approved'").fetchone()[0]
    d2_count = c.execute("SELECT COUNT(*) FROM rd_knowledge").fetchone()[0]

    # Confidence distribution — we derive from tickets that have ai_suggestion
    logs = c.execute(
        "SELECT ai_suggestion, ai_restricted_hint FROM tickets WHERE ai_suggestion IS NOT NULL"
    ).fetchall()
    green = yellow = red = 0
    for row in logs:
        # Simple heuristic: red if restricted_hint, yellow if no refs, green otherwise
        if row["ai_restricted_hint"]:
            red += 1
        elif row["ai_suggestion"]:
            green += 1
        else:
            yellow += 1
    total_logs = len(logs) or 1

    return {
        "total_tickets": total,
        "escalated_count": escalated,
        "escalation_rate": escalated / max(total, 1),
        "green_rate": green / total_logs,
        "yellow_rate": yellow / total_logs,
        "red_rate": red / total_logs,
        "d1_doc_count": d1_count,
        "d2_doc_count": d2_count,
    }
