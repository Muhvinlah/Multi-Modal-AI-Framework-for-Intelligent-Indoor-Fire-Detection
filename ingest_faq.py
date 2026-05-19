# ==============================================================================
# Tujuan       : Ingest FAQ markdown files ke ChromaDB + BM25
#                Format: setiap section dengan heading "## Q: ..." jadi 1 chunk
# Usage        : python ingest_faq.py
# Catatan      : BM25 index di-MERGE dengan index PDF yang sudah ada (kalau ada),
#                supaya hybrid search tetap meng-cover korpus PDF + FAQ.
#                Jadi urutan jalankan: ingest_pdf.py dulu, baru ingest_faq.py.
# ==============================================================================

import os
import re
import glob
import pickle
import chromadb
from sentence_transformers import SentenceTransformer

from app.config import (
    CHROMA_DB_PATH, CHROMA_COLLECTION,
    EMBEDDING_MODEL_NAME, BM25_INDEX_PATH,
)
from app.rag_engine import build_bm25_index

FAQ_DIR = "docs/faq"
_IS_E5 = "e5" in EMBEDDING_MODEL_NAME.lower()


def parse_faq_markdown(filepath: str) -> list:
    """Parse FAQ markdown, return list of {q, a, combined}."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Split by Q: heading
    sections = re.split(r"\n##\s+Q[:.]?\s*", content)[1:]
    chunks = []
    for sec in sections:
        # Split Q dan A — asumsi format "pertanyaan\n\nanswer..."
        parts = sec.strip().split("\n", 1)
        if len(parts) < 2:
            continue
        question = parts[0].strip()
        answer = parts[1].strip()
        chunks.append({
            "q": question,
            "a": answer,
            "combined": f"Pertanyaan: {question}\nJawaban: {answer}",
        })
    return chunks


def _load_existing_bm25_corpus():
    """Ambil docs + metadata dari BM25 index existing (PDF) biar bisa di-merge."""
    if not os.path.exists(BM25_INDEX_PATH):
        return [], []
    try:
        with open(BM25_INDEX_PATH, "rb") as f:
            data = pickle.load(f)
        return data.get("docs", []), data.get("metadata", [])
    except Exception as e:
        print(f"[FAQ] Gagal baca BM25 existing ({e}) — index baru hanya FAQ")
        return [], []


def main():
    if not os.path.exists(FAQ_DIR):
        print(f"❌ Folder {FAQ_DIR} belum ada. Bikin dulu + isi markdown FAQ.")
        return

    md_files = glob.glob(os.path.join(FAQ_DIR, "*.md"))
    if not md_files:
        print(f"❌ Nggak ada file .md di {FAQ_DIR}")
        return

    all_chunks = []
    all_metadata = []
    for fp in md_files:
        chunks = parse_faq_markdown(fp)
        for c in chunks:
            all_chunks.append(c["combined"])
            all_metadata.append({
                "source": os.path.basename(fp),
                "type": "faq",
                "question": c["q"][:200],
            })
        print(f"[FAQ] {fp}: {len(chunks)} Q&A pairs")

    if not all_chunks:
        print("❌ Nggak ada chunk yang berhasil di-parse")
        return

    # Embed + add to ChromaDB
    print(f"\n[FAQ] Encoding {len(all_chunks)} chunks...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    docs_prefixed = [f"passage: {d}" for d in all_chunks] if _IS_E5 else all_chunks
    embeddings = model.encode(docs_prefixed, show_progress_bar=True).tolist()

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    try:
        collection = client.get_collection(name=CHROMA_COLLECTION)
    except Exception:
        collection = client.create_collection(name=CHROMA_COLLECTION)

    ids = [f"faq_{i}" for i in range(len(all_chunks))]
    collection.add(
        ids=ids,
        documents=all_chunks,
        embeddings=embeddings,
        metadatas=all_metadata,
    )
    print(f"[FAQ] ✅ Added {len(all_chunks)} chunks to ChromaDB")

    # Merge dengan BM25 index PDF yang sudah ada (kalau ada), baru rebuild
    pdf_docs, pdf_meta = _load_existing_bm25_corpus()
    # Hindari duplikat FAQ kalau ingest_faq dijalankan dua kali
    pdf_keep = [
        (d, m) for d, m in zip(pdf_docs, pdf_meta or [{}] * len(pdf_docs))
        if (m or {}).get("type") != "faq"
    ]
    merged_docs = [d for d, _ in pdf_keep] + all_chunks
    merged_meta = [m for _, m in pdf_keep] + all_metadata
    build_bm25_index(merged_docs, merged_meta)
    print(f"[FAQ] ✅ BM25 index rebuilt: {len(merged_docs)} docs total "
          f"({len(merged_docs) - len(all_chunks)} PDF + {len(all_chunks)} FAQ)")


if __name__ == "__main__":
    main()
