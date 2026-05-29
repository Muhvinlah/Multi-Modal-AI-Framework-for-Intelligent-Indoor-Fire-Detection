#!/bin/bash
# Start vLLM server untuk RTX 3060 6GB laptop.
# GPU memory utilization 45% = 2.7 GB untuk vLLM (weights + KV cache).
# Sisanya 55% = ~3.3 GB untuk YOLO + LSTM + OS overhead.
#
# --enable-prefix-caching: system prompt selalu sama → vLLM cache attention
#   prefix → request ke-2 dan seterusnya jauh lebih cepat.
set -e

AWQ_MODEL="./models/qwen2.5-3b-base-awq"

if [ ! -d "$AWQ_MODEL" ] || [ -z "$(ls -A $AWQ_MODEL 2>/dev/null)" ]; then
    echo "ERROR: AWQ model tidak ditemukan di $AWQ_MODEL"
    echo "  Jalankan dulu:"
    echo "  python -m venv venv_awq && source venv_awq/bin/activate"
    echo "  pip install -r scripts/requirements_awq.txt"
    echo "  python scripts/download_base_model.py"
    echo "  python scripts/quantize_to_awq.py"
    exit 1
fi

echo "Starting vLLM server (RTX 3060 6GB config)..."
echo "  Model : $AWQ_MODEL"
echo "  Port  : 8002"
echo "  GPU MU: 45% (~2.7 GB dari 6 GB)"

vllm serve "$AWQ_MODEL" \
    --served-model-name qwen-k3 \
    --port 8002 \
    --quantization awq \
    --dtype float16 \
    --max-model-len 2048 \
    --gpu-memory-utilization 0.45 \
    --max-num-seqs 4 \
    --enable-prefix-caching \
    --trust-remote-code
