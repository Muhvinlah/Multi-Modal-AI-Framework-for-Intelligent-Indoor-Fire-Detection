# chatbot_service/rag_engine.py
# ==============================================================================
# Tujuan : Hybrid RAG (BM25 + Dense + Re-rank) self-contained di chatbot_service
#          Ported dari app/rag_engine.py — tanpa import dari app/
# Main Functions: load_rag_engine(), retrieve(query, sensor_context)
# Fail-soft: kalau load gagal, log warning, service tetap jalan tanpa RAG
# ==============================================================================

import os
import re
import pickle
from typing import List, Dict
import numpy as np

from chatbot_service.config import cfg

# === State global ===
_embedding_model = None
_reranker = None
_collection = None
_bm25 = None
_bm25_docs: List[str] = []
_bm25_metadata: List[dict] = []
def _simple_tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def load_rag_engine():
    """Load semua komponen RAG saat startup. Idempotent. Fail-soft per komponen."""
    global _embedding_model, _reranker, _collection, _bm25, _bm25_docs, _bm25_metadata

    # 1. Embedding model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(cfg.embedding_model_name)
        print(f"[RAG] Embedding loaded: {cfg.embedding_model_name}")
    except Exception as e:
        print(f"[RAG] Embedding gagal: {e} — dense search disabled")

    # 2. Cross-encoder reranker (opsional)
    if cfg.reranker_model_name:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(cfg.reranker_model_name, max_length=512)
            print(f"[RAG] Reranker loaded: {cfg.reranker_model_name}")
        except Exception as e:
            print(f"[RAG] Reranker gagal: {e} — fallback ke dense-only")
    else:
        print("[RAG] Reranker disabled (RERANKER_MODEL_NAME kosong)")

    # 3. ChromaDB
    try:
        import chromadb
        client = chromadb.PersistentClient(path=cfg.chromadb_path)
        _collection = client.get_collection(name=cfg.chromadb_collection)
        print(f"[RAG] ChromaDB loaded: {cfg.chromadb_collection} ({_collection.count()} docs)")
    except Exception as e:
        print(f"[RAG] ChromaDB belum ada atau gagal: {e} — vector search disabled")

    # 4. BM25 index
    if os.path.exists(cfg.bm25_index_path):
        try:
            with open(cfg.bm25_index_path, "rb") as f:
                data = pickle.load(f)
            _bm25 = data["bm25"]
            _bm25_docs = data["docs"]
            _bm25_metadata = data.get("metadata", [{}] * len(_bm25_docs))
            print(f"[RAG] BM25 index loaded: {len(_bm25_docs)} docs")
        except Exception as e:
            print(f"[RAG] BM25 load error: {e}")
    else:
        print(f"[RAG] BM25 index belum ada ({cfg.bm25_index_path}) — jalankan ingest_pdf.py")


def build_bm25_index(docs: List[str], metadata: List[dict] = None):
    """Bangun BM25 index dari list docs dan simpan ke disk."""
    from rank_bm25 import BM25Okapi

    tokenized = [_simple_tokenize(d) for d in docs]
    bm25 = BM25Okapi(tokenized)

    index_dir = os.path.dirname(cfg.bm25_index_path)
    if index_dir:
        os.makedirs(index_dir, exist_ok=True)
    with open(cfg.bm25_index_path, "wb") as f:
        pickle.dump({
            "bm25": bm25,
            "docs": docs,
            "metadata": metadata or [{}] * len(docs),
        }, f)
    print(f"[RAG] BM25 index saved: {len(docs)} docs -> {cfg.bm25_index_path}")


def _dense_search(query: str, top_k: int) -> List[Dict]:
    if not _collection or not _embedding_model:
        return []
    try:
        q_prefixed = (
            f"query: {query}"
            if "e5" in cfg.embedding_model_name.lower()
            else query
        )
        q_emb = _embedding_model.encode([q_prefixed]).tolist()
        results = _collection.query(query_embeddings=q_emb, n_results=top_k)
        docs = results["documents"][0] if results["documents"] else []
        distances = results.get("distances", [[]])[0]
        return [
            {"doc": d, "score": 1.0 / (1.0 + dist), "source": "dense"}
            for d, dist in zip(docs, distances)
        ]
    except Exception as e:
        print(f"[RAG] Dense search error: {e}")
        return []


def _bm25_search(query: str, top_k: int) -> List[Dict]:
    if not _bm25 or not _bm25_docs:
        return []
    try:
        tokenized_q = _simple_tokenize(query)
        scores = _bm25.get_scores(tokenized_q)
        if scores.max() > 0:
            scores = scores / scores.max()
        top_idx = np.argsort(scores)[-top_k:][::-1]
        return [
            {"doc": _bm25_docs[i], "score": float(scores[i]), "source": "bm25"}
            for i in top_idx if scores[i] > 0
        ]
    except Exception as e:
        print(f"[RAG] BM25 search error: {e}")
        return []


def _hybrid_merge(dense_results: List[Dict], bm25_results: List[Dict]) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for r in dense_results:
        key = r["doc"][:100]
        merged[key] = {
            "doc": r["doc"],
            "score": r["score"] * cfg.rag_dense_weight,
            "sources": ["dense"],
        }
    for r in bm25_results:
        key = r["doc"][:100]
        if key in merged:
            merged[key]["score"] += r["score"] * cfg.rag_bm25_weight
            merged[key]["sources"].append("bm25")
        else:
            merged[key] = {
                "doc": r["doc"],
                "score": r["score"] * cfg.rag_bm25_weight,
                "sources": ["bm25"],
            }
    return sorted(merged.values(), key=lambda x: -x["score"])


def _rerank(query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
    if not _reranker or not candidates:
        return candidates[:top_k]
    try:
        pairs = [(query, c["doc"]) for c in candidates]
        rerank_scores = _reranker.predict(pairs)
        for c, s in zip(candidates, rerank_scores):
            c["rerank_score"] = float(s)
        return sorted(candidates, key=lambda x: -x["rerank_score"])[:top_k]
    except Exception as e:
        print(f"[RAG] Rerank error: {e}")
        return candidates[:top_k]


def _expand_query(query: str, sensor_context=None) -> str:
    """Expand query pendek dengan konteks sensor agar retrieval lebih relevan."""
    q = query.strip()
    if len(q.split()) >= 5:
        return q

    extras = []
    if sensor_context:
        if getattr(sensor_context, "flame_detected", False):
            extras.append("api terdeteksi sensor IR")
        temp = getattr(sensor_context, "temperature", 0)
        if temp > 45:
            extras.append(f"suhu tinggi {temp}C")
        mq2 = getattr(sensor_context, "mq2", 0)
        if mq2 > 300:
            extras.append("asap atau gas terdeteksi")
    if extras:
        return f"{q} (konteks: {', '.join(extras)})"
    return q


def retrieve(query: str, sensor_context=None) -> Dict:
    """Hybrid search + rerank.

    Returns:
        {"context": str, "chunks": list, "method": str}
    """
    expanded = _expand_query(query, sensor_context)

    dense_results = _dense_search(expanded, cfg.rag_top_k_retrieve)
    bm25_results = _bm25_search(expanded, cfg.rag_top_k_retrieve)

    if not dense_results and not bm25_results:
        return {"context": "", "chunks": [], "method": "no_results"}

    merged = _hybrid_merge(dense_results, bm25_results)
    method = "dense_only" if not bm25_results else "hybrid"

    if _reranker:
        top_final = _rerank(query, merged[:cfg.rag_top_k_retrieve], cfg.rag_top_k_final)
        method += "_rerank"
    else:
        top_final = merged[:cfg.rag_top_k_final]

    context_parts = [c["doc"] for c in top_final]
    full_context = "\n\n---\n\n".join(context_parts)[: cfg.rag_context_max_chars]

    return {"context": full_context, "chunks": top_final, "method": method}
