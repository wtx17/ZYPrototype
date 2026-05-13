"""Database layer: SQLite CRUD. Single wiki_pages table for all knowledge."""

import json
import re
import sqlite3
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

    # Run merge migration if old tables still exist
    old = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
        "('ai_knowledge', 'rd_knowledge')"
    ).fetchall()
    if old:
        _run_merge_migration(c)

    c.executescript("""
        CREATE TABLE IF NOT EXISTS wiki_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            parent_id INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'draft',
            knowledge_type TEXT DEFAULT 'd1',
            source TEXT DEFAULT 'manual',
            owner TEXT DEFAULT '',
            category TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            version TEXT DEFAULT '',
            entry_type TEXT DEFAULT '',
            release_note TEXT DEFAULT '',
            source_ticket_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            created_by TEXT DEFAULT 'cs',
            assigned_cs_id INTEGER REFERENCES users(id),
            assigned_rd_id INTEGER REFERENCES users(id),
            customer_user_id INTEGER REFERENCES users(id),
            service_ended INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'customer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(username, role)
        );

        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL CHECK(sender_type IN ('customer', 'cs', 'rd', 'system')),
            sender_name TEXT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS satisfaction_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            resolved TEXT,
            feedback_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ai_query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            query_text TEXT NOT NULL,
            answer_text TEXT NOT NULL,
            citations_json TEXT DEFAULT '[]',
            confidence_score REAL DEFAULT 0,
            confidence_label TEXT DEFAULT 'red',
            d2_match_found INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_ai_query_logs_ticket ON ai_query_logs(ticket_id);

        CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            escalated_by TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            solution TEXT,
            version TEXT,
            resolved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_escalations_ticket ON escalations(ticket_id);

        CREATE TABLE IF NOT EXISTS handling_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            user_id INTEGER REFERENCES users(id),
            notes TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_handling_records_ticket ON handling_records(ticket_id);
    """)
    _conn.commit()

    _migrate_tickets(c)


# ==================== Slug ====================

def _generate_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9_-]', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


# ==================== Merge Migration ====================

def _run_merge_migration(c):
    """One-time: merge ai_knowledge + rd_knowledge + old wiki_pages → new wiki_pages."""
    new_sql = """CREATE TABLE wiki_pages_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        parent_id INTEGER DEFAULT NULL,
        status TEXT DEFAULT 'draft',
        knowledge_type TEXT DEFAULT 'd1',
        source TEXT DEFAULT 'manual',
        owner TEXT DEFAULT '',
        category TEXT DEFAULT '',
        keywords TEXT DEFAULT '',
        version TEXT DEFAULT '',
        entry_type TEXT DEFAULT '',
        release_note TEXT DEFAULT '',
        source_ticket_id INTEGER DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
    c.execute(new_sql)

    def _safe(d, key, default=""):
        return d.get(key) if d else default

    # 1. Old wiki_pages → D1 approved
    has_wiki = c.execute("SELECT name FROM sqlite_master WHERE name='wiki_pages'").fetchone()
    if has_wiki:
        rows = c.execute("SELECT * FROM wiki_pages").fetchall()
        for r in rows:
            d = dict(r)
            c.execute(
                "INSERT INTO wiki_pages_new (id, slug, title, content, parent_id, owner, "
                "status, knowledge_type, source, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'approved', 'd1', 'manual', ?, ?)",
                (d["id"], d["slug"], d["title"], _safe(d, "content"),
                 _safe(d, "parent_id") or None, _safe(d, "owner"),
                 _safe(d, "created_at"), _safe(d, "updated_at"))
            )

    # 2. ai_knowledge migrated if not already in wiki_pages
    has_ai = c.execute("SELECT name FROM sqlite_master WHERE name='ai_knowledge'").fetchone()
    has_log = c.execute("SELECT name FROM sqlite_master WHERE name='wiki_import_log'").fetchone()
    if has_ai:
        # Approved, not yet imported
        if has_log:
            rows = c.execute(
                "SELECT * FROM ai_knowledge WHERE review_status = 'approved' "
                "AND id NOT IN (SELECT knowledge_id FROM wiki_import_log)"
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM ai_knowledge WHERE review_status = 'approved'"
            ).fetchall()
        for r in rows:
            d = dict(r)
            slug = _generate_slug(d["title"]) or f"page-ak-{d['id']}"
            c.execute(
                "INSERT INTO wiki_pages_new (slug, title, content, owner, "
                "status, knowledge_type, source, category, keywords, created_at, updated_at) "
                "VALUES (?, ?, ?, 'doc', 'approved', 'd1', 'manual', ?, ?, ?, ?)",
                (slug, d["title"], _safe(d, "content"),
                 _safe(d, "category"), _safe(d, "keywords"),
                 _safe(d, "created_at"), _safe(d, "updated_at"))
            )
        # Pending entries
        pending_rows = c.execute(
            "SELECT * FROM ai_knowledge WHERE review_status != 'approved'"
        ).fetchall()
        for r in pending_rows:
            d = dict(r)
            slug = _generate_slug(d["title"]) or f"page-ak-{d['id']}"
            new_status = "pending_review" if d.get("review_status") == "pending" else "draft"
            c.execute(
                "INSERT INTO wiki_pages_new (slug, title, content, owner, "
                "status, knowledge_type, source, category, keywords, created_at, updated_at) "
                "VALUES (?, ?, ?, 'doc', ?, 'd1', 'manual', ?, ?, ?, ?)",
                (slug, d["title"], _safe(d, "content"), new_status,
                 _safe(d, "category"), _safe(d, "keywords"),
                 _safe(d, "created_at"), _safe(d, "updated_at"))
            )

    # 3. rd_knowledge → D2 draft
    has_rd = c.execute("SELECT name FROM sqlite_master WHERE name='rd_knowledge'").fetchone()
    if has_rd:
        rows = c.execute("SELECT * FROM rd_knowledge").fetchall()
        for r in rows:
            d = dict(r)
            slug = _generate_slug(d["title"]) or f"rd-{d['id']}"
            c.execute(
                "INSERT INTO wiki_pages_new (slug, title, content, owner, "
                "status, knowledge_type, source, version, entry_type, release_note, "
                "source_ticket_id, keywords, created_at) "
                "VALUES (?, ?, ?, 'rd', 'draft', 'd2', 'manual', ?, ?, ?, ?, ?, ?)",
                (slug, d["title"], _safe(d, "content"),
                 _safe(d, "version"), _safe(d, "entry_type"),
                 _safe(d, "release_note"), d.get("source_ticket_id"),
                 _safe(d, "keywords"), _safe(d, "created_at"))
            )

    # 4. Drop old tables
    for tbl in ["ai_knowledge", "rd_knowledge", "wiki_pages", "wiki_import_log"]:
        c.execute(f"DROP TABLE IF EXISTS {tbl}")

    # 5. Rename
    c.execute("ALTER TABLE wiki_pages_new RENAME TO wiki_pages")
    _conn.commit()


# ==================== Tickets Migration ====================

def _migrate_tickets(c):
    _migrate_users(c)
    count = c.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0]
    if count == 0:
        _seed_wiki_pages(c)


def _migrate_users(c):
    """Seed default users (idempotent)."""
    defaults = [
        ("小陈", "小陈", "cs"),
        ("王工", "王工", "rd"),
        ("李婷", "李婷", "doc"),
        ("林总", "林总", "manager"),
    ]
    for username, display_name, role in defaults:
        c.execute(
            "INSERT OR IGNORE INTO users (username, display_name, role) VALUES (?, ?, ?)",
            (username, display_name, role)
        )
    _conn.commit()


def _seed_wiki_pages(c):
    """Seed wiki_pages with default knowledge entries on fresh install."""
    from seed_data import AI_KNOWLEDGE_ENTRIES, RD_KNOWLEDGE_ENTRIES
    from datetime import datetime as dt
    now = dt.now().isoformat()

    for entry in AI_KNOWLEDGE_ENTRIES:
        slug = _generate_slug(entry["title"]) or f"page-seed-{entry.get('id', 'x')}"
        if c.execute("SELECT 1 FROM wiki_pages WHERE slug = ?", (slug,)).fetchone():
            slug = f"{slug}-{_next_id(c, 'wiki_pages')}"
        c.execute(
            "INSERT INTO wiki_pages (slug, title, content, owner, status, knowledge_type, "
            "source, category, keywords, created_at, updated_at) "
            "VALUES (?, ?, ?, 'doc', 'approved', 'd1', 'manual', ?, ?, ?, ?)",
            (slug, entry["title"], entry["content"],
             entry.get("category", ""), entry.get("keywords", ""), now, now)
        )

    for entry in RD_KNOWLEDGE_ENTRIES:
        slug = _generate_slug(entry["title"]) or f"rd-seed-{entry.get('id', 'x')}"
        if c.execute("SELECT 1 FROM wiki_pages WHERE slug = ?", (slug,)).fetchone():
            slug = f"{slug}-{_next_id(c, 'wiki_pages')}"
        c.execute(
            "INSERT INTO wiki_pages (slug, title, content, owner, status, knowledge_type, "
            "source, version, entry_type, keywords, release_note, created_at) "
            "VALUES (?, ?, ?, 'rd', 'draft', 'd2', 'manual', ?, ?, ?, ?, ?)",
            (slug, entry["title"], entry["content"],
             entry.get("version", ""), entry.get("entry_type", ""),
             entry.get("keywords", ""), entry.get("release_note"), now)
        )
    _conn.commit()


# ==================== Wiki Pages CRUD ====================

def list_wiki_pages(status: Optional[str] = None,
                    knowledge_type: Optional[str] = None) -> list[dict]:
    c = get_conn()
    conditions = []
    params = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if knowledge_type:
        conditions.append("knowledge_type = ?")
        params.append(knowledge_type)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = c.execute(
        f"SELECT id, slug, title, parent_id, owner, status, knowledge_type, source, "
        f"updated_at, created_at FROM wiki_pages{where} ORDER BY created_at ASC",
        params
    ).fetchall()
    return [dict(r) for r in rows]


def get_wiki_page(page_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute("SELECT * FROM wiki_pages WHERE id = ?", (page_id,)).fetchone()
    return dict(row) if row else None


def get_wiki_page_by_slug(slug: str) -> Optional[dict]:
    c = get_conn()
    row = c.execute("SELECT * FROM wiki_pages WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def insert_wiki_page(data: dict) -> int:
    c = get_conn()
    base_slug = _generate_slug(data["title"])
    slug = base_slug if base_slug else f"page-{_next_id(c, 'wiki_pages')}"

    if c.execute("SELECT 1 FROM wiki_pages WHERE slug = ?", (slug,)).fetchone():
        slug = f"{slug}-{_next_id(c, 'wiki_pages')}"

    fields = ["slug", "title", "content"]
    placeholders = [":slug", ":title", ":content"]
    for key in ("parent_id", "status", "knowledge_type", "source", "owner",
                 "category", "keywords", "version", "entry_type", "release_note",
                 "source_ticket_id"):
        if key in data:
            fields.append(key)
            placeholders.append(f":{key}")

    defaults = {
        "status": "draft", "knowledge_type": "d1", "source": "manual", "owner": "",
        "content": "", "category": "", "keywords": "", "version": "",
        "entry_type": "", "release_note": "",
    }
    values = {**defaults, **data, "slug": slug}
    # parent_id / source_ticket_id: treat empty string as None
    for int_field in ("parent_id", "source_ticket_id"):
        if int_field in values and values[int_field] in (None, ""):
            values[int_field] = None

    cur = c.execute(
        f"INSERT INTO wiki_pages ({', '.join(fields)}) VALUES ({', '.join(placeholders)})",
        values,
    )
    page_id = cur.lastrowid
    _conn.commit()
    return page_id


def update_wiki_page(page_id: int, data: dict) -> bool:
    c = get_conn()
    fields = []
    values = []
    updatable = ("title", "content", "parent_id", "status", "knowledge_type",
                 "owner", "category", "keywords", "version", "entry_type",
                 "release_note", "source_ticket_id")
    for key in updatable:
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])

    if "title" in data:
        base_slug = _generate_slug(data["title"])
        slug = base_slug if base_slug else f"page-{page_id}"
        if c.execute("SELECT 1 FROM wiki_pages WHERE slug = ? AND id != ?",
                     (slug, page_id)).fetchone():
            slug = f"{slug}-{page_id}"
        fields.append("slug = ?")
        values.append(slug)

    if not fields:
        return False
    fields.append("updated_at = datetime('now')")
    values.append(page_id)
    cur = c.execute(f"UPDATE wiki_pages SET {', '.join(fields)} WHERE id = ?", values)
    _conn.commit()
    return cur.rowcount > 0


def delete_wiki_page(page_id: int) -> bool:
    c = get_conn()
    c.execute("UPDATE wiki_pages SET parent_id = NULL WHERE parent_id = ?", (page_id,))
    cur = c.execute("DELETE FROM wiki_pages WHERE id = ?", (page_id,))
    _conn.commit()
    return cur.rowcount > 0


def search_wiki_pages(query: str, knowledge_type: Optional[str] = None) -> list[dict]:
    c = get_conn()
    like = f"%{query}%"
    if knowledge_type:
        rows = c.execute(
            "SELECT id, slug, title, updated_at, knowledge_type FROM wiki_pages "
            "WHERE (title LIKE ? OR content LIKE ?) AND knowledge_type = ? "
            "ORDER BY updated_at DESC LIMIT 20",
            (like, like, knowledge_type)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT id, slug, title, updated_at, knowledge_type FROM wiki_pages "
            "WHERE title LIKE ? OR content LIKE ? "
            "ORDER BY updated_at DESC LIMIT 20",
            (like, like)
        ).fetchall()
    return [dict(r) for r in rows]


# ==================== Review Workflow (replaces ai_knowledge CRUD) ====================

def list_pending_review_pages() -> list[dict]:
    return list_wiki_pages(status="pending_review")


def submit_for_review(data: dict) -> int:
    """Doc team submits knowledge. Auto-desensitized by caller."""
    return insert_wiki_page({**data, "status": "pending_review", "knowledge_type": "d1"})


def approve_page(page_id: int) -> bool:
    return update_wiki_page(page_id, {"status": "approved"})


def reject_page(page_id: int) -> bool:
    """Reject a pending page (set back to draft)."""
    return update_wiki_page(page_id, {"status": "draft"})


# ==================== D1 / D2 queries for ChromaDB and agent ====================

def list_approved_d1_pages() -> list[dict]:
    """Pages available for D1 ChromaDB vectorization."""
    c = get_conn()
    rows = c.execute(
        "SELECT * FROM wiki_pages WHERE knowledge_type = 'd1' AND status = 'approved'"
    ).fetchall()
    return [dict(r) for r in rows]


def list_d2_pages() -> list[dict]:
    """Pages available for D2 ChromaDB vectorization."""
    c = get_conn()
    rows = c.execute(
        "SELECT * FROM wiki_pages WHERE knowledge_type = 'd2'"
    ).fetchall()
    return [dict(r) for r in rows]


# ==================== Helpers ====================

def _next_id(c, table: str) -> int:
    row = c.execute(f"SELECT MAX(id) FROM {table}").fetchone()
    return (row[0] or 0) + 1


# ==================== Users ====================

def get_or_create_user(username: str, display_name: str = "", role: str = "cs") -> dict:
    c = get_conn()
    row = c.execute(
        "SELECT * FROM users WHERE username = ? AND role = ?", (username, role)
    ).fetchone()
    if not row:
        c.execute(
            "INSERT INTO users (username, display_name, role) VALUES (?, ?, ?)",
            (username, display_name or username, role)
        )
        _conn.commit()
        row = c.execute(
            "SELECT * FROM users WHERE username = ? AND role = ?", (username, role)
        ).fetchone()
    return dict(row)


def get_user(user_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


# ==================== Tickets ====================

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
            "SELECT t.* FROM tickets t "
            "JOIN escalations e ON t.id = e.ticket_id AND e.resolved_at IS NULL "
            "WHERE t.status != 'closed' ORDER BY t.created_at DESC"
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


def insert_ai_query_log(ticket_id: int, query_text: str, answer_text: str,
                        citations_json: str = "[]", confidence_score: float = 0,
                        confidence_label: str = "red", d2_match_found: bool = False) -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO ai_query_logs (ticket_id, query_text, answer_text, citations_json, "
        "confidence_score, confidence_label, d2_match_found) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticket_id, query_text, answer_text, citations_json,
         confidence_score, confidence_label, 1 if d2_match_found else 0)
    )
    _conn.commit()
    return cur.lastrowid


def escalate_ticket(ticket_id: int, reason: str = "") -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET status = 'escalated', "
        "updated_at = datetime('now') WHERE id = ?",
        (ticket_id,),
    )
    c.execute(
        "INSERT INTO escalations (ticket_id, reason) VALUES (?, ?)",
        (ticket_id, reason),
    )
    _conn.commit()
    return cur.rowcount > 0


def resolve_ticket_escalation(ticket_id: int, solution: str, version: Optional[str] = None) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET status = 'closed', service_ended = 1, "
        "updated_at = datetime('now') WHERE id = ?",
        (ticket_id,),
    )
    c.execute(
        "UPDATE escalations SET solution = ?, version = ?, resolved_at = datetime('now') "
        "WHERE ticket_id = ? AND resolved_at IS NULL",
        (solution, version, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def add_handling_record(ticket_id: int, notes: str, user_id: int = 0) -> bool:
    c = get_conn()
    c.execute(
        "INSERT INTO handling_records (ticket_id, user_id, notes) VALUES (?, ?, ?)",
        (ticket_id, user_id or None, notes),
    )
    _conn.commit()
    return True


# ==================== Messages ====================

def insert_message(ticket_id: int, sender_type: str, sender_name: str, content: str) -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO messages (ticket_id, sender_type, sender_name, content) VALUES (?, ?, ?, ?)",
        (ticket_id, sender_type, sender_name, content),
    )
    _conn.commit()
    return cur.lastrowid


def get_messages(ticket_id: int, after_id: int = 0, limit: int = 100) -> list[dict]:
    c = get_conn()
    rows = c.execute(
        "SELECT * FROM messages WHERE ticket_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
        (ticket_id, after_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_last_message_id(ticket_id: int) -> int:
    c = get_conn()
    row = c.execute(
        "SELECT MAX(id) FROM messages WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()
    return row[0] or 0


# ==================== Satisfaction Feedback ====================

def insert_satisfaction_feedback(ticket_id: int, resolved: str, feedback_text: str = "") -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO satisfaction_feedback (ticket_id, resolved, feedback_text) VALUES (?, ?, ?)",
        (ticket_id, resolved, feedback_text),
    )
    _conn.commit()
    return cur.lastrowid


def get_satisfaction_feedback(ticket_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute(
        "SELECT * FROM satisfaction_feedback WHERE ticket_id = ? ORDER BY id DESC LIMIT 1",
        (ticket_id,),
    ).fetchone()
    return dict(row) if row else None


# ==================== Ticket Assignment ====================

def assign_ticket_cs(ticket_id: int, cs_user_id: int = 0) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_cs_id = ?, updated_at = datetime('now') WHERE id = ?",
        (cs_user_id or None, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def clear_ticket_cs(ticket_id: int) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_cs_id = NULL, updated_at = datetime('now') WHERE id = ?",
        (ticket_id,),
    )
    _conn.commit()
    return cur.rowcount > 0


def assign_ticket_rd(ticket_id: int, rd_user_id: int = 0) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_rd_id = ?, updated_at = datetime('now') WHERE id = ?",
        (rd_user_id or None, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def update_ticket_customer(ticket_id: int, customer_user_id: int = 0) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET customer_user_id = ?, updated_at = datetime('now') WHERE id = ?",
        (customer_user_id or None, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def end_ticket_service(ticket_id: int) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET service_ended = 1, status = 'closed', updated_at = datetime('now') WHERE id = ?",
        (ticket_id,),
    )
    _conn.commit()
    return cur.rowcount > 0


def list_active_tickets_for_agent(agent_name: str, role: str) -> list[dict]:
    c = get_conn()
    if role == "cs":
        rows = c.execute(
            "SELECT t.* FROM tickets t "
            "LEFT JOIN escalations e ON t.id = e.ticket_id AND e.resolved_at IS NULL "
            "LEFT JOIN users u ON t.assigned_cs_id = u.id "
            "WHERE t.status != 'closed' AND t.service_ended = 0"
            " AND e.id IS NULL"
            " AND (u.username = ? OR t.assigned_cs_id IS NULL)"
            " ORDER BY t.updated_at DESC",
            (agent_name,),
        ).fetchall()
    elif role == "rd":
        rows = c.execute(
            "SELECT t.* FROM tickets t "
            "JOIN escalations e ON t.id = e.ticket_id AND e.resolved_at IS NULL "
            "WHERE t.status != 'closed' AND t.service_ended = 0 "
            "ORDER BY t.updated_at DESC",
        ).fetchall()
    else:
        rows = []
    return [dict(r) for r in rows]


def get_next_ticket_id() -> int:
    c = get_conn()
    row = c.execute("SELECT MAX(id) FROM tickets").fetchone()
    return (row[0] or 0) + 1


# ==================== Metrics ====================

def get_metrics() -> dict:
    c = get_conn()
    total = c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    week = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE date(created_at) >= date('now', '-6 days')"
    ).fetchone()[0]
    pending = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE status = 'pending'"
    ).fetchone()[0]
    escalated = c.execute(
        "SELECT COUNT(*) FROM escalations WHERE resolved_at IS NULL"
    ).fetchone()[0]
    escalated_waiting = c.execute(
        "SELECT COUNT(*) FROM escalations e "
        "JOIN tickets t ON t.id = e.ticket_id "
        "WHERE e.resolved_at IS NULL AND t.assigned_rd_id IS NULL"
    ).fetchone()[0]

    d1_count = c.execute(
        "SELECT COUNT(*) FROM wiki_pages WHERE knowledge_type = 'd1' AND status = 'approved'"
    ).fetchone()[0]
    d2_count = c.execute(
        "SELECT COUNT(*) FROM wiki_pages WHERE knowledge_type = 'd2'"
    ).fetchone()[0]
    pending_review = c.execute(
        "SELECT COUNT(*) FROM wiki_pages WHERE status = 'pending_review'"
    ).fetchone()[0]

    logs = c.execute("SELECT confidence_label, confidence_score FROM ai_query_logs").fetchall()
    green = sum(1 for r in logs if r["confidence_label"] == "green")
    yellow = sum(1 for r in logs if r["confidence_label"] == "yellow")
    red = sum(1 for r in logs if r["confidence_label"] == "red")
    total_logs = len(logs) or 1
    avg_conf = sum(r["confidence_score"] or 0 for r in logs) / total_logs
    ai_today = c.execute(
        "SELECT COUNT(*) FROM ai_query_logs WHERE date(created_at) = date('now')"
    ).fetchone()[0]

    sat_rows = c.execute(
        "SELECT resolved, COUNT(*) as cnt FROM satisfaction_feedback GROUP BY resolved"
    ).fetchall()
    sat_yes = sum(r["cnt"] for r in sat_rows if r["resolved"] == "yes")
    sat_no = sum(r["cnt"] for r in sat_rows if r["resolved"] == "no")

    user_rows = c.execute(
        "SELECT role, COUNT(*) as cnt FROM users GROUP BY role"
    ).fetchall()
    user_counts = {r["role"]: r["cnt"] for r in user_rows}

    return {
        "total_tickets": total,
        "week_tickets": week,
        "pending_tickets": pending,
        "escalated_count": escalated,
        "escalated_waiting": escalated_waiting,
        "escalation_rate": escalated / max(total, 1),
        "green_rate": green / total_logs,
        "yellow_rate": yellow / total_logs,
        "red_rate": red / total_logs,
        "avg_confidence": round(avg_conf, 2),
        "ai_queries_today": ai_today,
        "d1_doc_count": d1_count,
        "d2_doc_count": d2_count,
        "pending_review_count": pending_review,
        "satisfaction_yes": sat_yes,
        "satisfaction_no": sat_no,
        "cs_count": user_counts.get("cs", 0),
        "rd_count": user_counts.get("rd", 0),
        "doc_count": user_counts.get("doc", 0),
    }
