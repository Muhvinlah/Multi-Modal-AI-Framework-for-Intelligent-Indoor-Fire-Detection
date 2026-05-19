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
import re
import uuid
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Optional

from app.config import (
    CHATBOT_MODEL_PATH, CHATBOT_N_CTX, CHATBOT_N_GPU_LAYERS,
    CHATBOT_N_THREADS, CHATBOT_FALLBACK_MODEL,
)

router = APIRouter()

# Thread count untuk llama.cpp. 8 = sweet spot untuk model 7B di CPU
# (terlalu banyak thread malah turun karena sync overhead).
_LLM_THREADS = min(8, os.cpu_count() or 4)

_llm = None

# Pengetahuan bawaan K3 sebagai fallback jika RAG/embedding belum ready
_BUILTIN_K3 = """PROSEDUR EVAKUASI KEBAKARAN:
1. Tetap tenang, jangan panik. 2. Matikan peralatan listrik. 3. Keluar melalui jalur evakuasi, JANGAN gunakan lift. 4. Berkumpul di Assembly Point. 5. Laporkan kehadiran ke Floor Warden.

CARA MENGGUNAKAN APAR (Teknik PASS): Pull (Tarik pin), Aim (Arahkan nozzle ke pangkal api), Squeeze (Tekan tuas), Sweep (Sapukan sisi ke sisi). Jaga jarak 1.5-2 meter.

KELAS KEBAKARAN: A (Padat)=Air/Busa/Powder. B (Cair/Gas)=Busa/CO2/Powder. C (Listrik)=CO2/Powder, JANGAN AIR. D (Logam)=Powder khusus.

SENSOR: MQ-2=gas mudah terbakar, MQ-4=metana, MQ-5=LPG, MQ-7=CO, MQ-135=kualitas udara. YOLOv11=deteksi api/asap CCTV. XGBoost=prediksi sensor.

P3K ASAP: Pindahkan ke udara segar, longgarkan pakaian, CPR jika perlu, hubungi 118/112.
P3K LUKA BAKAR: Aliri air 15-20 menit, tutup kasa steril, jangan oleskan odol/mentega.

Tim Developer: Ervin, Akmal, Jascon, dan Farhan (PBL Semester 6)."""

# Kata kunci domain yang biasa muncul di pertanyaan valid
_MEANINGFUL_TOKENS = re.compile(
    r"\b(apa|gimana|kenapa|bagaimana|cara|kondisi|status|bahaya|aman|"
    r"suhu|kelembapan|sensor|api|asap|gas|mq\d*|evakuasi|apar|p3k|"
    r"co|lpg|metana|kebakaran|jelaskan|tolong|berapa|dimana|siapa|"
    r"lstm|anomaly|skor|score|threshold)\b",
    re.IGNORECASE,
)


def _is_too_vague(message: str, history: list) -> bool:
    """Deteksi pertanyaan ambigu yang harus di-klarifikasi dulu."""
    msg = message.strip()
    word_count = len(msg.split())
    has_keyword = bool(_MEANINGFUL_TOKENS.search(msg))

    # < 3 kata DAN nggak ada keyword domain DAN history kosong → ambigu
    if word_count < 3 and not has_keyword and len(history) == 0:
        return True
    # Fragment ngalor-ngidul tanpa context
    if word_count <= 2 and msg.lower() in {
        "trus", "terus", "lalu", "gimana", "kenapa", "kok", "hmm", "oke", "ya", "iya"
    }:
        return True
    return False


def _clarification_response(message: str, sensor_context) -> str:
    """Generate clarification request — jangan paksa SLM halu."""
    msg = message.lower().strip()

    if "kelembapan" in msg or "humid" in msg:
        if sensor_context and sensor_context.humidity > 0:
            return (f"Maksud lo soal kelembapan saat ini? Sekarang sensor "
                    f"baca {sensor_context.humidity:.1f}%. Mau tanya apakah "
                    f"normal, atau efeknya ke deteksi kebakaran?")
        return ("Mau tanya soal kelembapan apa nih? Bisa diperjelas: "
                "(1) nilai sensor sekarang, (2) range aman, atau "
                "(3) efek kelembapan ke deteksi kebakaran?")

    if "suhu" in msg or "temperatur" in msg:
        return ("Soal suhu maksudnya: (1) baca sensor sekarang, "
                "(2) threshold bahaya, atau (3) prosedur kalau suhu naik?")

    if "gas" in msg or "mq" in msg:
        return ("Sensor gas yang mana? MQ-2 (gas mudah terbakar), MQ-4 (metana), "
                "MQ-5 (LPG), MQ-7 (CO), MQ-135 (kualitas udara), atau MQ-3 (alkohol)?")

    return ("Pertanyaannya kurang spesifik nih. Coba lengkapi — "
            "misal: 'apa arti score LSTM 1?' atau "
            "'gimana prosedur kalau MQ7 tinggi?'")


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


def _load_one_model(model_path: str, n_ctx: int):
    """Load 1 model GGUF: coba GPU dulu, fallback CPU. Raise kalau gagal total."""
    from llama_cpp import Llama
    n_gpu, backend = _detect_gpu_backend()

    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=CHATBOT_N_THREADS,
            n_gpu_layers=CHATBOT_N_GPU_LAYERS if n_gpu != 0 else 0,
            verbose=False,
        )
        print(f"[Chatbot] Loaded: {model_path} "
              f"(n_ctx={n_ctx}, threads={CHATBOT_N_THREADS}, backend={backend})")
        return llm
    except Exception as gpu_err:
        if n_gpu == 0:
            raise
        # GPU gagal → fallback CPU dengan model yang sama
        print(f"[Chatbot] GPU ({backend}) gagal: {gpu_err}")
        print("[Chatbot] Fallback ke CPU...")
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=_LLM_THREADS,
            n_gpu_layers=0,
            verbose=False,
        )
        print(f"[Chatbot] Loaded: {model_path} (CPU fallback, n_ctx={n_ctx})")
        return llm


def load_chatbot():
    """Load chatbot saat startup. Coba model utama; kalau gagal load
    (mis. OOM / file tidak ada), otomatis fallback ke model kecil (1.5B)."""
    global _llm

    # Kandidat: model utama → model fallback (kecil). n_ctx fallback dibatasi
    # agar lebih ringan di RAM.
    candidates = [(CHATBOT_MODEL_PATH, CHATBOT_N_CTX)]
    if CHATBOT_FALLBACK_MODEL and CHATBOT_FALLBACK_MODEL != CHATBOT_MODEL_PATH:
        candidates.append((CHATBOT_FALLBACK_MODEL, min(CHATBOT_N_CTX, 3072)))

    for path, nctx in candidates:
        if not os.path.exists(path):
            print(f"[Chatbot] Model GGUF tidak ditemukan: {path}")
            continue
        try:
            _llm = _load_one_model(path, nctx)
            break
        except ImportError:
            print("[Chatbot] llama-cpp-python belum diinstall.")
            break
        except Exception as e:
            print(f"[Chatbot] Gagal load {path}: {e}")
            _llm = None
            if path != candidates[-1][0]:
                print("[Chatbot] Coba model fallback yang lebih ringan...")

    if _llm is None:
        print("[Chatbot] Semua kandidat model gagal — pakai pengetahuan builtin K3.")

    # RAG engine (embedding + reranker + ChromaDB + BM25) load terpusat
    try:
        from app.rag_engine import load_rag_engine
        load_rag_engine()
    except Exception as e:
        print(f"[Chatbot] RAG engine gagal load: {e}")
        print("[Chatbot] Chatbot menggunakan pengetahuan bawaan (builtin).")


def _search_knowledge(query, sensor_context=None):
    """Wrapper backward-compat untuk rag_engine. Return context string."""
    try:
        from app.rag_engine import retrieve
        result = retrieve(query, sensor_context)
        return result.get("context", "")
    except Exception as e:
        print(f"[Chatbot] RAG retrieve error: {e}")
        return ""


def _build_history_text(history: list, fmt: str) -> str:
    """Bangun teks riwayat percakapan sesuai format model."""
    out = ""
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "").strip()
        if not content:
            continue
        if fmt == "chatml":
            tag = "user" if role == "user" else "assistant"
            out += f"<|im_start|>{tag}\n{content}<|im_end|>\n"
        elif fmt == "llama3":
            tag = "user" if role == "user" else "assistant"
            out += f"<|start_header_id|>{tag}<|end_header_id|>\n\n{content}<|eot_id|>"
        else:  # gemma
            tag = "user" if role == "user" else "model"
            out += f"<start_of_turn>{tag}\n{content}<end_of_turn>\n"
    return out


def _generate_response(user_message: str, context: str, sensor_block: str = "", history: list = None):
    """Generate response menggunakan SLM lokal, dengan sensor context dan riwayat percakapan."""
    if not _llm:
        return "Maaf, model chatbot belum dimuat. Pastikan file GGUF tersedia di folder models/."

    system_text = (
        "Kamu adalah Asisten K3 untuk sistem deteksi kebakaran IoT. "
        "Gaya jawab: ringkas, faktual, 1-3 kalimat, Bahasa Indonesia baku.\n\n"
        "ATURAN KETAT (WAJIB DIIKUTI):\n"
        "1. JIKA pertanyaan ambigu / kurang konteks → tanya balik untuk klarifikasi. "
        "JANGAN tebak-tebak atau karang jawaban.\n"
        "2. JIKA nilai sensor = 0 atau ada catatan 'belum terhubung' → "
        "sampaikan 'data sensor belum tersedia'. JANGAN sebut 0 sebagai nilai nyata "
        "(contoh SALAH: 'kelembapan turun ke 0°C'). Sarankan cek koneksi ESP32.\n"
        "3. JIKA LSTM anomaly=YA TAPI nilai sensor 0/aneh → kemungkinan sensor "
        "rusak atau belum konek, BUKAN kebakaran. Sarankan cek hardware dulu.\n"
        "4. JIKA LSTM anomaly=YA dengan sensor valid (>0) → indikasi pattern berubah "
        "cepat (gas naik, suhu naik). Sarankan waspada + cek lokasi.\n"
        "5. JANGAN gunakan kata yang tidak baku atau typo aneh (contoh SALAH: "
        "'buaya kelembapan', 'lembah ruangan'). Gunakan istilah teknis yang benar.\n"
        "6. Kelembapan diukur dalam % (PERSEN), bukan °C. Suhu dalam °C.\n"
        "7. Untuk prosedur K3 (APAR, evakuasi, P3K) → gunakan PENGETAHUAN K3 di bawah.\n"
        "8. Jika ditanya 'score LSTM artinya apa', jelaskan: itu skor 0-1 dari "
        "autoencoder yang ngukur seberapa beda pattern sensor sekarang vs kondisi normal "
        "yang dipelajari. Score >= 0.5 = anomaly.\n"
        "9. JIKA ada section 'TOOLS YANG TERSEDIA' di context, kamu BOLEH emit "
        "TOOL_CALL untuk ambil data real-time. Kalau pertanyaan bisa dijawab "
        "dari pengetahuan yang sudah ada, jangan emit TOOL_CALL.\n"
        "10. JIKA ada 'HASIL TOOL' di context, pakai data itu untuk jawab "
        "pertanyaan secara spesifik. Jangan emit TOOL_CALL lagi.\n"
        "11. JIKA pertanyaan smalltalk (hi, thanks), jawab singkat dan ramah.\n\n"
    )
    if sensor_block:
        system_text += f"KONDISI SAAT INI:\n{sensor_block}\n\n"
    system_text += "PENGETAHUAN K3:\n" + context

    history_turns = (history or [])[-6:]  # max 3 giliran terakhir

    model_name_lower = CHATBOT_MODEL_PATH.lower()

    if "qwen" in model_name_lower:
        fmt = "chatml"
        prompt = (
            f"<|im_start|>system\n{system_text}<|im_end|>\n"
            + _build_history_text(history_turns, fmt)
            + f"<|im_start|>user\n{user_message}<|im_end|>\n"
            + "<|im_start|>assistant\n"
        )
    elif "llama" in model_name_lower:
        fmt = "llama3"
        prompt = (
            f"<|start_header_id|>system<|end_header_id|>\n\n{system_text}<|eot_id|>"
            + _build_history_text(history_turns, fmt)
            + f"<|start_header_id|>user<|end_header_id|>\n\n{user_message}<|eot_id|>"
            + "<|start_header_id|>assistant<|end_header_id|>\n\n"
        )
    else:  # Gemma / default
        fmt = "gemma"
        prompt = (
            f"<start_of_turn>user\n{system_text}\n\n"
            + _build_history_text(history_turns, fmt)
            + f"{user_message}<end_of_turn>\n"
            + "<start_of_turn>model\n"
        )

    try:
        response = _llm(
            prompt,
            max_tokens=350,
            temperature=0.3,
            top_p=0.85,
            repeat_penalty=1.15,
            stop=["<end_of_turn>", "<eos>", "</s>", "<|im_end|>", "<|eot_id|>",
                  "\nUser:", "\nuser:", "\n\n\n", "<start_of_turn>"],
        )
        text = response["choices"][0]["text"].strip()
        if len(text) < 5:
            return "Maaf, saya tidak dapat memberikan jawaban untuk pertanyaan tersebut."
        return text
    except Exception as e:
        print(f"[Chatbot] Generation error: {e}")
        return "Maaf, terjadi kendala saat memproses jawaban."


class SensorContext(BaseModel):
    """Snapshot sensor saat user kirim pesan (dari frontend dashboard)."""
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    mq135: float = 0.0
    mq2: float = 0.0
    mq3: float = 0.0
    mq4: float = 0.0
    mq5: float = 0.0
    mq7: float = 0.0
    temperature: float = 0.0
    humidity: float = 0.0
    prob_akhir: float = 0.0       # Hasil decision fusion saat ini
    status: Optional[str] = None  # "Aman" / "Waspada" / "Bahaya"
    detected_class: Optional[str] = None  # Clean/Smoke/Gasoline/Mixture


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []
    sensor_context: Optional[SensorContext] = None   # NEW


def _build_sensor_block(ctx, lstm_result) -> str:
    """Bangun teks ringkas kondisi sensor + LSTM untuk diinjeksi ke prompt."""
    lstm_str = "tidak tersedia"
    if lstm_result and lstm_result.get("available"):
        lstm_str = (
            f"score={lstm_result['anomaly_score']:.2f} ({lstm_result.get('severity', '?')}), "
            f"anomaly={'YA' if lstm_result['is_anomaly'] else 'TIDAK'}"
        )

    all_zero = all(
        getattr(ctx, k) == 0
        for k in ['mq135', 'mq2', 'mq3', 'mq4', 'mq5', 'mq7', 'temperature', 'humidity']
    )
    sensor_note = ("\nCATATAN: Semua nilai sensor = 0, sensor fisik kemungkinan belum terhubung."
                   if all_zero else "")

    return (
        f"Kamera: {ctx.camera_name or ctx.camera_id or 'unknown'}\n"
        f"Status sistem: {ctx.status or 'unknown'} (prob bahaya fusi: {ctx.prob_akhir:.0f}%)\n"
        f"Deteksi visual: {ctx.detected_class or 'Clean'}\n"
        f"Suhu: {ctx.temperature:.1f}°C | Kelembapan: {ctx.humidity:.1f}%\n"
        f"MQ135={ctx.mq135:.0f} MQ2={ctx.mq2:.0f} MQ7={ctx.mq7:.0f} "
        f"MQ4={ctx.mq4:.0f} MQ5={ctx.mq5:.0f} MQ3={ctx.mq3:.0f} (ADC)\n"
        f"LSTM time-series: {lstm_str}"
        f"{sensor_note}"
    )


@router.post("/api/chat")
async def chat_with_bot(req: ChatRequest):
    """Endpoint chatbot dengan intent routing + tool calling + RAG + LSTM badge."""
    pertanyaan = req.message
    has_sensor = req.sensor_context is not None

    # === 1. Pre-flight guard: pertanyaan ambigu (dari Sprint 1) ===
    if _is_too_vague(pertanyaan, req.history or []):
        return {
            "message_id": uuid.uuid4().hex[:16],
            "reply": _clarification_response(pertanyaan, req.sensor_context),
            "context_used": "",
            "lstm": None,
            "intent": "clarification",
            "tool_used": None,
        }

    # === 2. Intent classification ===
    from app.intent_router import classify_intent, smalltalk_response
    intent = classify_intent(pertanyaan, has_sensor_context=has_sensor)

    # === 3. Fast-path: smalltalk (no SLM) ===
    if intent == "smalltalk":
        return {
            "message_id": uuid.uuid4().hex[:16],
            "reply": smalltalk_response(pertanyaan),
            "context_used": "",
            "lstm": None,
            "intent": intent,
            "tool_used": None,
        }

    # === 4. Build sensor block + LSTM inference ===
    sensor_block = ""
    lstm_result = None
    if req.sensor_context:
        ctx = req.sensor_context
        from app.lstm_anomaly import predict_anomaly
        if ctx.camera_id:
            lstm_result = await asyncio.to_thread(predict_anomaly, ctx.camera_id)
        sensor_block = _build_sensor_block(ctx, lstm_result)

    # === 5. RAG retrieve (skip kalau tool_needed) ===
    konteks_rag = ""
    if intent in ("rag_query", "system_meta"):
        konteks_rag = _search_knowledge(pertanyaan, req.sensor_context)
    konteks_final = konteks_rag if konteks_rag else _BUILTIN_K3

    # === 6. Conversation summary (sliding window) ===
    from app.conversation import build_effective_history
    effective_history = build_effective_history(req.history or [], llm=_llm)

    # === 7. First-pass LLM (with tool calling) ===
    tool_result_text = ""
    if intent == "tool_needed":
        from app.chat_tools import (
            get_tools_prompt, parse_tool_call,
            dispatch_tool_call, format_tool_result,
        )

        tools_prompt = get_tools_prompt()
        first_pass_context = f"{tools_prompt}\n\nPENGETAHUAN K3:\n{konteks_final}"

        first_response = await asyncio.to_thread(
            _generate_response, pertanyaan, first_pass_context,
            sensor_block, effective_history
        )

        tool_call = parse_tool_call(first_response)
        if tool_call:
            print(f"[Chatbot] Tool call detected: {tool_call}")
            tool_result = await asyncio.to_thread(
                dispatch_tool_call,
                tool_call["tool"],
                tool_call["args"],
                req.sensor_context,
            )
            tool_result_text = format_tool_result(tool_call["tool"], tool_result)

            # === 8. Second-pass LLM dengan tool result ===
            final_context = f"{konteks_final}\n\n{tool_result_text}"
            balasan = await asyncio.to_thread(
                _generate_response, pertanyaan, final_context,
                sensor_block, effective_history
            )
        else:
            # Bot decided no tool needed — pakai response first-pass
            balasan = first_response
    else:
        balasan = await asyncio.to_thread(
            _generate_response, pertanyaan, konteks_final,
            sensor_block, effective_history
        )

    return {
        "message_id": uuid.uuid4().hex[:16],
        "reply": balasan,
        "context_used": konteks_rag,
        "lstm": lstm_result,
        "intent": intent,
        "tool_used": tool_result_text[:200] if tool_result_text else None,
    }
