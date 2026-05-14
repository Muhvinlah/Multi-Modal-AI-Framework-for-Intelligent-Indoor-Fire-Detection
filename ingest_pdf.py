import os
import glob
from pypdf import PdfReader
import chromadb
from sentence_transformers import SentenceTransformer

def ingest_all_pdfs(folder_path: str = "docs", collection_name: str = "k3_knowledge"):
    """
    Membaca semua file PDF di dalam folder, mengekstrak teks, 
    mengubah ke vektor, dan menyimpan ke ChromaDB.
    """
    # Pastikan folder ada
    if not os.path.exists(folder_path):
        print(f"Folder '{folder_path}' tidak ditemukan. Membuat folder baru...")
        os.makedirs(folder_path)
        print("Silakan masukkan file PDF Anda ke dalam folder 'docs' lalu jalankan ulang.")
        return

    # Cari semua file PDF di folder tersebut
    pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
    if not pdf_files:
        print(f"Tidak ada file PDF di dalam folder '{folder_path}'.")
        return

    texts = []
    metadata = []
    ids = []
    doc_counter = 1

    print(f"Ditemukan {len(pdf_files)} file PDF. Memulai ekstraksi...\n")

    # 1 & 2. Membaca dan mengekstrak teks dari SEMUA file PDF
    for pdf_path in pdf_files:
        nama_file = os.path.basename(pdf_path)
        print(f"Membaca: {nama_file}")
        try:
            reader = PdfReader(pdf_path)
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and text.strip():
                    texts.append(text.strip())
                    metadata.append({"page": i + 1, "source": nama_file})
                    ids.append(f"doc_{doc_counter}")
                    doc_counter += 1
        except Exception as e:
            print(f"Error membaca PDF {nama_file}: {e}")

    if not texts:
        print("Tidak ada teks yang berhasil diekstrak dari seluruh PDF.")
        return

    # 3. Mengubah teks menjadi vektor
    print(f"\nTotal {len(texts)} halaman berhasil diekstrak.")
    print("Memuat model AI ('all-MiniLM-L6-v2')...")
    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        print("Mengubah teks menjadi vektor (embedding)...")
        embeddings = model.encode(texts).tolist()
    except Exception as e:
        print(f"Error memuat model: {e}")
        return

    # 4. Menyimpan ke database vektor lokal
    print("Menyimpan ke database ChromaDB lokal...")
    try:
        client = chromadb.PersistentClient(path="./chroma_db_native")
        collection = client.get_or_create_collection(name=collection_name)
        
        collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadata,
            ids=ids
        )
        print(f"✅ SUKSES! Pengetahuan AI diperbarui dengan {len(texts)} dokumen ke koleksi '{collection_name}'.")
    except Exception as e:
        print(f"Error menyimpan ke ChromaDB: {e}")

if __name__ == "__main__":
    # Jalankan fungsi utama
    ingest_all_pdfs("docs")