# ==============================================================================
# Tujuan       : Analisis feedback untuk identify common failure modes
# Usage        : python scripts/analyze_feedback.py
# ==============================================================================

import sqlite3
from collections import Counter
import re

DB_PATH = "data/feedback.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # === Overall stats ===
    total = conn.execute("SELECT COUNT(*) as c FROM feedback").fetchone()["c"]
    if total == 0:
        print("❌ Belum ada feedback")
        return

    pos = conn.execute("SELECT COUNT(*) as c FROM feedback WHERE rating=1").fetchone()["c"]
    print(f"📊 Total: {total} | 👍 {pos} ({pos/total:.1%}) | 👎 {total-pos} ({(total-pos)/total:.1%})\n")

    # === Per intent breakdown ===
    print("=== Per Intent ===")
    rows = conn.execute("""
        SELECT intent, COUNT(*) as t,
               SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) as p
        FROM feedback WHERE intent IS NOT NULL
        GROUP BY intent
        ORDER BY t DESC
    """).fetchall()
    for r in rows:
        rate = r["p"] / r["t"] if r["t"] else 0
        bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
        print(f"  {r['intent']:20s} {bar} {rate:.0%} ({r['p']}/{r['t']})")

    # === Common negative reasons ===
    print("\n=== Top Negative Reasons ===")
    rows = conn.execute("""
        SELECT reason FROM feedback
        WHERE rating=-1 AND reason IS NOT NULL AND reason != ''
    """).fetchall()
    if rows:
        words = []
        for r in rows:
            words.extend(re.findall(r"\b\w{4,}\b", r["reason"].lower()))
        for w, c in Counter(words).most_common(10):
            print(f"  {w}: {c}x")
    else:
        print("  (no reason text yet)")

    # === Negative samples (recent) ===
    print("\n=== Latest 5 Negative Examples (untuk koreksi manual) ===")
    rows = conn.execute("""
        SELECT user_message, bot_reply, reason
        FROM feedback WHERE rating=-1
        ORDER BY created_at DESC LIMIT 5
    """).fetchall()
    for i, r in enumerate(rows, 1):
        print(f"\n[{i}] Q: {r['user_message'][:80]}...")
        print(f"    A: {r['bot_reply'][:120]}...")
        if r["reason"]:
            print(f"    Why bad: {r['reason']}")

    print("\n💡 Untuk koreksi manual:")
    print("   1. Copy pertanyaan + jawaban yang salah di atas")
    print("   2. Tulis jawaban yang BENAR di data/corrections.jsonl")
    print("   3. Run scripts/build_training_data.py untuk rebuild dataset")

    conn.close()


if __name__ == "__main__":
    main()
