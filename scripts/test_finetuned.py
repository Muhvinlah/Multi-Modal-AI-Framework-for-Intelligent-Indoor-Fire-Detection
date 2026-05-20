# ==============================================================================
# Tujuan       : Sanity test fine-tuned model sebelum production deploy
#                Run 20 test questions + compare quality dengan baseline
# Usage        : python scripts/test_finetuned.py
# ==============================================================================

import os
import sys
import json
import time
from pathlib import Path

# Adjust path sesuai project lo
MODEL_PATH = os.getenv("CHATBOT_MODEL_PATH", "models/qwen2.5-3b-k3-q4_k_m.gguf")
N_GPU_LAYERS = int(os.getenv("CHATBOT_N_GPU_LAYERS", "-1"))   # -1 = all layers to GPU
N_CTX = int(os.getenv("CHATBOT_N_CTX", "4096"))

TEST_QUESTIONS = [
    # K3 Procedure
    "Gimana cara pakai APAR yang benar?",
    "Kebakaran listrik pakai APAR apa?",
    "Prosedur evakuasi gedung tinggi?",
    "P3K luka bakar derajat 2?",
    "Korban terhirup CO harus diapain?",
    # Fire knowledge
    "Beda kebakaran kelas A dan B?",
    "Tanda awal kebakaran apa aja?",
    "Kompor meledak penyebabnya?",
    # System knowledge
    "Apa itu LSTM anomaly score?",
    "Score LSTM 1 artinya apa?",
    "Sensor MQ-7 deteksi apa?",
    "Sensor MQ-2 vs MQ-5 bedanya?",
    # Edge cases
    "Kalau",                              # Ambigu — harusnya minta klarifikasi
    "Resep nasi goreng dong",             # Out of domain — harusnya tolak
    "Terima kasih",                       # Smalltalk
    # Scenario
    "Tetangga rumah kebakaran, gua harus apa?",
    "Tabung LPG bocor di dapur",
    "Notif Telegram bilang bahaya kamera 2",
    # Multi-turn implied
    "Bahaya CO konsentrasi berapa ppm?",
    "Berapa lama kebakaran bisa membesar?",
]


def main():
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Model tidak ditemukan: {MODEL_PATH}")
        print(f"   Pastikan file .gguf dari Kaggle udah di-download ke models/")
        sys.exit(1)
    
    try:
        from llama_cpp import Llama
    except ImportError:
        print("❌ pip install llama-cpp-python")
        sys.exit(1)
    
    print(f"📦 Loading: {MODEL_PATH}")
    print(f"   GPU layers: {N_GPU_LAYERS}, Context: {N_CTX}")
    t_start = time.time()
    
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=N_CTX,
        n_gpu_layers=N_GPU_LAYERS,
        n_threads=8,
        verbose=False,
    )
    print(f"   ✅ Loaded in {time.time() - t_start:.1f}s\n")
    
    system_prompt = (
        "Kamu adalah Asisten K3 untuk sistem deteksi kebakaran IoT. "
        "Jawab ringkas, faktual, Bahasa Indonesia baku. "
        "Maksimal 3 kalimat kecuali user minta lebih panjang."
    )
    
    print("=" * 80)
    print("RUNNING TEST SUITE")
    print("=" * 80)
    
    results = []
    total_tokens = 0
    total_time = 0
    
    for i, q in enumerate(TEST_QUESTIONS, 1):
        print(f"\n[{i}/{len(TEST_QUESTIONS)}] ❓ {q}")
        
        t0 = time.time()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": q},
            ],
            max_tokens=200,
            temperature=0.3,
            top_p=0.9,
        )
        elapsed = time.time() - t0
        
        reply = response["choices"][0]["message"]["content"].strip()
        tokens = response["usage"]["completion_tokens"]
        speed = tokens / elapsed if elapsed > 0 else 0
        
        total_tokens += tokens
        total_time += elapsed
        
        print(f"💬 {reply}")
        print(f"   ⏱️ {elapsed:.2f}s | {tokens} tokens | {speed:.1f} tok/s")
        
        results.append({
            "question": q,
            "answer": reply,
            "elapsed_sec": round(elapsed, 2),
            "tokens": tokens,
            "tokens_per_sec": round(speed, 1),
        })
    
    # Save results
    os.makedirs("eval/results", exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = f"eval/results/test_finetuned_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "model_path": MODEL_PATH,
            "timestamp": timestamp,
            "total_questions": len(TEST_QUESTIONS),
            "avg_tokens_per_sec": round(total_tokens / total_time, 1) if total_time else 0,
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 80)
    print(f"✅ Done. Avg speed: {total_tokens / total_time:.1f} tok/s")
    print(f"   Results saved: {out_path}")
    print("\n💡 Review jawaban di file results — pastikan:")
    print("   - Grammar Indo baku, no typo aneh")
    print("   - Edge case 'Kalau' diminta klarifikasi (bukan halusinasi)")
    print("   - Out-of-domain ('resep nasi goreng') ditolak halus")
    print("   - Smalltalk 'Terima kasih' direspon ramah singkat")


if __name__ == "__main__":
    main()