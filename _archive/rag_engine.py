# ==============================================================================
# Tujuan       : Hybrid RAG (BM25 + Dense + Re-rank) untuk chatbot K3
# Caller       : app.chatbot
# Dependensi   : rank_bm25, sentence_transformers, chromadb, nltk
# Main Functions: build_bm25_index(), retrieve(), load_rag_engine()
# Side Effects : Load reranker (~568MB), BM25 index (~few MB)
# ==============================================================================

import os
import re
import pickle
import threading
from typing import List, Dict
import numpy as np

from app.config import (
    CHROMA_DB_PATH, CHROMA_COLLECTION,
    EMBEDDING_MODEL_NAME, RERANKER_MODEL_NAME,
    RAG_BM25_WEIGHT, RAG_DENSE_WEIGHT,
    RAG_TOP_K_RETRIEVE, RAG_TOP_K_FINAL,
    RAG_CONTEXT_MAX_CHARS, BM25_INDEX_PATH,
)

# === State global ===
_embedding_model = None
_reranker = None
_collection = None
_bm25 = None
_bm25_docs: List[str] = []     # raw docs untuk lookup
_bm25_metadata: List[dict] = []
_lock = threading.Lock()


def _simple_tokenize(text: str) -> List[str]:
    """Tokenizer ringan untuk BM25 — lowercase + alphanumeric."""
    return re.findall(r"\b\w+\b", text.lower())


def load_rag_engine():
    """Load semua komponen RAG saat startup. Idempotent."""
    global _embedding_model, _reranker, _collection, _bm25, _bm25_docs, _bm25_metadata

    # 1. Embedding model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print(f"[RAG] Embedding loaded: {EMBEDDING_MODEL_NAME}")
    except Exception as e:
        print(f"[RAG] Embedding gagal: {e}")

    # 2. Cross-encoder reranker
    if RERANKER_MODEL_NAME:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(RERANKER_MODEL_NAME, max_length=512)
            print(f"[RAG] Reranker loaded: {RERANKER_MODEL_NAME}")
        except Exception as e:
            print(f"[RAG] Reranker gagal: {e} — fallback ke dense-only")
    else:
        print("[RAG] Reranker disabled (RERANKER_MODEL_NAME kosong)")

    # 3. ChromaDB
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _collection = client.get_collection(name=CHROMA_COLLECTION)
        print(f"[RAG] ChromaDB loaded: {CHROMA_COLLECTION} ({_collection.count()} docs)")
    except Exception as e:
        print(f"[RAG] ChromaDB belum ada: {e}")

    # 4. BM25 index
    if os.path.exists(BM25_INDEX_PATH):
        try:
            with open(BM25_INDEX_PATH, "rb") as f:
                data = pickle.load(f)
            _bm25 = data["bm25"]
            _bm25_docs = data["docs"]
            _bm25_metadata = data.get("metadata", [{}] * len(_bm25_docs))
            print(f"[RAG] BM25 index loaded: {len(_bm25_docs)} docs")
        except Exception as e:
            print(f"[RAG] BM25 load error: {e}")
    else:
        print("[RAG] BM25 index belum ada — jalankan ingest_pdf.py untuk build")


def build_bm25_index(docs: List[str], metadata: List[dict] = None):
    """Bangun BM25 index dari list docs, simpan ke disk. Dipanggil dari ingest_pdf.py."""
    from rank_bm25 import BM25Okapi

    tokenized = [_simple_tokenize(d) for d in docs]
    bm25 = BM25Okapi(tokenized)

    os.makedirs(os.path.dirname(BM25_INDEX_PATH), exist_ok=True)
    with open(BM25_INDEX_PATH, "wb") as f:
        pickle.dump({
            "bm25": bm25,
            "docs": docs,
            "metadata": metadata or [{}] * len(docs),
        }, f)
    print(f"[RAG] BM25 index saved: {len(docs)} docs → {BM25_INDEX_PATH}")


def _dense_search(query: str, top_k: int) -> List[Dict]:
    """Dense retrieval via ChromaDB. Return list of {doc, score, source}."""
    if not _collection or not _embedding_model:
        return []
    try:
        # E5 model butuh prefix "query:" untuk pertanyaan
        q_prefixed = f"query: {query}" if "e5" in EMBEDDING_MODEL_NAME.lower() else query
        q_emb = _embedding_model.encode([q_prefixed]).tolist()
        results = _collection.query(query_embeddings=q_emb, n_results=top_k)
        docs = results["documents"][0] if results["documents"] else []
        # ChromaDB distance → similarity score (smaller distance = more similar)
        distances = results.get("distances", [[]])[0]
        return [
            {
                "doc": d,
                "score": 1.0 / (1.0 + dist),   # normalize 0-1
                "source": "dense",
            }
            for d, dist in zip(docs, distances)
        ]
    except Exception as e:
        print(f"[RAG] Dense search error: {e}")
        return []


def _bm25_search(query: str, top_k: int) -> List[Dict]:
    """BM25 keyword search. Return list of {doc, score, source}."""
    if not _bm25 or not _bm25_docs:
        return []
    try:
        tokenized_q = _simple_tokenize(query)
        scores = _bm25.get_scores(tokenized_q)
        # Normalize scores ke 0-1 via max
        if scores.max() > 0:
            scores = scores / scores.max()
        top_idx = np.argsort(scores)[-top_k:][::-1]
        return [
            {
                "doc": _bm25_docs[i],
                "score": float(scores[i]),
                "source": "bm25",
            }
            for i in top_idx if scores[i] > 0
        ]
    except Exception as e:
        print(f"[RAG] BM25 search error: {e}")
        return []


def _hybrid_merge(dense_results: List[Dict], bm25_results: List[Dict]) -> List[Dict]:
    """Gabungkan hasil dense + BM25 dengan weighted score. Dedupe by doc content."""
    merged = {}
    for r in dense_results:
        key = r["doc"][:100]   # first 100 chars sebagai key (cukup unik)
        merged[key] = {
            "doc": r["doc"],
            "score": r["score"] * RAG_DENSE_WEIGHT,
            "sources": ["dense"],
        }
    for r in bm25_results:
        key = r["doc"][:100]
        if key in merged:
            merged[key]["score"] += r["score"] * RAG_BM25_WEIGHT
            merged[key]["sources"].append("bm25")
        else:
            merged[key] = {
                "doc": r["doc"],
                "score": r["score"] * RAG_BM25_WEIGHT,
                "sources": ["bm25"],
            }
    return sorted(merged.values(), key=lambda x: -x["score"])


def _rerank(query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
    """Re-rank kandidat pake cross-encoder. Jauh lebih akurat dari embedding similarity."""
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
    """Expand query pendek dengan konteks sensor biar retrieval lebih nyambung."""
    q = query.strip()
    if len(q.split()) >= 5:
        return q   # query udah cukup panjang

    extras = []
    if sensor_context:
        if sensor_context.detected_class and sensor_context.detected_class != "Clean":
            extras.append(f"deteksi {sensor_context.detected_class}")
        if sensor_context.status and sensor_context.status.lower() == "bahaya":
            extras.append("kondisi bahaya kebakaran")
    if extras:
        return f"{q} (konteks: {', '.join(extras)})"
    return q


def retrieve(query: str, sensor_context=None) -> Dict:
    """Main entry point: hybrid search + rerank → return context string + metadata.

    Returns:
        {
            "context": str,           # joined text untuk inject ke LLM prompt
            "chunks": List[Dict],     # raw chunks dengan metadata (debug)
            "method": str,            # "hybrid_rerank" / "dense_only" / "fallback"
        }
    """
    expanded = _expand_query(query, sensor_context)

    # 1. Parallel-ish retrieval (sequential aja, dense+bm25 cepet)
    dense_results = _dense_search(expanded, RAG_TOP_K_RETRIEVE)
    bm25_results = _bm25_search(expanded, RAG_TOP_K_RETRIEVE)

    if not dense_results and not bm25_results:
        return {"context": "", "chunks": [], "method": "no_results"}

    # 2. Hybrid merge
    merged = _hybrid_merge(dense_results, bm25_results)

    # 3. Rerank top kandidat
    method = "dense_only" if not bm25_results else "hybrid"
    if _reranker:
        top_final = _rerank(query, merged[:RAG_TOP_K_RETRIEVE], RAG_TOP_K_FINAL)
        method += "_rerank"
    else:
        top_final = merged[:RAG_TOP_K_FINAL]

    # 4. Build context string
    context_parts = [c["doc"] for c in top_final]
    full_context = "\n\n---\n\n".join(context_parts)[:RAG_CONTEXT_MAX_CHARS]

    return {
        "context": full_context,
        "chunks": top_final,
        "method": method,
    }
