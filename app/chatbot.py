# ==============================================================================
# Tujuan       : Chatbot K3 independen menggunakan SLM lokal (llama-cpp-python)
#                RAG pipeline: ChromaDB search -> SLM generate response
#                Fallback ke pengetahuan bawaan jika embedding belum tersedia
#                GPU auto-detect: CUDA → Vulkan → CPU
# Caller       : main.py (router include), frontend chat
# Dependensi   : llama_cpp, chromadb, sentence_transformers
# Main Functions: POST /api/chat, load_chatbot()
# Side Effects : Load model GGUF ke RAM/VRAM (~250MB), query ChromaDB
# ==============================================================================

import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Optional

from app.config import (
    CHATBOT_MODEL_PATH, CHROMA_DB_PATH,
    CHROMA_COLLECTION, EMBEDDING_MODEL_NAME,
)

router = APIRouter()

_llm = None
_embedding_model = None
_collection = None

# Pengetahuan bawaan K3 sebagai fallback jika RAG/embedding belum ready
_BUILTIN_K3 = """PROSEDUR EVAKUASI KEBAKARAN:
1. Tetap tenang, jangan panik. 2. Matikan peralatan listrik. 3. Keluar melalui jalur evakuasi, JANGAN gunakan lift. 4. Berkumpul di Assembly Point. 5. Laporkan kehadiran ke Floor Warden.

CARA MENGGUNAKAN APAR (Teknik PASS): Pull (Tarik pin), Aim (Arahkan nozzle ke pangkal api), Squeeze (Tekan tuas), Sweep (Sapukan sisi ke sisi). Jaga jarak 1.5-2 meter.

KELAS KEBAKARAN: A (Padat)=Air/Busa/Powder. B (Cair/Gas)=Busa/CO2/Powder. C (Listrik)=CO2/Powder, JANGAN AIR. D (Logam)=Powder khusus.

SENSOR: MQ-2=gas mudah terbakar, MQ-4=metana, MQ-5=LPG, MQ-7=CO, MQ-135=kualitas udara. YOLOv11=deteksi api/asap CCTV. XGBoost=prediksi sensor.

P3K ASAP: Pindahkan ke udara segar, longgarkan pakaian, CPR jika perlu, hubungi 118/112.
P3K LUKA BAKAR: Aliri air 15-20 menit, tutup kasa steril, jangan oleskan odol/mentega.

Tim Developer: Ervin, Akmal, Jascon, dan Farhan (PBL Semester 6)."""


def _detect_gpu_backend():
    """Deteksi backend GPU yang tersedia: CUDA → Vulkan → CPU.

    Returns:
        int: jumlah layer GPU (-1 = semua di GPU, 0 = CPU only)
        str: nama backend yang terdeteksi
    """
    # Cek CUDA (NVIDIA)
    try:
        import torch
        if torch.cuda.is_available():
            return -1, f"CUDA ({torch.cuda.get_device_name(0)})"
    except ImportError:
        pass

    # Cek Vulkan via environment variable compile flag
    # llama-cpp-python yang di-compile dengan GGML_VULKAN=ON akan
    # otomatis pakai Vulkan saat n_gpu_layers > 0
    try:
        from llama_cpp import llama_supports_gpu_offload
        if llama_supports_gpu_offload():
            return -1, "Vulkan/GPU"
    except (ImportError, AttributeError):
        pass

    return 0, "CPU"


def load_chatbot():
    """Load semua komponen chatbot saat startup.
    GPU fallback: CUDA → Vulkan → CPU."""
    global _llm, _embedding_model, _collection

    if os.path.exists(CHATBOT_MODEL_PATH):
        try:
            from llama_cpp import Llama
            n_gpu, backend = _detect_gpu_backend()

            # Coba load dengan GPU dulu
            try:
                _llm = Llama(
                    model_path=CHATBOT_MODEL_PATH,
                    n_ctx=1024,
                    n_threads=4,
                    n_gpu_layers=n_gpu,
                    verbose=False,
                )
                print(f"[Chatbot] SLM loaded: {CHATBOT_MODEL_PATH} ({backend})")
            except Exception as gpu_err:
                if n_gpu != 0:
                    # GPU gagal, fallback ke CPU
                    print(f"[Chatbot] GPU ({backend}) gagal: {gpu_err}")
                    print("[Chatbot] Fallback ke CPU...")
                    _llm = Llama(
                        model_path=CHATBOT_MODEL_PATH,
                        n_ctx=1024,
                        n_threads=4,
                        n_gpu_layers=0,
                        verbose=False,
                    )
                    print(f"[Chatbot] SLM loaded: {CHATBOT_MODEL_PATH} (CPU fallback)")
                else:
                    raise
        except ImportError:
            print("[Chatbot] llama-cpp-python belum diinstall.")
        except Exception as e:
            print(f"[Chatbot] Error loading SLM: {e}")
    else:
        print(f"[Chatbot] Model GGUF tidak ditemukan: {CHATBOT_MODEL_PATH}")

    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print(f"[Chatbot] Embedding model loaded: {EMBEDDING_MODEL_NAME}")
    except Exception as e:
        print(f"[Chatbot] Embedding gagal: {e}")
        print("[Chatbot] Chatbot menggunakan pengetahuan bawaan (builtin).")

    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _collection = client.get_collection(name=CHROMA_COLLECTION)
        print(f"[Chatbot] ChromaDB loaded: {CHROMA_COLLECTION}")
    except Exception as e:
        print(f"[Chatbot] ChromaDB belum ada: {e}")


def _search_knowledge(query, n_results=3):
    """Cari dokumen relevan di ChromaDB."""
    if not _collection or not _embedding_model:
        return ""
    try:
        query_emb = _embedding_model.encode([query]).tolist()
        results = _collection.query(query_embeddings=query_emb, n_results=n_results)
        docs = results["documents"][0] if results["documents"] else []
        return "\n".join(docs)[:600]
    except Exception as e:
        print(f"[Chatbot] Search error: {e}")
        return ""


def _generate_response(user_message, context):
    """Generate response menggunakan SLM lokal."""
    if not _llm:
        return "Maaf, model chatbot belum dimuat. Pastikan file GGUF tersedia di folder models/."

    system_text = (
        "Kamu adalah Asisten K3 (Keselamatan Kerja). "
        "Jawab singkat dalam Bahasa Indonesia berdasarkan KONTEKS.\n\n"
        "KONTEKS:\n" + context
    )

    # Deteksi format berdasarkan nama file model
    model_name_lower = CHATBOT_MODEL_PATH.lower()
    
    if "qwen" in model_name_lower:
        # Format ChatML untuk Qwen 2.5
        prompt = (
            f"<|im_start|>system\n{system_text}<|im_end|>\n"
            f"<|im_start|>user\n{user_message}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
    elif "llama" in model_name_lower:
        # Format Llama 3
        prompt = (
            f"<|start_header_id|>system<|end_header_id|>\n\n{system_text}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n\n{user_message}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        )
    else:
        # Format Default (Gemma 3)
        prompt = (
            f"<start_of_turn>user\n"
            f"{system_text}\n\n{user_message}<end_of_turn>\n"
            f"<start_of_turn>model\n"
        )

    try:
        # Gunakan raw completion `_llm()` alih-alih `create_chat_completion` 
        # agar kita punya kontrol penuh terhadap struktur tag
        response = _llm(
            prompt,
            max_tokens=256,
            temperature=0.1,
            top_p=0.85,
            repeat_penalty=1.3,
            stop=["<end_of_turn>", "<eos>", "</s>", "<|im_end|>", "<|eot_id|>", "\nUser:", "\n\n\n"],
        )
        text = response["choices"][0]["text"].strip()
        if len(text) < 5:
            return "Maaf, saya tidak dapat memberikan jawaban untuk pertanyaan tersebut."
        return text
    except Exception as e:
        print(f"[Chatbot] Generation error: {e}")
        return "Maaf, terjadi kendala saat memproses jawaban."


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []


@router.post("/api/chat")
async def chat_with_bot(req: ChatRequest):
    """Endpoint chatbot RAG dengan fallback builtin."""
    pertanyaan = req.message

    # 1. Coba RAG dari ChromaDB
    konteks_rag = _search_knowledge(pertanyaan)

    # 2. Fallback ke pengetahuan bawaan jika RAG kosong
    konteks_final = konteks_rag if konteks_rag else _BUILTIN_K3

    # 3. Generate jawaban
    import asyncio
    balasan = await asyncio.to_thread(_generate_response, pertanyaan, konteks_final)

    return {"reply": balasan, "context_used": konteks_rag}
