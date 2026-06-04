"""Database layer: SQLite schema and CRUD for tickets, users, and wiki knowledge."""

import re
import sqlite3
from datetime import datetime
from typing import Optional

from config import SQLITE_PATH

_conn: Optional[sqlite3.Connection] = None

ROLE_PREFIXES = {
    "manager": "MGR",
    "cs": "CS",
    "customer": "CUS",
    "rd": "RD",
    "doc": "DOC",
}

ENTRY_TYPE_DEFAULTS = [
    ("general", "通用文档"),
    ("solution", "技术方案"),
    ("release_note", "发布说明"),
]

APP_TABLES = [
    "wiki_page_keywords",
    "knowledge_keywords",
    "wiki_page_versions",
    "wiki_pages",
    "entry_types",
    "handling_records",
    "escalations",
    "ai_query_logs",
    "satisfaction_feedback",
    "messages",
    "tickets",
    "users",
    "ai_knowledge",
    "rd_knowledge",
    "wiki_import_log",
]


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _init_db()
    return _conn


def _init_db():
    c = _conn
    if c is None:
        return

    if _schema_is_legacy(c):
        _drop_app_tables(c)

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            role TEXT NOT NULL CHECK(role IN ('manager', 'cs', 'customer', 'rd', 'doc')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(username, role)
        );

        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            assigned_cs_id TEXT REFERENCES users(id),
            assigned_rd_id TEXT REFERENCES users(id),
            customer_user_id TEXT REFERENCES users(id),
            service_ended INTEGER DEFAULT 0,
            cs_accepted_at TIMESTAMP,
            rd_accepted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
        CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets(customer_user_id);
        CREATE INDEX IF NOT EXISTS idx_tickets_updated ON tickets(updated_at);

        CREATE TABLE IF NOT EXISTS entry_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wiki_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            parent_id INTEGER REFERENCES wiki_pages(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'draft',
            knowledge_type TEXT DEFAULT 'd1',
            owner_user_id TEXT REFERENCES users(id),
            entry_type_id INTEGER REFERENCES entry_types(id),
            version TEXT DEFAULT '',
            release_note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_wiki_pages_status ON wiki_pages(status);
        CREATE INDEX IF NOT EXISTS idx_wiki_pages_type ON wiki_pages(knowledge_type);
        CREATE INDEX IF NOT EXISTS idx_wiki_pages_parent ON wiki_pages(parent_id);
        CREATE INDEX IF NOT EXISTS idx_wiki_pages_entry_type ON wiki_pages(entry_type_id);

        CREATE TABLE IF NOT EXISTS knowledge_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wiki_page_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
            keyword_id INTEGER NOT NULL REFERENCES knowledge_keywords(id),
            UNIQUE(page_id, keyword_id)
        );

        CREATE INDEX IF NOT EXISTS idx_wiki_page_keywords_page ON wiki_page_keywords(page_id);
        CREATE INDEX IF NOT EXISTS idx_wiki_page_keywords_keyword ON wiki_page_keywords(keyword_id);

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            sender_type TEXT NOT NULL CHECK(sender_type IN ('customer', 'cs', 'rd', 'system')),
            sender_name TEXT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_messages_ticket ON messages(ticket_id);

        CREATE TABLE IF NOT EXISTS satisfaction_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            resolved TEXT,
            feedback_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_satisfaction_ticket ON satisfaction_feedback(ticket_id);

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
            user_id TEXT REFERENCES users(id),
            notes TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_handling_records_ticket ON handling_records(ticket_id);

        CREATE TABLE IF NOT EXISTS wiki_page_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            editor TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_wiki_page_versions_page ON wiki_page_versions(page_id);
    """)

    _seed_entry_types(c)
    _seed_default_users(c)
    if c.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0] == 0:
        _seed_wiki_pages(c)
    _conn.commit()


def _schema_is_legacy(c: sqlite3.Connection) -> bool:
    users_cols = _table_columns(c, "users")
    tickets_cols = _table_columns(c, "tickets")
    wiki_cols = _table_columns(c, "wiki_pages")
    if not users_cols and not tickets_cols and not wiki_cols:
        return False
    if users_cols and (users_cols.get("id", "").upper() != "TEXT"):
        return True
    if "created_by" in tickets_cols:
        return True
    if {"category", "keywords", "source", "source_ticket_id"} & set(wiki_cols):
        return True
    if "entry_type_id" not in wiki_cols and wiki_cols:
        return True
    return False


def _table_columns(c: sqlite3.Connection, table: str) -> dict[str, str]:
    rows = c.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"]: r["type"] for r in rows}


def _drop_app_tables(c: sqlite3.Connection):
    c.execute("PRAGMA foreign_keys = OFF")
    for table in APP_TABLES:
        c.execute(f"DROP TABLE IF EXISTS {table}")
    c.execute("PRAGMA foreign_keys = ON")
    c.commit()


def _seed_entry_types(c: sqlite3.Connection):
    for code, name in ENTRY_TYPE_DEFAULTS:
        c.execute(
            "INSERT OR IGNORE INTO entry_types (code, name) VALUES (?, ?)",
            (code, name),
        )


def _seed_default_users(c: sqlite3.Connection):
    defaults = [
        ("CS001", "小陈", "小陈", "cs"),
        ("RD001", "王工", "王工", "rd"),
        ("DOC001", "李婷", "李婷", "doc"),
        ("MGR001", "林总", "林总", "manager"),
    ]
    for user_id, username, display_name, role in defaults:
        c.execute(
            "INSERT OR IGNORE INTO users (id, username, display_name, role) VALUES (?, ?, ?, ?)",
            (user_id, username, display_name, role),
        )


def _seed_wiki_pages(c: sqlite3.Connection):
    from seed_data import AI_KNOWLEDGE_ENTRIES, RD_KNOWLEDGE_ENTRIES

    now = datetime.now().isoformat()
    doc_user_id = _resolve_user_id("DOC001") or "DOC001"
    rd_user_id = _resolve_user_id("RD001") or "RD001"

    for entry in AI_KNOWLEDGE_ENTRIES:
        insert_wiki_page({
            "title": entry["title"],
            "content": entry["content"],
            "owner_user_id": doc_user_id,
            "status": "approved",
            "knowledge_type": "d1",
            "entry_type": "general",
            "keywords": entry.get("keywords", ""),
            "created_at": now,
            "updated_at": now,
        })

    for entry in RD_KNOWLEDGE_ENTRIES:
        insert_wiki_page({
            "title": entry["title"],
            "content": entry["content"],
            "owner_user_id": rd_user_id,
            "status": "draft",
            "knowledge_type": "d2",
            "entry_type": entry.get("entry_type", "solution"),
            "version": entry.get("version", ""),
            "keywords": entry.get("keywords", ""),
            "release_note": entry.get("release_note") or "",
            "created_at": now,
            "updated_at": now,
        })


# ==================== Helpers ====================

def _generate_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9_-]', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


def _next_autoincrement_hint(c: sqlite3.Connection, table: str) -> int:
    row = c.execute(f"SELECT MAX(id) FROM {table}").fetchone()
    return (row[0] or 0) + 1


def _next_user_id(c: sqlite3.Connection, role: str) -> str:
    prefix = ROLE_PREFIXES.get(role)
    if not prefix:
        raise ValueError(f"Unsupported role: {role}")
    row = c.execute(
        "SELECT id FROM users WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    next_no = 1
    if row:
        m = re.match(rf"^{re.escape(prefix)}(\d+)$", row["id"])
        if m:
            next_no = int(m.group(1)) + 1
    return f"{prefix}{next_no:03d}"


def _next_ticket_id(c: sqlite3.Connection) -> int:
    prefix = datetime.now().strftime("%Y%m%d")
    start = int(f"{prefix}0000")
    end = int(f"{prefix}9999")
    row = c.execute(
        "SELECT MAX(id) FROM tickets WHERE id BETWEEN ? AND ?",
        (start, end),
    ).fetchone()
    return (row[0] or start) + 1


def _entry_type_id(code: Optional[str]) -> int:
    c = get_conn()
    normalized = (code or "general").strip() or "general"
    row = c.execute("SELECT id FROM entry_types WHERE code = ?", (normalized,)).fetchone()
    if row:
        return row["id"]
    cur = c.execute(
        "INSERT INTO entry_types (code, name) VALUES (?, ?)",
        (normalized, normalized),
    )
    _conn.commit()
    return cur.lastrowid


def _resolve_user_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    c = get_conn()
    row = c.execute("SELECT id FROM users WHERE id = ?", (value,)).fetchone()
    if row:
        return row["id"]
    row = c.execute(
        "SELECT id FROM users WHERE username = ? ORDER BY created_at ASC LIMIT 1",
        (value,),
    ).fetchone()
    return row["id"] if row else None


def _split_keywords(keywords: Optional[str]) -> list[str]:
    if not keywords:
        return []
    parts = re.split(r"[,，]", keywords)
    seen = set()
    result = []
    for part in parts:
        kw = part.strip()
        key = kw.lower()
        if kw and key not in seen:
            seen.add(key)
            result.append(kw)
    return result


def _set_page_keywords(page_id: int, keywords: Optional[str]):
    c = get_conn()
    c.execute("DELETE FROM wiki_page_keywords WHERE page_id = ?", (page_id,))
    for keyword in _split_keywords(keywords):
        c.execute("INSERT OR IGNORE INTO knowledge_keywords (name) VALUES (?)", (keyword,))
        row = c.execute("SELECT id FROM knowledge_keywords WHERE name = ?", (keyword,)).fetchone()
        if row:
            c.execute(
                "INSERT OR IGNORE INTO wiki_page_keywords (page_id, keyword_id) VALUES (?, ?)",
                (page_id, row["id"]),
            )


def _page_keywords(page_id: int) -> str:
    c = get_conn()
    rows = c.execute(
        "SELECT kk.name FROM knowledge_keywords kk "
        "JOIN wiki_page_keywords wpk ON wpk.keyword_id = kk.id "
        "WHERE wpk.page_id = ? ORDER BY kk.name",
        (page_id,),
    ).fetchall()
    return ",".join(r["name"] for r in rows)


def _page_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["entry_type"] = d.pop("entry_type", None) or ""
    d["owner"] = d.get("owner_username") or d.get("owner_user_id") or ""
    d["keywords"] = _page_keywords(d["id"])
    return d


def _page_select_sql() -> str:
    return (
        "SELECT wp.*, et.code AS entry_type, "
        "u.username AS owner_username, u.display_name AS owner_name "
        "FROM wiki_pages wp "
        "LEFT JOIN entry_types et ON wp.entry_type_id = et.id "
        "LEFT JOIN users u ON wp.owner_user_id = u.id "
    )


# ==================== Users ====================

def get_or_create_user(username: str, display_name: str = "", role: str = "cs") -> dict:
    c = get_conn()
    row = c.execute(
        "SELECT * FROM users WHERE username = ? AND role = ?", (username, role)
    ).fetchone()
    if not row:
        user_id = _next_user_id(c, role)
        c.execute(
            "INSERT INTO users (id, username, display_name, role) VALUES (?, ?, ?, ?)",
            (user_id, username, display_name or username, role),
        )
        _conn.commit()
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)


def get_user(user_id: str) -> Optional[dict]:
    c = get_conn()
    row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


# ==================== Wiki Pages CRUD ====================

def list_wiki_pages(status: Optional[str] = None,
                    knowledge_type: Optional[str] = None) -> list[dict]:
    c = get_conn()
    conditions = []
    params = []
    if status:
        conditions.append("wp.status = ?")
        params.append(status)
    if knowledge_type:
        conditions.append("wp.knowledge_type = ?")
        params.append(knowledge_type)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = c.execute(
        _page_select_sql() + where + " ORDER BY wp.created_at ASC",
        params,
    ).fetchall()
    return [_page_row_to_dict(r) for r in rows]


def get_wiki_page(page_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute(_page_select_sql() + " WHERE wp.id = ?", (page_id,)).fetchone()
    return _page_row_to_dict(row) if row else None


def get_wiki_page_by_slug(slug: str) -> Optional[dict]:
    c = get_conn()
    row = c.execute(_page_select_sql() + " WHERE wp.slug = ?", (slug,)).fetchone()
    return _page_row_to_dict(row) if row else None


def insert_wiki_page(data: dict) -> int:
    c = get_conn()
    base_slug = _generate_slug(data["title"])
    slug = base_slug if base_slug else f"page-{_next_autoincrement_hint(c, 'wiki_pages')}"
    if c.execute("SELECT 1 FROM wiki_pages WHERE slug = ?", (slug,)).fetchone():
        slug = f"{slug}-{_next_autoincrement_hint(c, 'wiki_pages')}"

    owner_user_id = data.get("owner_user_id") or _resolve_user_id(data.get("owner"))
    entry_type_id = _entry_type_id(data.get("entry_type"))
    parent_id = data.get("parent_id") or None
    values = {
        "slug": slug,
        "title": data["title"],
        "content": data.get("content", ""),
        "parent_id": parent_id,
        "status": data.get("status", "draft"),
        "knowledge_type": data.get("knowledge_type", "d1"),
        "owner_user_id": owner_user_id,
        "entry_type_id": entry_type_id,
        "version": data.get("version", "") or "",
        "release_note": data.get("release_note", "") or "",
        "created_at": data.get("created_at") or datetime.now().isoformat(),
        "updated_at": data.get("updated_at") or datetime.now().isoformat(),
    }
    cur = c.execute(
        "INSERT INTO wiki_pages (slug, title, content, parent_id, status, knowledge_type, "
        "owner_user_id, entry_type_id, version, release_note, created_at, updated_at) "
        "VALUES (:slug, :title, :content, :parent_id, :status, :knowledge_type, "
        ":owner_user_id, :entry_type_id, :version, :release_note, :created_at, :updated_at)",
        values,
    )
    page_id = cur.lastrowid
    _set_page_keywords(page_id, data.get("keywords", ""))
    _conn.commit()
    return page_id


def update_wiki_page(page_id: int, data: dict, editor: str = "") -> bool:
    c = get_conn()

    if editor and ("title" in data or "content" in data):
        row = c.execute("SELECT title, content FROM wiki_pages WHERE id = ?", (page_id,)).fetchone()
        if row:
            save_wiki_page_version(page_id, row["title"], row["content"], editor)

    fields = []
    values = []
    direct_fields = ("title", "content", "parent_id", "status", "knowledge_type",
                     "version", "release_note")
    for key in direct_fields:
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key] or None if key == "parent_id" else data[key])

    if "owner_user_id" in data or "owner" in data:
        fields.append("owner_user_id = ?")
        values.append(data.get("owner_user_id") or _resolve_user_id(data.get("owner")))

    if "entry_type" in data:
        fields.append("entry_type_id = ?")
        values.append(_entry_type_id(data.get("entry_type")))

    if "title" in data:
        base_slug = _generate_slug(data["title"])
        slug = base_slug if base_slug else f"page-{page_id}"
        if c.execute("SELECT 1 FROM wiki_pages WHERE slug = ? AND id != ?",
                     (slug, page_id)).fetchone():
            slug = f"{slug}-{page_id}"
        fields.append("slug = ?")
        values.append(slug)

    if "keywords" in data:
        _set_page_keywords(page_id, data.get("keywords", ""))

    if not fields and "keywords" not in data:
        return False
    if fields:
        fields.append("updated_at = datetime('now', 'localtime')")
        values.append(page_id)
        cur = c.execute(f"UPDATE wiki_pages SET {', '.join(fields)} WHERE id = ?", values)
    else:
        cur = c.execute(
            "UPDATE wiki_pages SET updated_at = datetime('now', 'localtime') WHERE id = ?",
            (page_id,),
        )
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
    params = [query, query, like, like]
    where = "WHERE wp.title LIKE ? OR wp.content LIKE ?"
    if knowledge_type:
        where = "WHERE (wp.title LIKE ? OR wp.content LIKE ?) AND wp.knowledge_type = ?"
        params.append(knowledge_type)
    rows = c.execute(
        "SELECT wp.id, wp.slug, wp.title, wp.updated_at, wp.knowledge_type, et.code AS entry_type, "
        "CASE WHEN instr(wp.content, ?) > 0 THEN substr(wp.content, max(instr(wp.content, ?) - 30, 1), min(length(wp.content), 150)) "
        "ELSE substr(wp.content, 1, 120) END AS snippet "
        "FROM wiki_pages wp LEFT JOIN entry_types et ON wp.entry_type_id = et.id "
        f"{where} ORDER BY wp.updated_at DESC LIMIT 20",
        params,
    ).fetchall()
    results = [dict(r) for r in rows]
    for r in results:
        r["keywords"] = _page_keywords(r["id"])
    return results


def list_pending_review_pages() -> list[dict]:
    return list_wiki_pages(status="pending_review")


def submit_for_review(data: dict) -> int:
    return insert_wiki_page({**data, "status": "pending_review", "knowledge_type": "d1"})


def approve_page(page_id: int) -> bool:
    return update_wiki_page(page_id, {"status": "approved"})


def reject_page(page_id: int) -> bool:
    return update_wiki_page(page_id, {"status": "draft"})


def list_wiki_keywords(knowledge_type: Optional[str] = None) -> list[dict]:
    pages = list_wiki_pages(knowledge_type=knowledge_type)
    return [
        {"title": p["title"], "slug": p["slug"], "keywords": p.get("keywords", "")}
        for p in pages
    ]


def list_approved_d1_pages() -> list[dict]:
    c = get_conn()
    rows = c.execute(
        _page_select_sql() + " WHERE wp.knowledge_type = 'd1' AND wp.status = 'approved'"
    ).fetchall()
    return [_page_row_to_dict(r) for r in rows]


def list_d2_pages() -> list[dict]:
    c = get_conn()
    rows = c.execute(_page_select_sql() + " WHERE wp.knowledge_type = 'd2'").fetchall()
    return [_page_row_to_dict(r) for r in rows]


def get_related_pages(page_id: int, limit: int = 5) -> list[dict]:
    c = get_conn()
    page = get_wiki_page(page_id)
    if not page:
        return []

    result_ids = set()
    results = []

    keyword_rows = c.execute(
        "SELECT keyword_id FROM wiki_page_keywords WHERE page_id = ?",
        (page_id,),
    ).fetchall()
    keyword_ids = [r["keyword_id"] for r in keyword_rows]
    if keyword_ids:
        placeholders = ",".join("?" for _ in keyword_ids)
        rows = c.execute(
            "SELECT DISTINCT wp.id, wp.title, wp.slug, wp.knowledge_type "
            "FROM wiki_pages wp "
            "JOIN wiki_page_keywords wpk ON wpk.page_id = wp.id "
            f"WHERE wp.id != ? AND wp.knowledge_type = ? AND wpk.keyword_id IN ({placeholders}) "
            "ORDER BY wp.id DESC LIMIT ?",
            [page_id, page["knowledge_type"], *keyword_ids, limit],
        ).fetchall()
        for r in rows:
            result_ids.add(r["id"])
            d = dict(r)
            d["keywords"] = _page_keywords(r["id"])
            results.append(d)

    if len(results) < limit and page.get("parent_id") is not None:
        rows = c.execute(
            "SELECT id, title, slug, knowledge_type FROM wiki_pages "
            "WHERE id != ? AND parent_id = ? ORDER BY id DESC LIMIT ?",
            (page_id, page["parent_id"], limit - len(results)),
        ).fetchall()
        for r in rows:
            if r["id"] not in result_ids:
                result_ids.add(r["id"])
                d = dict(r)
                d["keywords"] = _page_keywords(r["id"])
                results.append(d)

    if len(results) < limit:
        rows = c.execute(
            "SELECT id, title, slug, knowledge_type FROM wiki_pages "
            "WHERE id != ? AND knowledge_type = ? ORDER BY id DESC LIMIT ?",
            (page_id, page["knowledge_type"], limit - len(results)),
        ).fetchall()
        for r in rows:
            if r["id"] not in result_ids:
                d = dict(r)
                d["keywords"] = _page_keywords(r["id"])
                results.append(d)

    return results


# ==================== Tickets ====================

def insert_ticket(data: dict) -> int:
    c = get_conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        ticket_id = _next_ticket_id(c)
        c.execute(
            "INSERT INTO tickets (id, title, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                ticket_id,
                data["title"],
                data.get("description", ""),
                data.get("status", "pending"),
                data.get("created_at") or datetime.now().isoformat(),
                data.get("updated_at") or datetime.now().isoformat(),
            ),
        )
        _conn.commit()
        return ticket_id
    except Exception:
        _conn.rollback()
        raise


def get_ticket(ticket_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute(
        "SELECT t.*, cs.display_name AS cs_name, rd.display_name AS rd_name, "
        "cust.display_name AS customer_name "
        "FROM tickets t "
        "LEFT JOIN users cs ON t.assigned_cs_id = cs.id "
        "LEFT JOIN users rd ON t.assigned_rd_id = rd.id "
        "LEFT JOIN users cust ON t.customer_user_id = cust.id "
        "WHERE t.id = ?",
        (ticket_id,),
    ).fetchone()
    return dict(row) if row else None


def list_tickets(escalated_only: bool = False) -> list[dict]:
    c = get_conn()
    if escalated_only:
        rows = c.execute(
            "SELECT t.*, rd.display_name AS rd_name, cust.display_name AS customer_name "
            "FROM tickets t "
            "JOIN escalations e ON t.id = e.ticket_id AND e.resolved_at IS NULL "
            "LEFT JOIN users rd ON t.assigned_rd_id = rd.id "
            "LEFT JOIN users cust ON t.customer_user_id = cust.id "
            "WHERE t.status != 'closed' ORDER BY t.created_at DESC"
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT t.*, "
            "cs.display_name AS cs_name, "
            "rd.display_name AS rd_name, "
            "cust.display_name AS customer_name, "
            "sf.resolved AS satisfaction, "
            "sf.feedback_text AS satisfaction_feedback "
            "FROM tickets t "
            "LEFT JOIN users cs ON t.assigned_cs_id = cs.id "
            "LEFT JOIN users rd ON t.assigned_rd_id = rd.id "
            "LEFT JOIN users cust ON t.customer_user_id = cust.id "
            "LEFT JOIN satisfaction_feedback sf ON t.id = sf.ticket_id "
            "ORDER BY t.created_at DESC LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]


def update_ticket_status(ticket_id: int, status: str):
    c = get_conn()
    c.execute(
        "UPDATE tickets SET status = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (status, ticket_id),
    )
    _conn.commit()


def insert_ai_query_log(ticket_id: int, query_text: str, answer_text: str,
                        citations_json: str = "[]", confidence_score: float = 0,
                        confidence_label: str = "red", d2_match_found: bool = False) -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO ai_query_logs (ticket_id, query_text, answer_text, citations_json, "
        "confidence_score, confidence_label, d2_match_found, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))",
        (ticket_id, query_text, answer_text, citations_json,
         confidence_score, confidence_label, 1 if d2_match_found else 0),
    )
    _conn.commit()
    return cur.lastrowid


def list_ai_query_logs(ticket_id: int) -> list[dict]:
    c = get_conn()
    rows = c.execute(
        "SELECT * FROM ai_query_logs WHERE ticket_id = ? ORDER BY created_at ASC",
        (ticket_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def escalate_ticket(ticket_id: int, reason: str = "") -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET status = 'escalated', "
        "updated_at = datetime('now', 'localtime') WHERE id = ?",
        (ticket_id,),
    )
    c.execute(
        "INSERT INTO escalations (ticket_id, reason, created_at) "
        "VALUES (?, ?, datetime('now', 'localtime'))",
        (ticket_id, reason),
    )
    _conn.commit()
    return cur.rowcount > 0


def resolve_ticket_escalation(ticket_id: int, solution: str, version: Optional[str] = None) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET status = 'closed', service_ended = 1, "
        "updated_at = datetime('now', 'localtime') WHERE id = ?",
        (ticket_id,),
    )
    c.execute(
        "UPDATE escalations SET solution = ?, version = ?, resolved_at = datetime('now', 'localtime') "
        "WHERE ticket_id = ? AND resolved_at IS NULL",
        (solution, version, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def add_handling_record(ticket_id: int, notes: str, user_id: str = "") -> bool:
    c = get_conn()
    c.execute(
        "INSERT INTO handling_records (ticket_id, user_id, notes, created_at) "
        "VALUES (?, ?, ?, datetime('now', 'localtime'))",
        (ticket_id, user_id or None, notes),
    )
    _conn.commit()
    return True


# ==================== Messages ====================

def insert_message(ticket_id: int, sender_type: str, sender_name: str, content: str) -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO messages (ticket_id, sender_type, sender_name, content, created_at) "
        "VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
        (ticket_id, sender_type, sender_name, content),
    )
    c.execute(
        "UPDATE tickets SET updated_at = datetime('now', 'localtime') WHERE id = ?",
        (ticket_id,),
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
        "SELECT MAX(id) FROM messages WHERE ticket_id = ?", (ticket_id,),
    ).fetchone()
    return row[0] or 0


# ==================== Satisfaction Feedback ====================

def insert_satisfaction_feedback(ticket_id: int, resolved: str, feedback_text: str = "") -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO satisfaction_feedback (ticket_id, resolved, feedback_text, created_at) "
        "VALUES (?, ?, ?, datetime('now', 'localtime'))",
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

def assign_ticket_cs(ticket_id: int, cs_user_id: str = "") -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_cs_id = ?, cs_accepted_at = datetime('now', 'localtime'), "
        "updated_at = datetime('now', 'localtime') WHERE id = ?",
        (cs_user_id or None, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def clear_ticket_cs(ticket_id: int) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_cs_id = NULL, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (ticket_id,),
    )
    _conn.commit()
    return cur.rowcount > 0


def assign_ticket_rd(ticket_id: int, rd_user_id: str = "") -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET assigned_rd_id = ?, rd_accepted_at = datetime('now', 'localtime'), "
        "updated_at = datetime('now', 'localtime') WHERE id = ?",
        (rd_user_id or None, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def update_ticket_customer(ticket_id: int, customer_user_id: str = "") -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET customer_user_id = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (customer_user_id or None, ticket_id),
    )
    _conn.commit()
    return cur.rowcount > 0


def end_ticket_service(ticket_id: int) -> bool:
    c = get_conn()
    cur = c.execute(
        "UPDATE tickets SET service_ended = 1, status = 'closed', updated_at = datetime('now', 'localtime') WHERE id = ?",
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
            "WHERE t.status != 'closed' AND t.service_ended = 0 "
            "AND e.id IS NULL "
            "AND (u.username = ? OR t.assigned_cs_id IS NULL) "
            "ORDER BY t.updated_at DESC",
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
    return _next_ticket_id(get_conn())


# ==================== Metrics ====================

def get_metrics() -> dict:
    c = get_conn()
    total = c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    today = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE date(created_at) = date('now')"
    ).fetchone()[0]
    week = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE date(created_at) >= date('now', '-6 days')"
    ).fetchone()[0]
    pending = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE status = 'pending'"
    ).fetchone()[0]
    escalated = c.execute(
        "SELECT COUNT(*) FROM escalations WHERE resolved_at IS NULL"
    ).fetchone()[0]
    escalated_total = c.execute(
        "SELECT COUNT(DISTINCT ticket_id) FROM escalations"
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
    doc_updates_today = c.execute(
        "SELECT COUNT(*) FROM wiki_page_versions WHERE date(created_at) = date('now')"
    ).fetchone()[0]

    sat_rows = c.execute(
        "SELECT resolved, COUNT(*) as cnt FROM satisfaction_feedback GROUP BY resolved"
    ).fetchall()
    sat_yes = sum(r["cnt"] for r in sat_rows if r["resolved"] == "yes")
    sat_no = sum(r["cnt"] for r in sat_rows if r["resolved"] == "no")

    sla_sec = 24 * 3600
    avg_resp = c.execute(
        "SELECT AVG(CAST(strftime('%s', cs_accepted_at) AS REAL) "
        "- CAST(strftime('%s', created_at) AS REAL)) "
        "FROM tickets WHERE cs_accepted_at IS NOT NULL "
        "AND cs_accepted_at >= created_at"
    ).fetchone()[0]
    avg_resolution = c.execute(
        "SELECT AVG(CAST(strftime('%s', updated_at) AS REAL) "
        "- CAST(strftime('%s', created_at) AS REAL)) "
        "FROM tickets WHERE service_ended = 1 "
        "AND updated_at >= created_at"
    ).fetchone()[0]
    sla_total_closed = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE service_ended = 1"
    ).fetchone()[0]
    sla_compliant = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE service_ended = 1 "
        "AND updated_at >= created_at "
        "AND (CAST(strftime('%s', updated_at) AS REAL) - "
        "CAST(strftime('%s', created_at) AS REAL)) <= ?",
        (sla_sec,),
    ).fetchone()[0]
    sla_at_risk = c.execute(
        "SELECT COUNT(*) FROM tickets "
        "WHERE service_ended = 0 AND status != 'closed' "
        "AND (CAST(strftime('%s', 'now') AS REAL) - "
        "CAST(strftime('%s', created_at) AS REAL)) > ?",
        (sla_sec,),
    ).fetchone()[0]

    user_rows = c.execute("SELECT role, COUNT(*) as cnt FROM users GROUP BY role").fetchall()
    user_counts = {r["role"]: r["cnt"] for r in user_rows}

    ticket_daily_rows = c.execute(
        "SELECT date(created_at) as day, COUNT(*) as cnt "
        "FROM tickets WHERE date(created_at) >= date('now', '-6 days') GROUP BY day"
    ).fetchall()
    escalation_daily_rows = c.execute(
        "SELECT date(created_at) as day, COUNT(*) as cnt "
        "FROM escalations WHERE date(created_at) >= date('now', '-6 days') GROUP BY day"
    ).fetchall()
    ticket_daily = {r["day"]: r["cnt"] for r in ticket_daily_rows}
    escalation_daily = {r["day"]: r["cnt"] for r in escalation_daily_rows}
    history_days = c.execute(
        "WITH RECURSIVE days(day, n) AS ("
        "  SELECT date('now', '-6 days'), 0 "
        "  UNION ALL "
        "  SELECT date(day, '+1 day'), n + 1 FROM days WHERE n < 6"
        ") SELECT day, strftime('%m/%d', day) as label FROM days"
    ).fetchall()
    daily_operations = [
        {
            "date": r["day"],
            "label": r["label"],
            "tickets": ticket_daily.get(r["day"], 0),
            "escalations": escalation_daily.get(r["day"], 0),
        }
        for r in history_days
    ]

    return {
        "total_tickets": total,
        "today_tickets": today,
        "week_tickets": week,
        "pending_tickets": pending,
        "escalated_count": escalated,
        "escalated_total": escalated_total,
        "escalated_waiting": escalated_waiting,
        "escalation_rate": escalated_total / max(total, 1),
        "green_rate": green / total_logs,
        "yellow_rate": yellow / total_logs,
        "red_rate": red / total_logs,
        "avg_confidence": round(avg_conf, 2),
        "ai_queries_today": ai_today,
        "doc_updates_today": doc_updates_today,
        "d1_doc_count": d1_count,
        "d2_doc_count": d2_count,
        "pending_review_count": pending_review,
        "satisfaction_yes": sat_yes,
        "satisfaction_no": sat_no,
        "sla_response_sec": round(avg_resp or 0),
        "sla_resolution_sec": round(avg_resolution or 0),
        "sla_compliance_rate": sla_compliant / max(sla_total_closed, 1),
        "sla_at_risk": sla_at_risk,
        "sla_total_closed": sla_total_closed,
        "sla_compliant_count": sla_compliant,
        "cs_count": user_counts.get("cs", 0),
        "rd_count": user_counts.get("rd", 0),
        "doc_count": user_counts.get("doc", 0),
        "daily_operations": daily_operations,
    }


# ==================== Wiki Page Versions ====================

def save_wiki_page_version(page_id: int, title: str, content: str, editor: str) -> int:
    c = get_conn()
    cur = c.execute(
        "INSERT INTO wiki_page_versions (page_id, title, content, editor, created_at) "
        "VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
        (page_id, title, content, editor),
    )
    _conn.commit()
    return cur.lastrowid


def list_wiki_page_versions(page_id: int) -> list[dict]:
    c = get_conn()
    rows = c.execute(
        "SELECT id, page_id, title, editor, created_at FROM wiki_page_versions "
        "WHERE page_id = ? ORDER BY created_at DESC",
        (page_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_wiki_page_version(version_id: int) -> Optional[dict]:
    c = get_conn()
    row = c.execute(
        "SELECT * FROM wiki_page_versions WHERE id = ?", (version_id,),
    ).fetchone()
    return dict(row) if row else None
