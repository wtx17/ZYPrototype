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
    new_cols = [
        ("assigned_cs", "TEXT"),
        ("assigned_rd", "TEXT"),
        ("customer_id", "TEXT"),
        ("service_ended", "INTEGER DEFAULT 0"),
    ]
    existing = {row[1] for row in c.execute("PRAGMA table_info(tickets)").fetchall()}
    for col_name, col_type in new_cols:
        if col_name not in existing:
            c.execute(f"ALTER TABLE tickets ADD COLUMN {col_name} {col_type}")
    _conn.commit()

    # Seed wiki_pages if empty (fresh install)
    count = c.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0]
    if count == 0:
        _seed_wiki_pages(c)


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

def assign_ticket_cs(ticket_id: int, cs_agent: str) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_cs = ?, updated_at = datetime('now') WHERE id = ?",
        (cs_agent, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def clear_ticket_cs(ticket_id: int) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_cs = NULL, updated_at = datetime('now') WHERE id = ?",
        (ticket_id,),
    )
    _conn.commit()
    return cur.rowcount > 0


def assign_ticket_rd(ticket_id: int, rd_agent: str) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_rd = ?, updated_at = datetime('now') WHERE id = ?",
        (rd_agent, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def update_ticket_customer(ticket_id: int, customer_id: str) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET customer_id = ?, updated_at = datetime('now') WHERE id = ?",
        (customer_id, ticket_id),
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
            "SELECT * FROM tickets WHERE status != 'closed' AND service_ended = 0"
            " AND escalated_to_rd = 0"
            " AND (assigned_cs = ? OR assigned_cs IS NULL OR assigned_cs = '')"
            " ORDER BY updated_at DESC",
            (agent_name,),
        ).fetchall()
    elif role == "rd":
        rows = c.execute(
            "SELECT * FROM tickets WHERE escalated_to_rd = 1 AND status != 'closed'"
            " AND service_ended = 0 ORDER BY updated_at DESC",
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
    escalated = c.execute("SELECT COUNT(*) FROM tickets WHERE escalated_to_rd = 1").fetchone()[0]
    d1_count = c.execute(
        "SELECT COUNT(*) FROM wiki_pages WHERE knowledge_type = 'd1' AND status = 'approved'"
    ).fetchone()[0]
    d2_count = c.execute(
        "SELECT COUNT(*) FROM wiki_pages WHERE knowledge_type = 'd2'"
    ).fetchone()[0]

    logs = c.execute(
        "SELECT ai_suggestion, ai_restricted_hint FROM tickets WHERE ai_suggestion IS NOT NULL"
    ).fetchall()
    green = yellow = red = 0
    for row in logs:
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
