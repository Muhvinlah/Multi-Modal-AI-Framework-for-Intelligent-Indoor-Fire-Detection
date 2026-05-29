#!/bin/bash
# Start semua service berurutan: vLLM → chatbot_service → dashboard
# Jalankan dari root proyek: bash scripts/start_all.sh
set -e

mkdir -p logs .pids

echo "=== Fire Detection System — Start All ==="

# 1. vLLM (tunggu ready sebelum start chatbot)
echo "[1/3] Starting vLLM..."
bash scripts/start_vllm.sh > logs/vllm.log 2>&1 &
echo $! > .pids/vllm.pid

echo "      Waiting for vLLM ready (max 120s)..."
for i in $(seq 1 24); do
    sleep 5
    if curl -s http://localhost:8002/v1/models > /dev/null 2>&1; then
        echo "      vLLM ready (${i}x5s)"
        break
    fi
    if [ $i -eq 24 ]; then
        echo "      WARNING: vLLM timeout — chatbot akan start degraded"
    fi
done

# 2. Chatbot service
echo "[2/3] Starting chatbot service..."
uvicorn chatbot_service.main:app \
    --host 0.0.0.0 --port 8001 \
    > logs/chatbot.log 2>&1 &
echo $! > .pids/chatbot.pid
sleep 5
echo "      Chatbot service started"

# 3. Dashboard
echo "[3/3] Starting dashboard..."
uvicorn main:app \
    --host 0.0.0.0 --port 8000 \
    > logs/dashboard.log 2>&1 &
echo $! > .pids/dashboard.pid
sleep 3
echo "      Dashboard started"

echo ""
echo "=== All services running ==="
echo "  Dashboard  : http://localhost:8000"
echo "  Chatbot    : http://localhost:8001"
echo "  vLLM API   : http://localhost:8002"
echo ""
echo "Logs   : tail -f logs/vllm.log logs/chatbot.log logs/dashboard.log"
echo "Stop   : bash scripts/stop_all.sh"
