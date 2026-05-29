# chatbot_service/conversation.py
# ==============================================================================
# Tujuan : Sliding window history + heuristic summarization
#          Kompatibel dengan vLLM via generate() — summary LLM diaktifkan Sprint 2
# ==============================================================================

from typing import List, Dict, Tuple

MAX_RECENT_TURNS = 6
SUMMARY_TRIGGER = 10


def needs_summary(history: List[Dict]) -> bool:
    return len(history) >= SUMMARY_TRIGGER


def split_for_summary(history: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    if len(history) <= MAX_RECENT_TURNS:
        return [], history
    return history[:-MAX_RECENT_TURNS], history[-MAX_RECENT_TURNS:]


def _heuristic_summary(old_turns: List[Dict]) -> str:
    user_msgs = [t["content"] for t in old_turns if t.get("role") == "user"]
    topics = ", ".join(m[:40] for m in user_msgs[:3])
    return f"Sebelumnya user nanya soal: {topics}" if topics else "Percakapan sebelumnya tentang sensor dan K3."


def build_effective_history(history: List[Dict]) -> List[Dict]:
    """Return history siap dikirim ke vLLM. Kalau panjang, sisipkan summary turn."""
    if not needs_summary(history):
        return history[-MAX_RECENT_TURNS:]

    old, recent = split_for_summary(history)
    summary = _heuristic_summary(old)
    print(f"[Conversation] Summary dari {len(old)} turn lama -> {len(recent)} turn verbatim")
    return [{"role": "system", "content": f"[Ringkasan percakapan sebelumnya]: {summary}"}] + recent
