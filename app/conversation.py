# ==============================================================================
# Tujuan       : Manage conversation history dengan sliding window + summary
#                Kalau history > N turn → ringkas turn lama jadi 1 summary turn
# Caller       : app.chatbot
# ==============================================================================

from typing import List, Dict, Tuple


MAX_RECENT_TURNS = 6      # Jumlah turn terakhir yang dipertahankan verbatim
SUMMARY_TRIGGER = 10      # Trigger summarization saat total turn >= ini


def needs_summary(history: List[Dict]) -> bool:
    return len(history) >= SUMMARY_TRIGGER


def split_for_summary(history: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Split history jadi (untuk_diringkas, recent_verbatim)."""
    if len(history) <= MAX_RECENT_TURNS:
        return [], history
    return history[:-MAX_RECENT_TURNS], history[-MAX_RECENT_TURNS:]


def summarize_history(old_turns: List[Dict], llm=None) -> str:
    """Ringkas old turns jadi 1-3 kalimat. Pakai LLM kalau available, fallback heuristic."""
    if not old_turns:
        return ""

    if llm is None:
        # Fallback heuristic: ambil topik utama dari user turns
        user_msgs = [t["content"] for t in old_turns if t.get("role") == "user"]
        topics = ", ".join(m[:40] for m in user_msgs[:3])
        return f"Sebelumnya user nanya soal: {topics}"

    # LLM-based summarization
    history_text = "\n".join(
        f"{t.get('role', '?').upper()}: {t.get('content', '')[:200]}"
        for t in old_turns
    )
    prompt = (
        "Ringkas percakapan berikut dalam 1-2 kalimat ringkas Bahasa Indonesia. "
        "Sebutkan topik utama dan info kunci yang relevan.\n\n"
        f"{history_text}\n\nRINGKASAN:"
    )
    try:
        response = llm(
            prompt,
            max_tokens=120,
            temperature=0.2,
            stop=["\n\n", "USER:", "BOT:"],
        )
        summary = response["choices"][0]["text"].strip()
        return summary or "Percakapan sebelumnya tentang sensor dan K3."
    except Exception as e:
        print(f"[Conversation] Summary error: {e}")
        return "Percakapan sebelumnya tentang sensor dan K3."


def build_effective_history(history: List[Dict], llm=None) -> List[Dict]:
    """Return final history untuk dikirim ke LLM — disisipkan summary turn kalau perlu."""
    if not needs_summary(history):
        return history[-MAX_RECENT_TURNS:]

    old, recent = split_for_summary(history)
    summary = summarize_history(old, llm)
    print(f"[Conversation] Summary dibuat dari {len(old)} turn lama -> {len(recent)} turn verbatim")
    summary_turn = {
        "role": "system",
        "content": f"[Ringkasan percakapan sebelumnya]: {summary}",
    }
    return [summary_turn] + recent
