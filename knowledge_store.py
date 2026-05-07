"""ChromaDB vector store for knowledge base documents (D1 AI知识库, D2 研发知识库)."""

from __future__ import annotations

import os
import logging
from typing import Optional, List

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
)
from seed_data import KNOWLEDGE_ENTRIES

_vector_store: Optional[Chroma] = None


class BailianEmbeddings(Embeddings):
    """Custom embeddings that call Alibaba Bailian (DashScope) native embedding API.

    Uses the native endpoint (not OpenAI-compatible mode) because the compatible
    embedding endpoint rejects the chunked-input format that langchain_openai sends.
    """

    def __init__(self, api_key: str, model: str = "text-embedding-v2"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        logger = logging.getLogger(__name__)
        preview = texts[0][:80].replace("\n", " ") if texts else "(empty)"
        logger.info(
            "[Embedding] model=%s | batch_size=%d | preview=%s...",
            self.model, len(texts), preview,
        )
        resp = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": {"texts": texts},
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if "output" not in data or "embeddings" not in data["output"]:
            raise RuntimeError(f"Unexpected embedding response: {data}")
        embeddings = [e["embedding"] for e in data["output"]["embeddings"]]
        logger.info(
            "[Embedding] done | dims=%d | count=%d",
            len(embeddings[0]) if embeddings else 0, len(embeddings),
        )
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


def _get_embeddings() -> BailianEmbeddings:
    return BailianEmbeddings(api_key=DASHSCOPE_API_KEY, model=EMBEDDING_MODEL)


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        embeddings = _get_embeddings()
        if os.path.exists(CHROMA_PERSIST_DIR) and os.listdir(CHROMA_PERSIST_DIR):
            _vector_store = Chroma(
                persist_directory=CHROMA_PERSIST_DIR,
                embedding_function=embeddings,
                collection_name="knowledge_base",
            )
        else:
            _vector_store = _ingest_seed_data(embeddings)
    return _vector_store


def _ingest_seed_data(embeddings: BailianEmbeddings) -> Chroma:
    docs = []
    for entry in KNOWLEDGE_ENTRIES:
        metadata = {
            "title": entry["title"],
            "source_type": entry["source_type"],
            "version": entry["version"],
            "doc_id": entry.get("id", entry["title"]),
        }
        doc = LangchainDoc(page_content=entry["content"], metadata=metadata)
        docs.append(doc)

    store = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=CHROMA_PERSIST_DIR,
        collection_name="knowledge_base",
    )
    return store


def reset_vector_store():
    """Re-ingest seed data from scratch."""
    global _vector_store
    import shutil

    if os.path.exists(CHROMA_PERSIST_DIR):
        shutil.rmtree(CHROMA_PERSIST_DIR)
    _vector_store = None
    return get_vector_store()


def retrieve(
    query: str, top_k: int = RETRIEVAL_TOP_K
) -> list[tuple[LangchainDoc, float]]:
    """Retrieve relevant documents with similarity scores."""
    store = get_vector_store()
    results = store.similarity_search_with_relevance_scores(query, k=top_k)
    return [(doc, score) for doc, score in results if score >= SIMILARITY_THRESHOLD]


def retrieve_raw(query: str, top_k: int = RETRIEVAL_TOP_K) -> list:
    """Retrieve raw results for debugging without score filtering."""
    store = get_vector_store()
    return store.similarity_search_with_relevance_scores(query, k=top_k)


# --- Process 3: GitLab Release Notes 模拟同步 ---
def sync_from_gitlab(release_note: dict) -> str:
    """Simulate ingesting a new GitLab release note into the vector store."""
    store = get_vector_store()
    metadata = {
        "title": release_note.get("title", "Untitled Release Note"),
        "source_type": "GitLab",
        "version": release_note.get("version", "1.0"),
        "doc_id": release_note.get("id", release_note.get("title", "untitled")),
    }
    doc = LangchainDoc(page_content=release_note["content"], metadata=metadata)
    doc_ids = store.add_documents([doc])
    return doc_ids[0] if doc_ids else ""


def mark_doc_expired(doc_title: str) -> bool:
    """Mark a document as expired in the knowledge base."""
    store = get_vector_store()
    results = store.get(where={"title": doc_title})
    if not results["ids"]:
        return False
    for doc_id, metadata in zip(results["ids"], results["metadatas"]):
        metadata["validity_status"] = "过期"
        store._collection.update(ids=[doc_id], metadatas=[metadata])
    return True
