"""Process 4 (工单升级) + Process 5 (反馈升级工单): Escalation judgment logic.

Implements BR-06: Escalation triggers:
1. AI confidence < 0.6 (RED label)
2. Query matches forbidden category (BR-02)
3. Agent manually clicks "escalate"
4. Same ticket has 3 consecutive AI re-queries without adoption
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from database import get_ai_logs_for_ticket


class EscalationReason(str, Enum):
    LOW_CONFIDENCE = "AI置信度过低(< 0.6)"
    FORBIDDEN_CATEGORY = "命中禁止回答类别"
    MANUAL = "客服主动升级"
    RETRY_LIMIT = "同一工单连续3次AI查询未采纳"
    NO_KNOWLEDGE = "知识库无匹配结果"
    AGENT_DISCRETION = "客服判断需人工介入"


def should_auto_escalate(
    confidence_label: str,
    is_blocked: bool,
    block_reason: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Automatic escalation check after AI query.
    Returns (should_escalate, reason).
    """
    if is_blocked:
        return True, block_reason or EscalationReason.FORBIDDEN_CATEGORY.value

    if confidence_label == "red":
        return True, EscalationReason.LOW_CONFIDENCE.value

    return False, None


def check_retry_limit(ticket_id: str) -> tuple[bool, int]:
    """Check if a ticket has hit the 3-consecutive-retry limit (BR-06 condition 4).
    Returns (limit_reached, consecutive_count).
    """
    logs = get_ai_logs_for_ticket(ticket_id)
    if len(logs) < 3:
        return False, len(logs)

    # Check last 3 logs: if all have no feedback (not adopted), trigger escalation
    recent = logs[-3:]
    consecutive = 0
    for log_entry in reversed(recent):
        # A query without feedback is considered "not adopted"
        if log_entry.get("escalation_required") or log_entry.get("confidence_label") != "green":
            consecutive += 1
        else:
            break
    return consecutive >= 3, consecutive


def determine_escalation(
    ticket_id: str,
    confidence_label: str,
    is_blocked: bool,
    block_reason: Optional[str] = None,
    manual: bool = False,
) -> tuple[bool, Optional[str]]:
    """Full escalation decision combining auto-checks and manual trigger."""
    if manual:
        return True, EscalationReason.MANUAL.value

    auto, reason = should_auto_escalate(confidence_label, is_blocked, block_reason)
    if auto:
        return True, reason

    hit_limit, count = check_retry_limit(ticket_id)
    if hit_limit:
        return True, f"{EscalationReason.RETRY_LIMIT.value}(连续{count}次)"

    return False, None
