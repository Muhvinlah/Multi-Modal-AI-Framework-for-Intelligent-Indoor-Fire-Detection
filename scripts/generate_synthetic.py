# ==============================================================================
# Tujuan       : Generate synthetic Q&A pairs via LLM API untuk training data
#                Pilih provider: Claude (Anthropic) atau GPT (OpenAI)
# Usage        : python scripts/generate_synthetic.py --provider claude --count 200
# ==============================================================================

import os
import sys
import json
import argparse
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient

load_dotenv()

OUTPUT_PATH = "data/synthetic_qa.jsonl"

# === Domain seeds untuk variasi pertanyaan ===
SEED_TOPICS = [
    {"category": "sensor_knowledge", "topics": [
        "fungsi sensor MQ-2", "range deteksi MQ-7", "perbedaan MQ-4 dan MQ-5",
        "kalibrasi sensor MQ", "interpretasi nilai ADC sensor",
        "threshold normal sensor MQ-135", "warmup time sensor MQ",
    ]},
    {"category": "k3_procedure", "topics": [
        "prosedur evakuasi gedung 3 lantai", "teknik PASS APAR",
        "P3K luka bakar derajat 1 2 3", "P3K terhirup asap CO",
        "klasifikasi kebakaran A B C D K", "jenis APAR powder vs CO2",
        "prosedur sebelum panggil pemadam", "first aid hipoksia",
    ]},
    {"category": "system_knowledge", "topics": [
        "cara kerja LSTM autoencoder anomaly detection",
        "decision fusion YOLO + XGBoost", "ESP32 captive portal flow",
        "MQTT vs HTTP untuk IoT", "ChromaDB vector search",
        "Pydantic validation FastAPI", "RAG hybrid BM25 + dense",
    ]},
    {"category": "troubleshooting", "topics": [
        "sensor MQ baca 0 terus", "ESP32 reset terus",
        "WiFi disconnect ESP32", "ChromaDB collection not found",
        "llama-cpp-python install error", "false positive LSTM tinggi",
    ]},
]


CLAUDE_PROMPT = """Buat 5 pasangan tanya-jawab berkualitas tinggi tentang topik: "{topic}".
Konteks: Sistem deteksi kebakaran IoT dengan ESP32, sensor gas MQ, LSTM anomaly detection, YOLOv11, dan chatbot K3.

Format STRICT JSON (1 array, 5 objek):
[
  {{"instruction": "pertanyaan natural dalam Bahasa Indonesia", "output": "jawaban faktual, ringkas 1-3 kalimat"}},
  ...
]

Aturan:
- Pertanyaan harus variasi: ada yang formal, ada yang casual ("gimana cara...", "apa itu...", "kenapa...")
- Jawaban Bahasa Indonesia baku, faktual, NO halusinasi
- Hindari pertanyaan yang udah obvious dari konteks
- HANYA output JSON array, no preamble"""


def call_llm(topic: str, client: LLMClient) -> list:
    """Call LLM untuk generate Q&A 1 topik. Return list of {instruction, output}."""
    prompt = CLAUDE_PROMPT.format(topic=topic)
    result = client.generate_json(prompt, max_tokens=2000)
    if isinstance(result, list):
        return result
    # Beberapa provider kadang wrap di {"qa": [...]} / {"data": [...]}
    if isinstance(result, dict):
        return result.get("qa", result.get("data", []))
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=["gemini", "claude", "openai"],
        default=os.getenv("LLM_PROVIDER", "gemini"),
    )
    parser.add_argument("--count", type=int, default=200, help="Total Q&A pairs target")
    args = parser.parse_args()

    try:
        client = LLMClient(provider=args.provider)
    except (ValueError, ImportError) as e:
        print(e)
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # Flatten topics
    all_topics = [
        (cat["category"], t)
        for cat in SEED_TOPICS for t in cat["topics"]
    ]

    target_per_topic = max(5, args.count // len(all_topics))
    rounds = max(1, target_per_topic // 5)   # tiap call gen 5 pairs

    print(f"🚀 Generating ~{args.count} Q&A via {args.provider}")
    print(f"   {len(all_topics)} topics × {rounds} rounds × 5 pairs each\n")

    generated = []
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for category, topic in all_topics:
            for r in range(rounds):
                qa_list = call_llm(topic, client)
                for qa in qa_list:
                    if not qa.get("instruction") or not qa.get("output"):
                        continue
                    sample = {
                        "instruction": qa["instruction"],
                        "input": "",
                        "output": qa["output"],
                        "source": f"synthetic_{args.provider}",
                        "category": category,
                        "topic": topic,
                    }
                    f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    generated.append(sample)
                print(f"  ✓ {category}/{topic} (round {r+1}): {len(qa_list)} pairs")
                client.rate_limit_sleep()

    print(f"\n✅ Generated {len(generated)} pairs → {OUTPUT_PATH}")
    print(f"   Provider: {args.provider}")


if __name__ == "__main__":
    main()
