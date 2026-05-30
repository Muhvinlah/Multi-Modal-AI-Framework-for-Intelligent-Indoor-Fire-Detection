# chatbot_service/prompt_builder.py
# ==============================================================================
# Tujuan : Build OpenAI messages array + dynamic length controller
#          System prompt eksplisit supaya Qwen2.5-3B-Instruct (tanpa fine-tune K3)
#          tau cara handle konteks K3 yang datang dari RAG
# ==============================================================================
from typing import List, Dict, Tuple
from chatbot_service.config import cfg

_SYSTEM_BASE = """Kamu adalah Asisten K3 (Keselamatan dan Kesehatan Kerja) untuk sistem \
deteksi kebakaran IoT yang dibangun tim PBL Politeknik Negeri Jakarta \
(Ervin, Akmal, Jascon, Farhan).

DOMAIN KEAHLIAN:
- Prosedur K3 dan keselamatan kebakaran
- Interpretasi data sensor MQ-2 (LPG/asap), MQ-4 (metana), MQ-5 (LPG/gas kota), \
MQ-7 (CO), MQ-135 (NH3/NOx/benzena), SHTC3 (suhu/kelembapan), dan flame sensor IR
- Protokol evakuasi, penggunaan APAR, P3K, kelas kebakaran (A/B/C/D)
- Analisis anomali LSTM dari sistem fire detection (score 0-1, threshold 0.5)
- Regulasi K3 Indonesia (Permenaker No. 4/1980 APAR, SNI terkait kebakaran)

GAYA JAWAB:
- Bahasa Indonesia baku, profesional tapi mudah dipahami.
- JAWAB SECARA LENGKAP DAN TERSTRUKTUR:
  * Definisi/konteks singkat
  * Poin utama dengan nomor (1. 2. 3.)
  * Sub-detail dengan bullet (a. b. c.)
  * Catatan keamanan / pengecualian
  * Contoh konkret bila relevan
- JANGAN potong jawaban di tengah hanya untuk ringkas.
- Untuk prosedur K3 (APAR, evakuasi, P3K, kelas kebakaran): WAJIB jelaskan setiap \
langkah, alasan di baliknya, dan kondisi kapan TIDAK boleh dilakukan.

BATASAN DOMAIN (WAJIB DIIKUTI):
- Kamu HANYA menjawab pertanyaan tentang K3, keselamatan kebakaran, sensor, sistem deteksi kebakaran, prosedur darurat, dan topik terkait.
- Untuk pertanyaan di luar domain ini (politik, hiburan, tokoh publik, olahraga, resep, dll): tolak dengan sopan: "Maaf, saya hanya dapat membantu pertanyaan seputar K3 dan sistem deteksi kebakaran."

ATURAN FAKTUAL (WAJIB DIIKUTI):
1. Sensor nilai 0 = "belum terhubung" atau "offline". JANGAN sebut 0 sebagai kondisi \
normal atau "aman". Sarankan cek koneksi ESP32.
2. LSTM anomaly score >= 0.5 = pattern berubah signifikan.
   - Dengan sensor valid -> sarankan cek lokasi fisik secara langsung.
   - Dengan sensor 0 -> kemungkinan hardware issue, BUKAN kebakaran.
3. Suhu dalam derajat Celsius (C), kelembapan dalam persen RH (%).
4. Pertanyaan ambigu -> TANYA BALIK untuk klarifikasi, jangan tebak.
5. Smalltalk (halo, terima kasih, dll) -> respon singkat dan ramah, tidak perlu \
struktur formal.
6. JIKA ada TOOLS YANG TERSEDIA di context -> emit TOOL_CALL untuk data real-time.
   JIKA ada HASIL TOOL di context -> gunakan datanya, jangan emit TOOL_CALL lagi."""


_DETAIL_TRIGGERS = frozenset({
    "jelaskan", "jelasin", "detail", "lengkap", "terperinci",
    "step by step", "langkah", "tutorial", "panduan",
    "kenapa", "mengapa", "bagaimana cara", "apa saja",
    "tolong jelaskan", "sebutkan",
})


def get_length_budget(intent: str, question: str) -> Tuple[int, str]:
    """Tentukan max_tokens + length hint berdasarkan intent dan signal kata kunci.

    Returns: (max_tokens, length_hint)
    """
    q_lower = question.lower()
    wants_detail = any(t in q_lower for t in _DETAIL_TRIGGERS)

    if intent in ("smalltalk", "clarification"):
        return cfg.max_tokens_short, "Jawab singkat 1-2 kalimat."

    if intent == "tool_needed":
        return cfg.max_tokens_long, "Jawab lengkap dan terstruktur berdasarkan data sensor/tool. Selesaikan setiap poin hingga tuntas."

    if intent == "system_meta":
        return cfg.max_tokens_medium, "Jawab informatif dengan konteks sistem."

    # rag_query
    if wants_detail:
        return cfg.max_tokens_long, (
            "Berikan jawaban DETAIL DAN TERSTRUKTUR: "
            "poin bernomor untuk setiap langkah, sub-bullet untuk detail, "
            "dan contoh konkret. Jangan potong di tengah."
        )
    return cfg.max_tokens_medium, "Jawab informatif dan terstruktur, minimal 3-5 kalimat dengan poin-poin utama."


def build_messages(
    user_message: str,
    rag_context: str,
    sensor_block: str,
    tool_result: str,
    history: List[Dict],
    intent: str,
) -> Tuple[List[Dict], int]:
    """Build OpenAI-style messages list.

    Returns: (messages, max_tokens)
    """
    max_tokens, length_hint = get_length_budget(intent, user_message)

    system_text = f"{_SYSTEM_BASE}\n\nPANDUAN PANJANG JAWABAN SAAT INI:\n{length_hint}"

    if sensor_block:
        system_text += f"\n\nKONDISI SENSOR SAAT INI:\n{sensor_block}"

    if rag_context:
        system_text += f"\n\nPENGETAHUAN K3 (referensi dari knowledge base):\n{rag_context}"

    if tool_result:
        system_text += f"\n\nHASIL TOOL (data real-time dari sistem):\n{tool_result}"

    messages: List[Dict] = [{"role": "system", "content": system_text}]

    # Sliding window — last 6 turns (3 pasang user-assistant)
    for turn in (history or [])[-6:]:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})
    return messages, max_tokens
