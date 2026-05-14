"""Session and role-based access control for the knowledge management system.

Uses in-memory session store with signed cookie (no external dependencies).
"""

import secrets
import time
from datetime import datetime
from typing import Optional

from fastapi import Request, HTTPException

from config import SESSION_TTL

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
_last_cleanup: float = time.time()
CLEANUP_INTERVAL = 300  # clean up expired sessions every 5 minutes


def _cleanup_expired():
    """Remove sessions past their TTL. No-op when SESSION_TTL is 0."""
    if SESSION_TTL <= 0:
        return
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    expired = [
        sid for sid, s in _sessions.items()
        if "expires_at" in s and s["expires_at"] < now
    ]
    for sid in expired:
        _sessions.pop(sid, None)


def create_session(role: str, username: str) -> str:
    from database import get_or_create_user

    session_id = secrets.token_urlsafe(32)
    user = get_or_create_user(username, username, role)
    now = datetime.now()
    session_data = {
        "role": role,
        "username": username,
        "display_name": user.get("display_name", username),
        "user_id": user["id"],
        "created_at": now.isoformat(),
    }
    if SESSION_TTL > 0:
        session_data["expires_at"] = time.time() + SESSION_TTL
    _sessions[session_id] = session_data
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    _cleanup_expired()
    session = _sessions.get(session_id)
    if SESSION_TTL > 0 and session:
        if "expires_at" not in session:
            session["expires_at"] = time.time() + SESSION_TTL
        elif session["expires_at"] < time.time():
            _sessions.pop(session_id, None)
            return None
    return session


def destroy_session(session_id: str):
    _sessions.pop(session_id, None)


def _extract_session_id(request: Request) -> Optional[str]:
    """Extract session_id from X-Session-Id header first, then cookie.

    Header is preferred for multi-role tab support (each tab stores its own
    session_id in sessionStorage). Cookie is the fallback for browser-default
    auth flow.
    """
    sid = request.headers.get("X-Session-Id")
    if sid:
        return sid
    return request.cookies.get("session_id")


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
