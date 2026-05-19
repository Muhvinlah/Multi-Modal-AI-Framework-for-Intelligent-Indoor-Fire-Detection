# ==============================================================================
# Tujuan       : Combine seed + pdf + synthetic → final training dataset
#                Plus dedupe, quality filter, train/val split 90/10
# Output       : data/k3_qwen7b_train.jsonl + data/k3_qwen7b_val.jsonl
# Usage        : python scripts/build_k3_dataset.py
# ==============================================================================

import os
import json
import random
import hashlib
from pathlib import Path

SOURCES = {
    "seed":       "data/k3_seed_examples.jsonl",
    "pdf":        "data/k3_pdf_qa.jsonl",
    "synthetic":  "data/k3_synthetic_qa.jsonl",
}
TRAIN_PATH = "data/k3_qwen7b_train.jsonl"
VAL_PATH = "data/k3_qwen7b_val.jsonl"

# Oversampling weights — seed examples dianggap "gold", duplikasi lebih banyak
WEIGHTS = {
    "seed":      3,    # Triple oversampled
    "pdf":       1,
    "synthetic": 1,
}

VAL_RATIO = 0.10
MIN_QUESTION_LEN = 3       # Minimum word count
MIN_ANSWER_LEN = 10
MAX_ANSWER_LEN = 300       # Avoid super-long answers


def load_jsonl(path: str) -> list:
    if not os.path.exists(path):
        print(f"  ⚠️ {path} not found — skipping")
        return []
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def hash_question(messages: list) -> str:
    """Hash question text for dedup."""
    user_msg = next((m["content"] for m in messages if m.get("role") == "user"), "")
    return hashlib.md5(user_msg.lower().strip().encode()).hexdigest()


def quality_filter(item: dict) -> bool:
    """Filter low-quality samples."""
    messages = item.get("messages", [])
    if len(messages) < 2:
        return False
    
    user_msg = next((m["content"] for m in messages if m.get("role") == "user"), "")
    asst_msg = next((m["content"] for m in messages if m.get("role") == "assistant"), "")
    
    if len(user_msg.split()) < MIN_QUESTION_LEN:
        return False
    if not (MIN_ANSWER_LEN <= len(asst_msg) <= MAX_ANSWER_LEN):
        return False
    if user_msg.strip().lower() == asst_msg.strip().lower():
        return False
    return True


def main():
    random.seed(42)
    all_samples = []
    seen_hashes = set()
    stats_by_source = {}
    
    print("📥 Loading sources...")
    for source_name, path in SOURCES.items():
        items = load_jsonl(path)
        weight = WEIGHTS.get(source_name, 1)
        
        added = 0
        for item in items:
            if not quality_filter(item):
                continue
            h = hash_question(item.get("messages", []))
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            
            # Oversample by weight
            for _ in range(weight):
                all_samples.append(item)
            added += 1
        
        stats_by_source[source_name] = {
            "raw": len(items),
            "unique_added": added,
            "weight": weight,
        }
        print(f"  [{source_name}] raw: {len(items)}, unique kept: {added}, weight: {weight}x")
    
    if not all_samples:
        print("❌ No samples collected. Run scripts/extract_qa_from_pdf.py dan generate_synthetic_k3.py dulu.")
        return
    
    print(f"\n📊 Total samples (with oversampling): {len(all_samples)}")
    print(f"   Unique base samples: {len(seen_hashes)}")
    
    # Shuffle + split
    random.shuffle(all_samples)
    val_size = int(len(all_samples) * VAL_RATIO)
    val_samples = all_samples[:val_size]
    train_samples = all_samples[val_size:]
    
    # Write outputs
    with open(TRAIN_PATH, "w", encoding="utf-8") as f:
        for s in train_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(VAL_PATH, "w", encoding="utf-8") as f:
        for s in val_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    
    print(f"\n✅ Train: {len(train_samples)} → {TRAIN_PATH}")
    print(f"✅ Val:   {len(val_samples)} → {VAL_PATH}")
    print(f"\n💡 Next step: Upload kedua file ini sebagai Kaggle Dataset, lalu run notebook training.")


if __name__ == "__main__":
    main()