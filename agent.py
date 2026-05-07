"""Process 1 (AI处理) + Process 2 (知识沉淀): LangChain RAG pipeline.

Pipeline:
    query → desensitize → forbidden-check → retrieve → build-context →
    LLM generate (with citation) → validate citations → compute confidence →
    structured AIResponse
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
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
from knowledge_store import retrieve
from models import AIResponse, Citation, ConfidenceLabel

# --- Prompt template forces structured JSON ---
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
"""

RAG_USER_PROMPT = """## Knowledge Base Context (may be empty)
{context}

## Customer Query
{query}

Please generate your response following the JSON format specified in the system prompt."""


def _build_context(docs_with_scores: list) -> tuple[str, list[dict]]:
    """Build a text context block and raw citation candidates from retrieved docs."""
    context_parts = []
    citation_candidates = []
    for i, (doc, score) in enumerate(docs_with_scores):
        meta = doc.metadata
        block = (
            f"[Doc {i+1}] Title: {meta.get('title', 'Unknown')}\n"
            f"Source: {meta.get('source_type', 'Unknown')} | "
            f"Version: {meta.get('version', 'N/A')} | "
            f"Status: {meta.get('validity_status', '有效')}\n"
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
    """Check if the query matches any forbidden category (BR-02). Returns category name if blocked."""
    for pattern, category in FORBIDDEN_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return category
    return None


def _parse_llm_response(raw: str) -> Optional[dict]:
    """Parse LLM JSON output, handling common formatting issues."""
    raw = raw.strip()
    # Remove markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from the text
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


def query_ai(query_text: str, ticket_id: str) -> AIResponse:
    """Main RAG pipeline: process a customer support query through the AI system.

    Returns an AIResponse with answer, citations, confidence score/label,
    and flags for blocking/escalation.
    """
    logger = logging.getLogger(__name__)
    log_id = str(uuid.uuid4())[:8]
    flags = []  # collect warnings to prepend to the answer later
    logger.info("=== [Query %s] ticket=%s ===", log_id, ticket_id)
    logger.info("[Query] raw_input=%s", query_text[:120])

    # Step 1: Desensitize (Process 6)
    clean_query, changes = desensitize(query_text)
    if changes > 0:
        logger.info("[Desensitize] removed %d sensitive fields", changes)

    # Step 2: Forbidden category check (BR-02) — warn but don't block
    forbidden = _check_forbidden(clean_query)
    if forbidden:
        logger.warning("[Forbidden] category hit: %s — will ask LLM to refuse", forbidden)
        flags.append(f"⚠️ 该问题涉及 {forbidden}，AI 应拒绝回答并建议升级。")

    # Step 3: Retrieve from vector store (best-effort)
    docs_with_scores = []
    try:
        docs_with_scores = retrieve(clean_query)
    except Exception as e:
        err_msg = str(e)
        logger.error("[Retrieve] failed: %s — will proceed without KB context", err_msg)
        flags.append(f"知识库检索异常: {err_msg}")

    logger.info(
        "[Retrieve] got %d docs | scores=%s",
        len(docs_with_scores),
        [round(s, 3) for _, s in docs_with_scores],
    )
    for i, (doc, score) in enumerate(docs_with_scores):
        logger.info(
            "[Retrieve]   #%d title=%s score=%.3f",
            i + 1, doc.metadata.get("title", "?"), score,
        )

    if not docs_with_scores:
        logger.info("[Retrieve] no KB docs — LLM will answer from own knowledge")

    # Step 4: LLM Generation (always invoked)
    context, citation_candidates = _build_context(docs_with_scores)
    if not docs_with_scores:
        context = "(知识库中未找到相关文档，请根据你的通用知识回答，并标注为知识库未覆盖)"

    logger.info(
        "[LLM] calling model=%s base_url=%s context_len=%d flags=%d",
        LLM_MODEL, BAILIAN_BASE_URL, len(context), len(flags),
    )
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
        raw_output = chain.invoke({"context": context, "query": clean_query})
        logger.info("[LLM] raw_output preview=%s", raw_output[:200])
    except Exception as e:
        err_msg = str(e)
        logger.error("[LLM] call failed: %s", err_msg)
        return AIResponse(
            log_id=log_id, ticket_id=ticket_id, query_text=query_text,
            answer_text=f"AI 服务调用失败: {err_msg}",
            citations=[], confidence_score=0.0, confidence_label=ConfidenceLabel.RED,
            is_blocked=False, block_reason=None, escalation_required=True,
        )

    # Step 5: Parse structured output
    parsed = _parse_llm_response(raw_output)
    if parsed is None:
        logger.warning("[Parse] failed to parse JSON — returning raw output as plain answer")
        answer_text = raw_output[:2000]
        if flags:
            answer_text = "\n".join(flags) + "\n\n" + answer_text
        return AIResponse(
            log_id=log_id, ticket_id=ticket_id, query_text=query_text,
            answer_text=answer_text,
            citations=[], confidence_score=0.3, confidence_label=ConfidenceLabel.YELLOW,
            is_blocked=False, block_reason="JSON 解析失败，已返回原始输出。请人工核查。",
            escalation_required=False,
        )

    answer = parsed.get("answer", "")
    llm_confidence = float(parsed.get("confidence", 0.5))
    raw_citations = parsed.get("citations", [])
    logger.info(
        "[Parse] answer_len=%d | llm_confidence=%.2f | citation_count=%d",
        len(answer), llm_confidence, len(raw_citations),
    )

    # Step 6: Citation validation — soft, not a hard block
    citations = []
    for c in raw_citations:
        citations.append(Citation(
            doc_title=c.get("doc_title", "未知"),
            doc_version=c.get("doc_version", "N/A"),
            section=c.get("section", ""),
            snippet=c.get("snippet", ""),
        ))

    if not citations:
        logger.info("[Citation] no citations — answer from LLM general knowledge")

    # Step 7: Confidence computation
    if citations and citation_candidates:
        avg_similarity = (
            sum(c["similarity"] for c in citation_candidates[: len(citations)]) / len(citations)
        )
        blended_confidence = round(avg_similarity * 0.4 + llm_confidence * 0.6, 2)
    else:
        # No KB backing — use LLM's own (conservative) estimate
        avg_similarity = 0.0
        blended_confidence = round(llm_confidence * 0.8, 2)

    # Cap confidence when no KB docs were retrieved
    if not docs_with_scores and blended_confidence > 0.5:
        blended_confidence = 0.5

    logger.info(
        "[Confidence] retrieval_avg=%.3f | llm_self=%.2f | blended=%.2f → %s",
        avg_similarity, llm_confidence, blended_confidence,
        _compute_confidence_label(blended_confidence).value,
    )
    label = _compute_confidence_label(blended_confidence)

    # Prepend flags/warnings to the answer
    if flags:
        answer = "\n".join(flags) + "\n\n" + answer

    escalation_required = label == ConfidenceLabel.RED

    return AIResponse(
        log_id=log_id,
        ticket_id=ticket_id,
        query_text=query_text,
        answer_text=answer,
        citations=citations,
        confidence_score=blended_confidence,
        confidence_label=label,
        is_blocked=False,
        block_reason=None,
        escalation_required=escalation_required,
    )
