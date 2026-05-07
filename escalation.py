"""Process 4 (工单升级) + Process 5 (反馈升级工单): Escalation logic.

Escalation triggers (BR-06):
  1. AI confidence < 0.6 (RED label)
  2. Query matches forbidden category
  3. Agent manually clicks "escalate"
  4. D2 restricted match found for CS query
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class EscalationReason(str, Enum):
    LOW_CONFIDENCE = "AI置信度过低(< 0.6)"
    FORBIDDEN_CATEGORY = "命中禁止回答类别"
    MANUAL = "客服主动升级"
    D2_RESTRICTED = "检测到内部技术资料，需二线支持"
    NO_KNOWLEDGE = "知识库无匹配结果"


def should_auto_escalate(
    confidence_label: str,
    is_blocked: bool = False,
    d2_match_found: bool = False,
    block_reason: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    if is_blocked:
        return True, block_reason or EscalationReason.FORBIDDEN_CATEGORY.value
    if confidence_label == "red":
        return True, EscalationReason.LOW_CONFIDENCE.value
    if d2_match_found:
        return True, EscalationReason.D2_RESTRICTED.value
    return False, None
