"""
AWQ Int4 quantize Qwen2.5-3B-Instruct.
Input : models/qwen2.5-3b-base-hf/
Output: models/qwen2.5-3b-base-awq/
Calibration: k3_seed_examples.jsonl (128 sample, root proyek)

Install deps (di venv_awq):
    pip install -r scripts/requirements_awq.txt

Estimasi: 20-40 menit di RTX 3060. 2x lebih cepat di 3080+.
"""
import json
import os

MODEL_PATH  = "./models/qwen2.5-3b-base-hf"
OUTPUT_PATH = "./models/qwen2.5-3b-base-awq"
CALIB_DATA  = "./data/k3_seed_examples.jsonl"   
N_CALIB     = 128

# ── Guard 1: output sudah ada ────────────────────────────────────────────────
if os.path.exists(OUTPUT_PATH) and os.listdir(OUTPUT_PATH):
    print(f"✅ AWQ model sudah ada di {OUTPUT_PATH}, skip quantize")
    raise SystemExit(0)

# ── Guard 2: base model harus ada dulu ───────────────────────────────────────
if not os.path.exists(MODEL_PATH) or not os.listdir(MODEL_PATH):
    raise FileNotFoundError(
        f"Base model tidak ditemukan di {MODEL_PATH}.\n"
        "Jalankan dulu: python scripts/download_base_model.py"
    )

# ── Guard 3: calib file harus ada ────────────────────────────────────────────
if not os.path.exists(CALIB_DATA):
    raise FileNotFoundError(
        f"Calibration data tidak ditemukan: {CALIB_DATA}\n"
        "Pastikan k3_seed_examples.jsonl ada di root proyek."
    )

# ── Heavy imports SETELAH guard (biar cepat fail kalau ada yang kurang) ──────
from awq import AutoAWQForCausalLM
from transformers import AutoTokenizer

# ── Step 1: Load tokenizer dulu — dibutuhkan untuk apply_chat_template ───────
print(f"📦 Loading tokenizer dari {MODEL_PATH}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

# ── Step 2: Load & format calibration data ───────────────────────────────────
calib_texts = []
with open(CALIB_DATA, encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= N_CALIB:
            break
        item = json.loads(line)
        if "messages" in item:
            # Render chat template yang sama dengan inference
            text = tokenizer.apply_chat_template(
                item["messages"],
                tokenize=False,
                add_generation_prompt=False,
            )
        elif "text" in item:
            text = item["text"]
        else:
            text = item.get("instruction", "") + " " + item.get("output", "")
        if text.strip():
            calib_texts.append(text)

print(f"📊 Loaded {len(calib_texts)} calibration samples dari {CALIB_DATA}")

# Guard 4: calib tidak boleh kosong
if not calib_texts:
    raise ValueError(
        f"Calibration data kosong setelah parsing {CALIB_DATA}.\n"
        "Cek format file — harus ada field 'messages', 'text', atau 'instruction'."
    )

# ── Step 3: Load model (SETELAH calib siap — biar gak buang VRAM kalau fail) ─
print(f"📦 Loading model dari {MODEL_PATH}...")
model = AutoAWQForCausalLM.from_pretrained(MODEL_PATH, safetensors=True)

# ── Step 4: Quantize ──────────────────────────────────────────────────────────
quant_config = {
    "zero_point": True,
    "q_group_size": 128,
    "w_bit": 4,
    "version": "GEMM",
}

print("⚙️  Quantizing ke AWQ Int4 (estimasi 20-40 menit)...")
model.quantize(tokenizer, quant_config=quant_config, calib_data=calib_texts)

# ── Step 5: Save ──────────────────────────────────────────────────────────────
os.makedirs(OUTPUT_PATH, exist_ok=True)
model.save_quantized(OUTPUT_PATH)
tokenizer.save_pretrained(OUTPUT_PATH)

total_bytes = sum(
    os.path.getsize(os.path.join(OUTPUT_PATH, f))
    for f in os.listdir(OUTPUT_PATH)
    if os.path.isfile(os.path.join(OUTPUT_PATH, f))
)
print(f"✅ AWQ selesai: {OUTPUT_PATH} ({total_bytes / 1e9:.2f} GB)")