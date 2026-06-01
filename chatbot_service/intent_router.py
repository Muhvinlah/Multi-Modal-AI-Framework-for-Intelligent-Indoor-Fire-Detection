# chatbot_service/intent_router.py
# ==============================================================================
# Tujuan : Intent classifier rule-based — routing ke pipeline yang sesuai
# ==============================================================================

import re
from typing import Literal

Intent = Literal[
    "smalltalk",
    "tool_needed",
    "rag_query",
    "clarification",
    "system_meta",
    "out_of_domain",
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

# Report requests always need a tool call — no sensor context required
_REPORT_PATTERNS = re.compile(
    r"\b(laporan|buat\s*laporan|generate\s*report|cetak\s*laporan|"
    r"unduh\s*laporan|download\s*laporan|ekspor|export|rekap|rekapitulasi)\b",
    re.IGNORECASE,
)

# Topik yang jelas di luar domain K3 — ditangkap sebelum masuk LLM
_OFF_TOPIC_PATTERNS = re.compile(
    r"\b(politik|presiden|gubernur|walikota|bupati|dprd?|partai|pilkada|pemilu|"
    r"artis|selebriti|aktor|aktris|sinetron|drakor|film|lagu|musik|konser|"
    r"olahraga|sepakbola|basket|bulutangkis|liga|timnas|piala|pertandingan|skor|gol|"
    r"resep|masakan|makanan|kuliner|restoran|"
    r"cuaca|ramalan|zodiak|horoskop|"
    r"ekonomi|saham|crypto|bitcoin|investasi|pasar modal|"
    r"sejarah|geografi|matematika|fisika|kimia|biologi(?!\s*sensor)|"
    r"siapa\s+(?!dev|developer|pembuat|tim|yang\s+buat)"  # siapa X (bukan siapa dev)
    r")\b",
    re.IGNORECASE,
)

# Kata kunci yang mengonfirmasi pertanyaan termasuk domain K3
_K3_DOMAIN_KEYWORDS = re.compile(
    r"\b(kebakaran|api|asap|gas|smoke|fire|sensor|mq[- ]?\d|suhu|temperatur|"
    r"kelembapan|humidity|apar|pemadam|evakuasi|jalur\s*keluar|darurat|"
    r"k3|keselamatan|kesehatan\s*kerja|bahaya|hazard|co\b|lpg|metana|propana|"
    r"anomali|lstm|deteksi|flame|kamera|ruangan|sistem|alert|notifikasi|"
    r"bencana|ledakan|toksik|racun|oksigen|ventilasi|asbut)\b",
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
    msg = message.strip()
    if _SMALLTALK_PATTERNS.match(msg):
        return "smalltalk"
    if _SYSTEM_META_PATTERNS.search(msg):
        return "system_meta"
    # Off-topic check: blocked topic keyword present AND no K3 keyword to rescue it
    if _OFF_TOPIC_PATTERNS.search(msg) and not _K3_DOMAIN_KEYWORDS.search(msg):
        return "out_of_domain"
    if _REPORT_PATTERNS.search(msg):
        return "tool_needed"
    if _TOOL_HINT_PATTERNS.search(msg) and has_sensor_context:
        return "tool_needed"
    return "rag_query"


def out_of_domain_response() -> str:
    return (
        "Maaf, saya hanya dapat membantu pertanyaan seputar K3 dan sistem deteksi kebakaran — "
        "seperti prosedur evakuasi, cara pakai APAR, interpretasi data sensor, atau kondisi ruangan. "
        "Ada yang bisa saya bantu terkait keselamatan?"
    )


def smalltalk_response(message: str) -> str:
    msg = message.lower().strip()
    if re.match(r"^(hai|halo|hi|hello|hey|p)", msg):
        return ("Halo! Saya Asisten K3 sistem deteksi kebakaran. "
                "Mau tanya soal sensor, prosedur K3, atau kondisi ruangan sekarang?")
    if re.match(r"^(terima\s*kasih|thanks|thx|makasih)", msg):
        return "Sama-sama! Kalau ada pertanyaan lain soal keselamatan, tinggal tanya saja."
    if re.match(r"^(tes|test)", msg):
        return "Connection OK. Chatbot ready. Coba tanya: 'apa fungsi MQ-7?' atau 'kondisi sensor sekarang gimana?'"
    if msg in {"oke", "ok", "sip", "mantap"}:
        return "Siap! Ada lagi yang mau ditanyakan?"
    return "Halo! Ada yang bisa dibantu?"
