"""ChromaDB dual-collection vector store.
Data sources:
  - D1 (ai_knowledge): wiki_pages WHERE knowledge_type='d1' AND status='approved'
  - D2 (rd_knowledge): wiki_pages WHERE knowledge_type='d2'
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import List, Optional

import requests
from langchain_chroma import Chroma
from langchain_core.documents import Document as LangchainDoc
from langchain_core.embeddings import Embeddings

from config import (
    EMBEDDING_MODEL,
    CHROMA_PERSIST_DIR,
    RETRIEVAL_TOP_K,
    SIMILARITY_THRESHOLD,
    DASHSCOPE_API_KEY,
    AI_COLLECTION,
    RD_COLLECTION,
)

_ai_store: Optional[Chroma] = None
_rd_store: Optional[Chroma] = None


class BailianEmbeddings(Embeddings):
    """Custom embeddings calling Alibaba Bailian native embedding API."""

    def __init__(self, api_key: str, model: str = "text-embedding-v2"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        logger = logging.getLogger(__name__)
        preview = texts[0][:80].replace("\n", " ") if texts else "(empty)"
        logger.info("[Embedding] model=%s batch=%d preview=%s...", self.model, len(texts), preview)
        resp = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": {"texts": texts}},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if "output" not in data or "embeddings" not in data["output"]:
            raise RuntimeError(f"Unexpected embedding response: {data}")
        embeddings = [e["embedding"] for e in data["output"]["embeddings"]]
        logger.info("[Embedding] done dims=%d count=%d", len(embeddings[0]) if embeddings else 0, len(embeddings))
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


def _get_embeddings() -> BailianEmbeddings:
    return BailianEmbeddings(api_key=DASHSCOPE_API_KEY, model=EMBEDDING_MODEL)


# --- D1: AI Knowledge Store (from wiki_pages knowledge_type='d1' status='approved') ---

def get_ai_vector_store() -> Chroma:
    global _ai_store
    if _ai_store is None:
        embeddings = _get_embeddings()
        coll_dir = os.path.join(CHROMA_PERSIST_DIR, AI_COLLECTION)
        if os.path.exists(coll_dir) and os.listdir(coll_dir):
            _ai_store = Chroma(
                persist_directory=CHROMA_PERSIST_DIR,
                embedding_function=embeddings,
                collection_name=AI_COLLECTION,
            )
        else:
            _ai_store = _ingest_ai_from_db(embeddings)
    return _ai_store


def _ingest_ai_from_db(embeddings: BailianEmbeddings) -> Chroma:
    from database import list_approved_d1_pages
    pages = list_approved_d1_pages()
    docs = []
    for entry in pages:
        metadata = {
            "title": entry["title"],
            "slug": entry.get("slug", ""),
            "category": entry.get("category", ""),
            "keywords": entry.get("keywords", ""),
            "wiki_page_id": entry["id"],
        }
        docs.append(LangchainDoc(page_content=entry["content"], metadata=metadata))
    if not docs:
        docs.append(LangchainDoc(page_content="(empty)", metadata={"title": "placeholder"}))
    return Chroma.from_documents(
        documents=docs, embedding=embeddings,
        persist_directory=CHROMA_PERSIST_DIR, collection_name=AI_COLLECTION,
    )


def add_to_ai_knowledge(title: str, content: str, category: str = "", keywords: str = "",
                        slug: str = "", wiki_page_id: int = 0) -> str:
    store = get_ai_vector_store()
    doc = LangchainDoc(
        page_content=content,
        metadata={"title": title, "slug": slug, "category": category, "keywords": keywords,
                   "wiki_page_id": wiki_page_id},
    )
    ids = store.add_documents([doc])
    return ids[0] if ids else ""


def retrieve_ai_knowledge(query: str, top_k: int = RETRIEVAL_TOP_K) -> list[tuple[LangchainDoc, float]]:
    store = get_ai_vector_store()
    results = store.similarity_search_with_relevance_scores(query, k=top_k)
    return [(doc, score) for doc, score in results if score >= SIMILARITY_THRESHOLD]


# --- D2: R&D Knowledge Store (from wiki_pages knowledge_type='d2') ---

def get_rd_vector_store() -> Chroma:
    global _rd_store
    if _rd_store is None:
        embeddings = _get_embeddings()
        coll_dir = os.path.join(CHROMA_PERSIST_DIR, RD_COLLECTION)
        if os.path.exists(coll_dir) and os.listdir(coll_dir):
            _rd_store = Chroma(
                persist_directory=CHROMA_PERSIST_DIR,
                embedding_function=embeddings,
                collection_name=RD_COLLECTION,
            )
        else:
            _rd_store = _ingest_rd_from_db(embeddings)
    return _rd_store


def _ingest_rd_from_db(embeddings: BailianEmbeddings) -> Chroma:
    from database import list_d2_pages
    pages = list_d2_pages()
    docs = []
    for entry in pages:
        metadata = {
            "title": entry["title"],
            "slug": entry.get("slug", ""),
            "version": entry.get("version", ""),
            "entry_type": entry.get("entry_type", ""),
            "keywords": entry.get("keywords", ""),
            "wiki_page_id": entry["id"],
        }
        docs.append(LangchainDoc(page_content=entry["content"], metadata=metadata))
    if not docs:
        docs.append(LangchainDoc(page_content="(empty)", metadata={"title": "placeholder"}))
    return Chroma.from_documents(
        documents=docs, embedding=embeddings,
        persist_directory=CHROMA_PERSIST_DIR, collection_name=RD_COLLECTION,
    )


def add_to_rd_knowledge(title: str, content: str, entry_type: str, version: str = "",
                        keywords: str = "", source_ticket_id: Optional[int] = None,
                        release_note: Optional[str] = None, slug: str = "", wiki_page_id: int = 0) -> str:
    store = get_rd_vector_store()
    metadata = {
        "title": title, "slug": slug, "entry_type": entry_type, "version": version, "keywords": keywords,
        "wiki_page_id": wiki_page_id,
    }
    if source_ticket_id:
        metadata["source_ticket_id"] = source_ticket_id
    if release_note:
        metadata["release_note"] = release_note
    doc = LangchainDoc(page_content=content, metadata=metadata)
    ids = store.add_documents([doc])
    return ids[0] if ids else ""


def retrieve_rd_knowledge(query: str, top_k: int = RETRIEVAL_TOP_K) -> list[tuple[LangchainDoc, float]]:
    store = get_rd_vector_store()
    results = store.similarity_search_with_relevance_scores(query, k=top_k)
    return [(doc, score) for doc, score in results if score >= SIMILARITY_THRESHOLD]


def check_rd_match(query: str, top_k: int = 3) -> bool:
    results = retrieve_rd_knowledge(query, top_k)
    return len(results) > 0


# --- Reset ---

def reset_vector_stores():
    global _ai_store, _rd_store
    _ai_store = None
    _rd_store = None
    if os.path.exists(CHROMA_PERSIST_DIR):
        shutil.rmtree(CHROMA_PERSIST_DIR)
    get_ai_vector_store()
    get_rd_vector_store()
