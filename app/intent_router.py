# ==============================================================================
# Tujuan       : Intent classifier ringan (rule-based) untuk routing pertanyaan
#                ke pipeline yang sesuai — hindari overhead RAG buat smalltalk dll
# Caller       : app.chatbot
# ==============================================================================

import re
from typing import Literal

Intent = Literal[
    "smalltalk",          # hi, halo, thanks → respond tanpa RAG
    "tool_needed",        # butuh data real-time → SLM diharapkan emit TOOL_CALL
    "rag_query",          # pertanyaan K3 umum → full RAG pipeline
    "clarification",      # ambigu → tanya balik (handled di Sprint 1)
    "system_meta",        # tentang sistem itu sendiri (nama dev, fitur, dll)
]


_SMALLTALK_PATTERNS = re.compile(
    r"^(hai|halo|hi|hello|hey|p|tes|test|terima\s*kasih|thanks|thx|makasih|"
    r"oke|ok|sip|mantap|good\s*job|nice|👍|🙏)[\s\!\?\.\,]*$",
    re.IGNORECASE,
)

_TOOL_HINT_PATTERNS = re.compile(
    r"\b(sekarang|saat\s*ini|terkini|terakhir|tren|berapa|nilai|baca|live|"
    r"current|now|latest|history|riwayat|kapan|menit\s*terakhir|jam\s*terakhir|"
    r"kondisi\s*kamera|daftar\s*kamera|list\s*kamera|kamera\s*apa|"
    r"sensor\s*berapa|score\s*sekarang|alert\s*terakhir|notifikasi\s*kapan)\b",
    re.IGNORECASE,
)

_SYSTEM_META_PATTERNS = re.compile(
    r"\b(siapa\s*(dev|developer|pembuat|yang\s*buat|tim)|"
    r"nama\s*sistem|versi|kapan\s*dibuat|pbl|"
    r"apa\s*fungsi\s*(?:sistem|aplikasi)|"
    r"tujuan\s*(?:sistem|aplikasi|project))\b",
    re.IGNORECASE,
)


def classify_intent(message: str, has_sensor_context: bool = False) -> Intent:
    """Klasifikasi intent dari pesan user. Rule-based, deterministic."""
    msg = message.strip()

    if _SMALLTALK_PATTERNS.match(msg):
        return "smalltalk"

    if _SYSTEM_META_PATTERNS.search(msg):
        return "system_meta"

    if _TOOL_HINT_PATTERNS.search(msg) and has_sensor_context:
        return "tool_needed"

    return "rag_query"


def smalltalk_response(message: str) -> str:
    """Generate response untuk smalltalk tanpa nge-trigger SLM."""
    msg = message.lower().strip()

    if re.match(r"^(hai|halo|hi|hello|hey|p)", msg):
        return ("Halo! Saya Asisten K3 sistem deteksi kebakaran. "
                "Mau tanya soal sensor, prosedur K3, atau kondisi ruangan sekarang?")
    if re.match(r"^(terima\s*kasih|thanks|thx|makasih)", msg):
        return "Sama-sama! Kalau ada pertanyaan lain soal keselamatan, tinggal tanya saja."
    if re.match(r"^(tes|test)", msg):
        return "Connection OK ✅. Chatbot ready. Coba tanya: 'apa fungsi MQ-7?' atau 'kondisi sensor sekarang gimana?'"
    if msg in {"oke", "ok", "sip", "mantap"}:
        return "Siap! Ada lagi yang mau ditanyakan?"
    return "Halo! Ada yang bisa dibantu?"
