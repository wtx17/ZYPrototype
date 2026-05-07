"""Process 1 (AI处理): Dual-collection RAG pipeline with D1/D2 permission isolation.

CS queries:
  - D1: full content retrieved → LLM context
  - D2: presence check only (boolean) → NO content in LLM context
  - If D2 matches: append upgrade hint, set d2_match_found=True

RD/Doc queries:
  - Both D1 and D2 full content available
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config import (
    DASHSCOPE_API_KEY,
    BAILIAN_BASE_URL,
    LLM_MODEL,
    CONFIDENCE_GREEN,
    CONFIDENCE_YELLOW,
    FORBIDDEN_PATTERNS,
)
from desensitizer import desensitize
from knowledge_store import retrieve_ai_knowledge, retrieve_rd_knowledge, check_rd_match
from models import AIResponse, Citation, ConfidenceLabel

RAG_SYSTEM_PROMPT = """You are an AI customer support assistant for 智云科技 (Zhiyun Tech).

Below you MAY receive relevant knowledge base documents as context. Use them when available, but if the context is empty or irrelevant, answer the user's question using your own knowledge and mark it clearly.

Important safety rules:
- If the query involves: security incidents, known vulnerability details, customer credentials/keys/passwords, legal compliance, or unreleased product features — you MUST respond with a warning that this topic requires human escalation, and set confidence to 0.1.
- Otherwise, answer helpfully in Chinese.

Respond strictly in the following JSON format (no markdown code fences):

{{
  "answer": "Your answer in Chinese. Step-by-step format when applicable.",
  "citations": [
    {{"doc_title": "...", "doc_version": "...", "section": "...", "snippet": "..."}}
  ],
  "confidence": 0.0,
  "confidence_reason": "Brief explanation."
}}

Rules:
- If knowledge base context IS provided and relevant: use it, cite it, confidence >= 0.7.
- If context is partially relevant: use what you can, flag gaps, confidence 0.4-0.7.
- If context is empty or irrelevant: answer from your own knowledge, empty citations, confidence 0.3-0.5, and note "知识库未覆盖此问题，以下回答来自通用知识，请人工核实".
- If the query is dangerous (security/credentials/legal/unreleased): answer with a refusal, confidence 0.1.
- Citations: only cite documents actually provided in the context. If none provided, leave citations empty.
- If you see "[内部提示]" in the context: do NOT reference this in citations. It is only a signal for you to add a note at the end of your answer: "检测到相关内部技术资料，建议升级工单以获得更精准的支持。"
"""

RAG_USER_PROMPT = """## Conversation History (may be empty)
{history}

## Knowledge Base Context (may be empty)
{context}

## Current Query
{query}

Please generate your response following the JSON format specified in the system prompt. If conversation history is provided, your answer should be consistent with previous exchanges."""


def _build_history(history: list) -> str:
    if not history:
        return "(无历史对话)"
    parts = []
    for msg in history:
        role_label = "用户" if msg.get("role") == "user" else "AI助手"
        parts.append(f"[{role_label}]: {msg.get('content', '')}")
    return "\n".join(parts)


def _build_context(docs_with_scores: list, source: str = "D1") -> tuple[str, list[dict]]:
    context_parts = []
    citation_candidates = []
    for i, (doc, score) in enumerate(docs_with_scores):
        meta = doc.metadata
        block = (
            f"[{source} Doc {i+1}] Title: {meta.get('title', 'Unknown')}\n"
            f"Category: {meta.get('category', meta.get('entry_type', 'Unknown'))} | "
            f"Version: {meta.get('version', 'N/A')}\n"
            f"Content:\n{doc.page_content}\n"
        )
        context_parts.append(block)
        citation_candidates.append({
            "doc_title": meta.get("title", "Unknown"),
            "doc_version": meta.get("version", "N/A"),
            "similarity": score,
            "content": doc.page_content,
        })
    return "\n---\n".join(context_parts), citation_candidates


def _check_forbidden(query: str) -> Optional[str]:
    for pattern, category in FORBIDDEN_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return category
    return None


def _parse_llm_response(raw: str) -> Optional[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _compute_confidence_label(score: float) -> ConfidenceLabel:
    if score >= CONFIDENCE_GREEN:
        return ConfidenceLabel.GREEN
    elif score >= CONFIDENCE_YELLOW:
        return ConfidenceLabel.YELLOW
    else:
        return ConfidenceLabel.RED


def query_ai(query_text: str, ticket_id: Optional[int] = None, role: str = "cs",
             history: Optional[list] = None) -> AIResponse:
    """Main RAG pipeline with D1/D2 permission isolation.

    Args:
        query_text: The customer's query
        ticket_id: Associated ticket ID (optional — None for standalone queries)
        role: One of 'cs', 'rd', 'doc', 'manager' — controls D2 access
        history: List of prior turns [{"role": "user"|"assistant", "content": "..."}]
    """
    logger = logging.getLogger(__name__)
    log_id = str(uuid.uuid4())[:8]
    flags = []
    history = history or []
    logger.info("=== [Query %s] ticket=%s role=%s history_turns=%d ===", log_id, ticket_id, role, len(history))
    logger.info("[Query] raw_input=%s", query_text[:120])

    # Step 1: Desensitize
    clean_query, changes = desensitize(query_text)
    if changes > 0:
        logger.info("[Desensitize] removed %d sensitive fields", changes)

    # Step 2: Forbidden category check
    forbidden = _check_forbidden(clean_query)
    if forbidden:
        logger.warning("[Forbidden] category: %s", forbidden)
        flags.append(f"⚠️ 该问题涉及 {forbidden}，AI 应拒绝回答并建议升级。")

    # Step 3: Retrieve from D1 (always, full content)
    d1_docs = []
    try:
        d1_docs = retrieve_ai_knowledge(clean_query)
    except Exception as e:
        logger.error("[Retrieve D1] failed: %s", e)
        flags.append(f"知识库检索异常: {e}")

    logger.info("[Retrieve D1] %d docs | scores=%s", len(d1_docs), [round(s, 3) for _, s in d1_docs])

    # Step 4: D2 handling — depends on role
    d2_docs = []
    d2_match_found = False
    d2_hint = None

    if role in ("rd", "doc"):
        # RD and Doc can access full D2 content
        try:
            d2_docs = retrieve_rd_knowledge(clean_query)
            logger.info("[Retrieve D2] %d docs (full access for %s)", len(d2_docs), role)
        except Exception as e:
            logger.error("[Retrieve D2] failed: %s", e)
    else:
        # CS/Manager: presence check only (NO content)
        try:
            d2_match_found = check_rd_match(clean_query)
            if d2_match_found:
                logger.info("[Retrieve D2] match detected — restricting content from CS")
                d2_hint = "检测到相关内部技术资料，建议升级工单以获得更精准的支持。"
        except Exception as e:
            logger.error("[Retrieve D2 check] failed: %s", e)

    # Step 5: Build context from D1 (and D2 if permitted)
    context, citation_candidates = _build_context(d1_docs, source="D1")

    if d2_docs:
        d2_context, d2_citations = _build_context(d2_docs, source="D2")
        context = (context + "\n---\n" + d2_context) if context else d2_context
        citation_candidates.extend(d2_citations)

    if not d1_docs and not d2_docs:
        context = "(知识库中未找到相关文档，请根据你的通用知识回答，并标注为知识库未覆盖)"
        logger.info("[Retrieve] no KB docs — LLM will answer from own knowledge")
    elif d2_match_found and role in ("cs", "manager"):
        context += "\n\n[内部提示] 研发知识库中有相关资料但无权查看。请在回答末尾提醒用户升级工单。"

    # Step 6: LLM Generation
    logger.info("[LLM] calling model=%s context_len=%d flags=%d", LLM_MODEL, len(context), len(flags))
    llm = ChatOpenAI(
        model=LLM_MODEL,
        openai_api_key=DASHSCOPE_API_KEY,
        openai_api_base=BAILIAN_BASE_URL,
        temperature=0.1,
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", RAG_SYSTEM_PROMPT),
        ("user", RAG_USER_PROMPT),
    ])
    chain = prompt | llm | StrOutputParser()

    try:
        history_text = _build_history(history)
        raw_output = chain.invoke({"context": context, "query": clean_query, "history": history_text})
        logger.info("[LLM] raw_output preview=%s", raw_output[:200])
    except Exception as e:
        err_msg = str(e)
        logger.error("[LLM] call failed: %s", err_msg)
        return AIResponse(
            log_id=log_id, ticket_id=ticket_id or None, query_text=query_text,
            answer_text=f"AI 服务调用失败: {err_msg}",
            citations=[], confidence_score=0.0, confidence_label=ConfidenceLabel.RED,
            is_blocked=False, block_reason=None, escalation_required=True,
            d2_match_found=d2_match_found, d2_hint=d2_hint,
        )

    # Step 7: Parse structured output
    parsed = _parse_llm_response(raw_output)
    if parsed is None:
        logger.warning("[Parse] JSON parse failed — returning raw output")
        answer_text = raw_output[:2000]
        if flags:
            answer_text = "\n".join(flags) + "\n\n" + answer_text
        if d2_match_found and role in ("cs", "manager"):
            answer_text += "\n\n⚠️ 检测到相关内部技术资料，建议升级工单以获得更精准的支持。"
        return AIResponse(
            log_id=log_id, ticket_id=ticket_id or None, query_text=query_text,
            answer_text=answer_text,
            citations=[], confidence_score=0.3, confidence_label=ConfidenceLabel.YELLOW,
            is_blocked=False, block_reason="JSON 解析失败，已返回原始输出。请人工核查。",
            escalation_required=False, d2_match_found=d2_match_found, d2_hint=d2_hint,
        )

    answer = parsed.get("answer", "")
    llm_confidence = float(parsed.get("confidence", 0.5))
    raw_citations = parsed.get("citations", [])
    logger.info("[Parse] answer_len=%d llm_confidence=%.2f citations=%d",
                len(answer), llm_confidence, len(raw_citations))

    # Step 8: Citation validation
    citations = []
    for c in raw_citations:
        citations.append(Citation(
            doc_title=c.get("doc_title", "未知"),
            doc_version=c.get("doc_version", "N/A"),
            section=c.get("section", ""),
            snippet=c.get("snippet", ""),
        ))

    # Step 9: Confidence computation
    if citations and citation_candidates:
        n = min(len(citations), len(citation_candidates))
        avg_similarity = sum(c["similarity"] for c in citation_candidates[:n]) / n
        blended_confidence = round(avg_similarity * 0.4 + llm_confidence * 0.6, 2)
    else:
        avg_similarity = 0.0
        blended_confidence = round(llm_confidence * 0.8, 2)

    if not d1_docs and not d2_docs and blended_confidence > 0.5:
        blended_confidence = 0.5

    logger.info("[Confidence] retrieval_avg=%.3f llm_self=%.2f blended=%.2f → %s",
                avg_similarity, llm_confidence, blended_confidence,
                _compute_confidence_label(blended_confidence).value)
    label = _compute_confidence_label(blended_confidence)

    if flags:
        answer = "\n".join(flags) + "\n\n" + answer

    # Append D2 hint to answer for CS
    if d2_match_found and role in ("cs", "manager"):
        if "建议升级" not in answer:
            answer += "\n\n⚠️ 检测到相关内部技术资料，建议升级工单以获得更精准的支持。"

    escalation_required = label == ConfidenceLabel.RED or d2_match_found

    return AIResponse(
        log_id=log_id,
        ticket_id=ticket_id or None,
        query_text=query_text,
        answer_text=answer,
        citations=citations,
        confidence_score=blended_confidence,
        confidence_label=label,
        is_blocked=False,
        block_reason=None,
        escalation_required=escalation_required,
        d2_match_found=d2_match_found,
        d2_hint=d2_hint,
    )
