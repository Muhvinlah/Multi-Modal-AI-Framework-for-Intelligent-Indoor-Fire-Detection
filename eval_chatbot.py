# ==============================================================================
# Tujuan       : Evaluate chatbot accuracy via batch testset
# Usage        : python eval_chatbot.py
# Output       : eval/results/results_TIMESTAMP.json + console report
# ==============================================================================

import json
import os
import time
from datetime import datetime
import requests

TESTSET_PATH = "eval/testset.json"
CHAT_ENDPOINT = "http://localhost:8000/api/chat"
RESULTS_DIR = "eval/results"


def check_keywords(reply: str, expected: list) -> dict:
    """Check berapa banyak expected keywords yang ada di reply (case-insensitive)."""
    reply_lower = reply.lower()
    hits = [kw for kw in expected if kw.lower() in reply_lower]
    return {
        "hits": hits,
        "missed": [kw for kw in expected if kw.lower() not in reply_lower],
        "recall": len(hits) / len(expected) if expected else 0,
    }


def main():
    if not os.path.exists(TESTSET_PATH):
        print(f"❌ Testset nggak ada: {TESTSET_PATH}")
        return

    with open(TESTSET_PATH, encoding="utf-8") as f:
        testset = json.load(f)

    os.makedirs(RESULTS_DIR, exist_ok=True)

    print(f"🧪 Running eval: {len(testset)} questions\n" + "=" * 60)
    results = []
    total_recall = 0
    category_recall = {}

    for item in testset:
        q = item["question"]
        expected = item.get("expected_keywords", [])
        category = item.get("category", "general")

        start = time.time()
        try:
            resp = requests.post(
                CHAT_ENDPOINT,
                json={"message": q, "history": [], "sensor_context": None},
                timeout=60,
            )
            reply = resp.json().get("reply", "")
            elapsed = time.time() - start
        except Exception as e:
            print(f"  [{item['id']}] ERROR: {e}")
            results.append({**item, "error": str(e)})
            continue

        check = check_keywords(reply, expected)
        total_recall += check["recall"]
        category_recall.setdefault(category, []).append(check["recall"])

        status = "✅" if check["recall"] >= 0.5 else "❌"
        print(f"{status} [{item['id']}] {q[:50]}... → recall {check['recall']:.2f} ({elapsed:.1f}s)")
        if check["missed"]:
            print(f"   Missed: {check['missed']}")

        results.append({
            **item,
            "reply": reply,
            "recall": check["recall"],
            "hits": check["hits"],
            "missed": check["missed"],
            "latency_sec": round(elapsed, 2),
        })

    # Summary
    avg_recall = total_recall / len(testset) if testset else 0
    print("\n" + "=" * 60)
    print(f"📊 OVERALL: {avg_recall:.2%} keyword recall")
    print("\nPer category:")
    for cat, scores in category_recall.items():
        print(f"  {cat}: {sum(scores)/len(scores):.2%} ({len(scores)} questions)")

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"{RESULTS_DIR}/results_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "overall_recall": avg_recall,
            "category_recall": {k: sum(v) / len(v) for k, v in category_recall.items()},
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Results saved: {out_path}")


if __name__ == "__main__":
    main()
