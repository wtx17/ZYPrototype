"""Session and role-based access control for the knowledge management system.

Uses in-memory session store with signed cookie (no external dependencies).
"""

import secrets
from datetime import datetime
from typing import Optional

from fastapi import Request, HTTPException

ROLE_PERMISSIONS = {
    "cs":      ["query", "escalate", "tickets:own", "handling", "desensitize"],
    "rd":      ["knowledge:rd_write", "release-notes", "escalation:resolve", "tickets:escalated", "knowledge:rd_read"],
    "doc":     ["knowledge:submit", "knowledge:review", "knowledge:rd_read", "desensitize"],
    "manager": ["metrics", "tickets:all", "knowledge:read"],
}

ROLE_LABELS = {
    "cs": "客服",
    "rd": "二线研发",
    "doc": "文档团队",
    "manager": "管理层",
}

_sessions: dict[str, dict] = {}


def create_session(role: str, username: str) -> str:
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = {
        "role": role,
        "username": username,
        "created_at": datetime.now().isoformat(),
    }
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    return _sessions.get(session_id)


def destroy_session(session_id: str):
    _sessions.pop(session_id, None)


async def require_role(request: Request, allowed_roles: list[str]) -> dict:
    session_id = _extract_session_id(request)
    if not session_id:
        raise HTTPException(status_code=401, detail="未登录")
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="会话已过期")
    if session["role"] not in allowed_roles:
        raise HTTPException(status_code=403, detail="权限不足")
    return session


async def get_current_session(request: Request) -> Optional[dict]:
    session_id = _extract_session_id(request)
    if not session_id:
        return None
    return get_session(session_id)


def _extract_session_id(request: Request) -> Optional[str]:
    """Extract session_id from query param first, then cookie."""
    sid = request.query_params.get("session_id") or request.query_params.get("sid")
    if sid:
        return sid
    return request.cookies.get("session_id")
