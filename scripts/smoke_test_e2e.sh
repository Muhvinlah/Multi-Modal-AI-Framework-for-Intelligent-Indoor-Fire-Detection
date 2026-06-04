#!/bin/bash
# End-to-end smoke test — jalankan setelah semua service up.
# Usage: bash scripts/smoke_test_e2e.sh
# Requires: curl, python3

PASS=0; FAIL=0
BASE="http://localhost"

check() {
    local desc=$1 result=$2 expect=$3
    if echo "$result" | grep -q "$expect"; then
        echo "  PASS: $desc"
        ((PASS++))
    else
        echo "  FAIL: $desc"
        echo "    Expected : $expect"
        echo "    Got      : $(echo "$result" | head -c 300)"
        ((FAIL++))
    fi
}

echo "=== Smoke Test E2E ==="
echo ""

# T1: vLLM health
echo "[T1] vLLM running..."
R=$(curl -s --max-time 5 $BASE:8002/v1/models)
check "vLLM model registered as qwen-k3" "$R" "qwen-k3"

# T2: Chatbot health + LLM connected
echo "[T2] Chatbot LLM connected..."
R=$(curl -s --max-time 5 $BASE:8001/health)
check "Chatbot reports llm:true" "$R" '"llm":true'

# T3: Dashboard proxy ke chatbot
echo "[T3] Dashboard proxy reachable..."
R=$(curl -s --max-time 5 $BASE:8000/api/chat/health)
check "Dashboard proxy available:true" "$R" '"available":true'

# T4a: Smalltalk — harus singkat
echo "[T4a] Smalltalk response..."
R=$(curl -s --max-time 30 -X POST $BASE:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{"pertanyaan":"halo"}')
WORDS=$(echo "$R" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(len(d.get('reply','').split()))
except:
    print(999)" 2>/dev/null)
if [ "$WORDS" -lt 30 ] 2>/dev/null; then
    echo "  PASS: Smalltalk pendek ($WORDS kata)"
    ((PASS++))
else
    echo "  FAIL: Smalltalk terlalu panjang ($WORDS kata)"
    ((FAIL++))
fi

# T4b: Detail K3 — harus panjang
echo "[T4b] Detail K3 response..."
R=$(curl -s --max-time 90 -X POST $BASE:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{"pertanyaan":"jelaskan secara detail prosedur evakuasi kebakaran di gedung 5 lantai beserta langkah-langkahnya"}')
WORDS=$(echo "$R" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(len(d.get('reply','').split()))
except:
    print(0)" 2>/dev/null)
if [ "$WORDS" -gt 150 ] 2>/dev/null; then
    echo "  PASS: Detail K3 panjang ($WORDS kata)"
    ((PASS++))
else
    echo "  FAIL: Detail K3 terlalu pendek ($WORDS kata, ekspektasi >150)"
    ((FAIL++))
fi

# T5: Circuit breaker — matikan chatbot, 4 request, ke-4 harus 503 instan
echo "[T5] Circuit breaker..."
if [ -f ".pids/chatbot.pid" ]; then
    CHATBOT_PID=$(cat .pids/chatbot.pid)
    kill "$CHATBOT_PID" 2>/dev/null
    rm ".pids/chatbot.pid" 2>/dev/null
    sleep 2
    echo "  Chatbot dihentikan (PID $CHATBOT_PID). Kirim 3 request untuk trip breaker..."
fi

for i in 1 2 3; do
    curl -s --max-time 5 -X POST $BASE:8000/api/chat \
        -H "Content-Type: application/json" \
        -d '{"pertanyaan":"test"}' > /dev/null 2>&1
done

START_MS=$(date +%s%3N 2>/dev/null || echo 0)
HTTP_CODE=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" \
    -X POST $BASE:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{"pertanyaan":"test"}')
END_MS=$(date +%s%3N 2>/dev/null || echo 2001)
ELAPSED=$((END_MS - START_MS))

if [ "$HTTP_CODE" = "503" ] && [ "$ELAPSED" -lt 2000 ]; then
    echo "  PASS: Circuit breaker open — HTTP $HTTP_CODE dalam ${ELAPSED}ms"
    ((PASS++))
else
    echo "  FAIL: Circuit breaker (HTTP=$HTTP_CODE, elapsed=${ELAPSED}ms)"
    ((FAIL++))
fi

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
[ $FAIL -eq 0 ] && exit 0 || exit 1
