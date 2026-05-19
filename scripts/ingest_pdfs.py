# ==============================================================================
# Tujuan       : Ingest PDF K3 ke ChromaDB pakai LangChain
#                Jalankan: python scripts/ingest_pdfs.py
# Output       : Update ChromaDB collection 'k3_knowledge' di ./chroma_db_native
# Dependensi   : langchain-community, langchain-text-splitters, pypdf, chromadb
# ==============================================================================

import os
import glob
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from sentence_transformers import SentenceTransformer

PDF_DIR = "knowledge_base/k3_pdfs"      # taruh PDF lo di sini
CHROMA_DB_PATH = "./chroma_db_native"   # sama dgn app/config.py
CHROMA_COLLECTION = "k3_knowledge"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 80


def main():
    os.makedirs(PDF_DIR, exist_ok=True)
    pdfs = glob.glob(f"{PDF_DIR}/*.pdf")
    if not pdfs:
        print(f"❌ Tidak ada PDF di {PDF_DIR}/")
        return

    print(f"📚 Found {len(pdfs)} PDF(s)")

    # 1. Load + split pakai LangChain
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " "],
    )
    all_chunks = []
    for pdf in pdfs:
        print(f"  → Loading {pdf}")
        docs = PyPDFLoader(pdf).load()
        chunks = splitter.split_documents(docs)
        for c in chunks:
            c.metadata["source"] = os.path.basename(pdf)
        all_chunks.extend(chunks)
    print(f"📄 Total chunks: {len(all_chunks)}")

    # 2. Embed
    print("🔡 Encoding embeddings...")
    embedder = SentenceTransformer(EMBEDDING_MODEL)
    texts = [c.page_content for c in all_chunks]
    embeddings = embedder.encode(texts, show_progress_bar=True).tolist()

    # 3. Push ke ChromaDB (collection yang dipakai chatbot.py)
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    try:
        client.delete_collection(CHROMA_COLLECTION)  # fresh rebuild
    except Exception:
        pass
    collection = client.create_collection(name=CHROMA_COLLECTION)

    ids = [f"chunk_{i}" for i in range(len(all_chunks))]
    metadatas = [c.metadata for c in all_chunks]
    collection.add(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    print(f"✅ Inserted {len(all_chunks)} chunks ke ChromaDB '{CHROMA_COLLECTION}'")


if __name__ == "__main__":
    main()