# ==============================================================================
# Tujuan       : Build training dataset untuk fine-tune chatbot
#                Sources:
#                1. dataset_100k.jsonl (existing)
#                2. Feedback DB (positive examples + corrected negatives)
#                3. Synthetic Q&A (generate via API)
#                4. Sensor log conversations
# Output       : data/training_combined.jsonl (instruction-format)
# Usage        : python scripts/build_training_data.py
# ==============================================================================

import json
import os
import sqlite3
import random

EXISTING_DATASET = "dataset_100k.jsonl"
FEEDBACK_DB = "data/feedback.db"
SENSOR_LOG_DIR = "logs/sensor"   # Kalau ada
OUTPUT_PATH = "data/training_combined.jsonl"


def load_existing_dataset(limit=None):
    """Load dataset_100k existing dalam format instruction."""
    if not os.path.exists(EXISTING_DATASET):
        print(f"⚠️ {EXISTING_DATASET} tidak ditemukan — skip")
        return []

    samples = []
    with open(EXISTING_DATASET, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"✅ Loaded {len(samples)} from {EXISTING_DATASET}")
    return samples


def load_positive_feedback():
    """Ambil feedback positive sebagai high-quality training examples."""
    if not os.path.exists(FEEDBACK_DB):
        print(f"⚠️ {FEEDBACK_DB} belum ada — skip")
        return []

    conn = sqlite3.connect(FEEDBACK_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT user_message, bot_reply, intent
        FROM feedback WHERE rating = 1
    """).fetchall()
    conn.close()

    samples = [
        {
            "instruction": row["user_message"],
            "input": "",
            "output": row["bot_reply"],
            "source": "feedback_positive",
            "intent": row["intent"],
        }
        for row in rows
    ]
    print(f"✅ Loaded {len(samples)} from feedback (positive)")
    return samples


def load_corrected_negatives(corrections_file: str = "data/corrections.jsonl"):
    """Load negative feedback yang udah dikoreksi manual oleh developer."""
    if not os.path.exists(corrections_file):
        print(f"💡 Tip: Bikin {corrections_file} untuk koreksi manual jawaban yang salah")
        return []

    samples = []
    with open(corrections_file, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                samples.append({
                    "instruction": item["user_message"],
                    "input": "",
                    "output": item["corrected_reply"],
                    "source": "manual_correction",
                })
            except (json.JSONDecodeError, KeyError):
                continue
    print(f"✅ Loaded {len(samples)} corrections")
    return samples


def load_synthetic_qa(synthetic_file: str = "data/synthetic_qa.jsonl"):
    """Load synthetic Q&A yang dibuat via API (Claude/GPT).
    Run scripts/generate_synthetic.py dulu untuk bikin file ini."""
    if not os.path.exists(synthetic_file):
        print(f"💡 Tip: Run scripts/generate_synthetic.py untuk generate {synthetic_file}")
        return []

    samples = []
    with open(synthetic_file, encoding="utf-8") as f:
        for line in f:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"✅ Loaded {len(samples)} synthetic Q&A")
    return samples


def deduplicate(samples):
    """Dedupe by instruction text. Keep last (asumsi yang lebih baru lebih bagus)."""
    seen = {}
    for s in samples:
        key = s.get("instruction", "").strip().lower()
        if key:
            seen[key] = s
    return list(seen.values())


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    all_samples = []

    # 1. Existing dataset (capped buat balance)
    all_samples.extend(load_existing_dataset(limit=50000))

    # 2. Positive feedback (high quality)
    all_samples.extend(load_positive_feedback())

    # 3. Manual corrections (highest priority — multiply weight)
    corrections = load_corrected_negatives()
    all_samples.extend(corrections * 3)   # 3x oversampling

    # 4. Synthetic Q&A
    all_samples.extend(load_synthetic_qa())

    # Dedupe + shuffle
    print(f"\nTotal before dedupe: {len(all_samples)}")
    all_samples = deduplicate(all_samples)
    print(f"Total after dedupe:  {len(all_samples)}")
    random.shuffle(all_samples)

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # Stats
    by_source = {}
    for s in all_samples:
        src = s.get("source", "existing")
        by_source[src] = by_source.get(src, 0) + 1

    print(f"\n✅ Output: {OUTPUT_PATH}")
    print("📊 By source:")
    for k, v in by_source.items():
        print(f"   {k}: {v}")

    print(f"\n💡 Upload {OUTPUT_PATH} ke Kaggle dataset, lalu rerun Finetune_K3_Qwen_1.5B_Kaggle.ipynb")


if __name__ == "__main__":
    main()
