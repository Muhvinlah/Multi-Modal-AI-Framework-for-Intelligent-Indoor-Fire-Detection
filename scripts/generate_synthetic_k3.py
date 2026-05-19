# ==============================================================================
# Tujuan       : Generate synthetic Q&A K3-focused via Claude API
#                Target: ~1500-2000 pairs variasi pertanyaan
# Output       : data/k3_synthetic_qa.jsonl
# Usage        : python scripts/generate_synthetic_k3.py --count 1500
# Cost estimate: ~$0.30-0.60 dengan Haiku 3.5
# ==============================================================================

import os
import sys
import json
import argparse
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient

load_dotenv()

OUTPUT_PATH = "data/k3_synthetic_qa.jsonl"
SYSTEM_PROMPT_TRAINING = (
    "Kamu adalah Asisten K3 untuk sistem deteksi kebakaran IoT. "
    "Jawab ringkas, faktual, Bahasa Indonesia baku. "
    "Maksimal 3 kalimat kecuali user minta lebih panjang."
)


# === K3-specific topics organized by category ===
K3_TOPICS = {
    "apar_usage": [
        "teknik PASS untuk APAR",
        "kapan APAR powder vs CO2 vs foam",
        "ukuran APAR sesuai luas ruangan",
        "inspeksi rutin APAR bulanan dan tahunan",
        "kelas APAR ABC vs BC vs D",
        "perbedaan APAR portable dan trolley",
        "lifecycle APAR refill 5 tahunan",
        "posisi pemasangan APAR yang benar",
        "cara baca pressure gauge APAR",
    ],
    "fire_classification": [
        "kebakaran kelas A bahan padat",
        "kebakaran kelas B cairan dan gas",
        "kebakaran kelas C instalasi listrik",
        "kebakaran kelas D logam aktif",
        "kebakaran kelas K minyak goreng",
        "fire triangle oksigen panas bahan bakar",
        "fire tetrahedron termasuk chain reaction",
        "stages of fire incipient growth fully developed decay",
        "rollover dan backdraft phenomena",
    ],
    "evacuation": [
        "prosedur evakuasi gedung tinggi",
        "evakuasi disabled person dengan wheelchair",
        "assembly point yang aman",
        "kenapa nggak boleh pakai lift saat kebakaran",
        "fire warden role responsibility",
        "drill simulasi evakuasi rutin",
        "fire escape vs stairwell perbedaan",
        "PEEP personal emergency evacuation plan",
    ],
    "first_aid_fire": [
        "P3K luka bakar derajat 1 2 3",
        "luka bakar listrik berbeda dengan termal",
        "P3K terhirup asap dan CO",
        "P3K mata terkena bahan kimia",
        "burn shock dan dehidrasi",
        "rule of nine untuk hitung luas luka bakar",
        "tanda korban perlu medical evacuation",
        "kapan pakai cling film untuk luka bakar",
    ],
    "fire_prevention": [
        "instalasi listrik aman cegah korsleting",
        "penyimpanan B3 bahan beracun berbahaya",
        "housekeeping 5R untuk cegah kebakaran",
        "fire risk assessment 5 langkah",
        "permit to work hot work welding cutting",
        "smoking area dan ashtray management",
        "lockout tagout untuk maintenance listrik",
    ],
    "fire_systems": [
        "smoke detector ionisasi vs fotoelektrik",
        "heat detector fixed temperature vs rate of rise",
        "sprinkler wet pipe dry pipe preaction",
        "fire alarm conventional vs addressable",
        "hydrant indoor vs outdoor",
        "fire pump jockey main standby",
        "fire damper di sistem HVAC",
        "PA system untuk announcement evakuasi",
    ],
    "regulations": [
        "Permenaker tentang APAR dan instalasi",
        "Kepmenaker tentang fire safety officer",
        "NFPA 10 standar APAR",
        "NFPA 25 inspeksi sistem proteksi",
        "OSHA fire safety requirement",
        "SNI tentang fire protection",
        "BSN tentang sistem pemadam otomatis",
    ],
    "sensor_iot": [
        "MQ-2 deteksi gas mudah terbakar",
        "MQ-3 deteksi alkohol",
        "MQ-4 deteksi metana",
        "MQ-5 deteksi LPG",
        "MQ-7 deteksi karbon monoksida",
        "MQ-135 kualitas udara umum",
        "SHTC3 suhu dan kelembapan",
        "flame sensor IR infrared",
        "kalibrasi sensor MQ warmup time",
        "interpretasi nilai ADC sensor",
    ],
    "system_specific": [
        "LSTM autoencoder anomaly detection",
        "YOLOv11 deteksi api dan asap",
        "decision fusion YOLO + XGBoost",
        "RAG hybrid BM25 + dense retrieval",
        "ESP32 captive portal WiFi",
        "Telegram notification untuk alert bahaya",
        "WebSocket realtime sensor streaming",
    ],
    "scenario_emergency": [
        "kebakaran di kantor lantai 5",
        "kompor meledak di dapur",
        "tabung LPG bocor",
        "korsleting laptop di kamar tidur",
        "kebakaran kabel saat kerja malam",
        "alarm bunyi tapi tidak ada api",
        "tetangga rumah kebakaran",
        "rokok meninggalkan bara di sofa",
        "trafo listrik dekat rumah meledak",
    ],
    "edge_cases": [
        "pertanyaan ambigu pendek butuh klarifikasi",
        "pertanyaan di luar K3 (politik, gosip, dll) harus tolak",
        "pertanyaan medis kompleks selain P3K dasar",
        "pertanyaan teknis di luar sistem (router setup, dll)",
        "user panic mode minta bantuan urgent",
    ],
}


SYNTHESIS_PROMPT = """Buat 6 pasangan tanya-jawab K3 berkualitas tinggi untuk topik: "{topic}".

KARAKTERISTIK Q&A:
- Pertanyaan natural, mix formal dan casual ("gimana", "apa", "kenapa", "kapan")
- Jawaban faktual 1-3 kalimat Bahasa Indonesia baku
- Variasi tone: pertanyaan teknis, pertanyaan praktis, pertanyaan klarifikasi
- HINDARI: pertanyaan trivial, jawaban panjang berbelit, halusinasi fakta

KONTEKS: Sistem ini gabungan sensor MQ + computer vision YOLOv11 + LSTM anomaly + chatbot RAG untuk early fire detection.

OUTPUT FORMAT (HANYA JSON array, no preamble):
[
  {{"q": "pertanyaan natural", "a": "jawaban faktual ringkas"}},
  ...
]"""


def call_llm(topic: str, client: LLMClient) -> list:
    prompt = SYNTHESIS_PROMPT.format(topic=topic)
    result = client.generate_json(prompt, max_tokens=2000)
    return result if isinstance(result, list) else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1500)
    parser.add_argument(
        "--provider",
        choices=["gemini", "claude", "openai"],
        default=os.getenv("LLM_PROVIDER", "gemini"),
    )
    args = parser.parse_args()

    try:
        client = LLMClient(provider=args.provider)
    except (ValueError, ImportError) as e:
        print(e)
        sys.exit(1)

    # Flatten topics
    all_topics = [(cat, t) for cat, topics in K3_TOPICS.items() for t in topics]
    target_per_topic = max(6, args.count // len(all_topics))
    rounds = max(1, target_per_topic // 6)

    print(f"🚀 Target: ~{args.count} Q&A pairs via {args.provider}")
    print(f"   {len(all_topics)} topics × {rounds} rounds × 6 pairs each")
    if args.provider == "gemini":
        # Free tier: 15 req/menit → ~4 detik per call
        total_calls = len(all_topics) * rounds
        eta_min = (total_calls * 4) / 60
        print(f"   ⏱️  Estimated time: ~{eta_min:.0f} menit (free tier rate limit)\n")
    else:
        print()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    total = 0

    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        for cat, topic in all_topics:
            for r in range(rounds):
                qa_list = call_llm(topic, client)
                for qa in qa_list:
                    if not qa.get("q") or not qa.get("a"):
                        continue
                    sample = {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT_TRAINING},
                            {"role": "user", "content": qa["q"].strip()},
                            {"role": "assistant", "content": qa["a"].strip()},
                        ],
                        "source": f"synthetic:{cat}",
                        "topic": topic,
                    }
                    out.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    total += 1
                print(f"  ✓ [{cat}] {topic} (r{r+1}): {len(qa_list)} pairs (total: {total})")
                client.rate_limit_sleep()

    print(f"\n✅ Generated {total} pairs → {OUTPUT_PATH}")
    print(f"   Provider: {args.provider}")


if __name__ == "__main__":
    main()