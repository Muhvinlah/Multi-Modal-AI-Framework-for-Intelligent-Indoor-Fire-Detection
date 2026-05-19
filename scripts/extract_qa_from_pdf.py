# ==============================================================================
# Tujuan       : Ekstrak Q&A pairs dari PDF K3 menggunakan Claude API
#                PDF di-chunk per section, tiap chunk dikirim ke Claude untuk
#                generate 5-10 Q&A pairs yang faithful ke konten asli
# Input        : PDF files di docs/k3_sources/
# Output       : data/k3_pdf_qa.jsonl (ChatML format)
# Usage        : python scripts/extract_qa_from_pdf.py
# Estimated cost: ~$0.50-2.00 untuk 3 PDF medium size (Haiku 3.5)
# ==============================================================================

import os
import sys
import json
import glob
import re
import argparse
from typing import List
from dotenv import load_dotenv

# Import unified LLM client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient

load_dotenv()

PDF_DIR = "docs/k3_sources"
OUTPUT_PATH = "data/k3_pdf_qa.jsonl"
CHUNK_SIZE_CHARS = 2500       # Chunk size per chunk dikirim ke Claude
CHUNK_OVERLAP = 200
SYSTEM_PROMPT_TRAINING = (
    "Kamu adalah Asisten K3 untuk sistem deteksi kebakaran IoT. "
    "Jawab ringkas, faktual, Bahasa Indonesia baku. "
    "Maksimal 3 kalimat kecuali user minta lebih panjang."
)


def extract_pdf_text(pdf_path: str) -> List[dict]:
    """Extract text per page dari PDF. Return list of {page_num, text}."""
    try:
        import pdfplumber
    except ImportError:
        print("❌ pip install pdfplumber dulu")
        sys.exit(1)
    
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 50:   # skip empty/cover pages
                pages.append({"page_num": i + 1, "text": text})
    return pages


def chunk_text(pages: List[dict], chunk_size: int = CHUNK_SIZE_CHARS) -> List[str]:
    """Gabungkan pages jadi chunks dengan overlap untuk preserve context."""
    full_text = "\n\n".join(f"[Page {p['page_num']}]\n{p['text']}" for p in pages)
    chunks = []
    start = 0
    while start < len(full_text):
        end = start + chunk_size
        chunk = full_text[start:end]
        # Cari boundary natural (akhir kalimat)
        if end < len(full_text):
            last_period = chunk.rfind(". ")
            if last_period > chunk_size * 0.7:
                chunk = chunk[:last_period + 1]
                end = start + last_period + 1
        chunks.append(chunk.strip())
        start = end - CHUNK_OVERLAP
    return chunks


CLAUDE_EXTRACTION_PROMPT = """Berdasarkan teks K3 / penanganan kebakaran berikut, buat 5-8 pasangan tanya-jawab berkualitas tinggi untuk training chatbot.

ATURAN STRICT:
1. Pertanyaan harus natural, seperti yang user beneran akan tanya (formal & casual mix)
2. Jawaban HARUS FAITHFUL ke teks asli — jangan ngarang fakta yang tidak ada
3. Jawaban ringkas 1-3 kalimat Bahasa Indonesia baku
4. Variasi tipe pertanyaan: definisi, prosedur, why, when, comparison
5. Hindari pertanyaan trivial (tanggal terbit, nomor regulasi, dll)
6. Fokus pada knowledge praktis K3 dan penanganan kebakaran

OUTPUT FORMAT (HANYA JSON array, no preamble, no markdown):
[
  {{"q": "pertanyaan natural", "a": "jawaban faktual 1-3 kalimat"}},
  ...
]

=== TEKS K3 ===
{chunk}
=== END TEKS ==="""


def call_llm(chunk: str, client: LLMClient) -> List[dict]:
    """Call LLM untuk extract Q&A dari 1 chunk."""
    prompt = CLAUDE_EXTRACTION_PROMPT.format(chunk=chunk)
    result = client.generate_json(prompt, max_tokens=2500)
    return result if isinstance(result, list) else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=["gemini", "claude", "openai"],
        default=os.getenv("LLM_PROVIDER", "gemini"),
        help="LLM provider (default: gemini for free tier)"
    )
    args = parser.parse_args()

    try:
        client = LLMClient(provider=args.provider)
    except (ValueError, ImportError) as e:
        print(e)
        sys.exit(1)

    pdf_files = sorted(glob.glob(f"{PDF_DIR}/*.pdf"))
    if not pdf_files:
        print(f"❌ Nggak ada PDF di {PDF_DIR}/")
        print("   Copy file PDF K3 lo ke folder tersebut dulu.")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    total_qa = 0
    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        for pdf_path in pdf_files:
            pdf_name = os.path.basename(pdf_path)
            print(f"\n📄 Processing: {pdf_name}")

            pages = extract_pdf_text(pdf_path)
            if not pages:
                print("  ⚠️ No text extracted")
                continue
            print(f"  📖 {len(pages)} pages extracted")

            chunks = chunk_text(pages)
            print(f"  📦 {len(chunks)} chunks created")

            for i, chunk in enumerate(chunks):
                print(f"  → Chunk {i+1}/{len(chunks)}: calling LLM...", end="", flush=True)
                qa_pairs = call_llm(chunk, client)

                for qa in qa_pairs:
                    if not qa.get("q") or not qa.get("a"):
                        continue
                    sample = {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT_TRAINING},
                            {"role": "user", "content": qa["q"].strip()},
                            {"role": "assistant", "content": qa["a"].strip()},
                        ],
                        "source": f"pdf:{pdf_name}",
                        "chunk_idx": i,
                    }
                    out.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    total_qa += 1

                print(f" got {len(qa_pairs)} pairs ✓")
                client.rate_limit_sleep()   # Auto-adjust sleep based on provider

    print(f"\n✅ Total Q&A extracted: {total_qa}")
    print(f"   Provider: {args.provider}")
    print(f"   Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()