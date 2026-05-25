# ==============================================================================
# Tujuan       : Centralized executor pools untuk isolasi thread berat
#                Mencegah YOLO/LLM memblokir thread pool web server
# Caller       : app.websocket_handler (YOLO), app.chatbot (LLM)
# Main Objects : yolo_pool, llm_pool
# Notes        : Kedua pool ini TERPISAH dari default asyncio thread pool.
#                asyncio.to_thread() pakai ThreadPoolExecutor bawaan Python
#                (shared dengan seluruh app). Pool ini prevent starvation.
# ==============================================================================

import os
from concurrent.futures import ThreadPoolExecutor

# ─────────────────────────────────────────────────────────────────────────────
# YOLO Pool — max 2 worker threads
#   - Setiap kamera bisa trigger YOLO secara paralel (hingga 2 kamera sekaligus)
#   - YOLO releases GIL saat inference (torch/C++), jadi multi-thread efektif
#   - > 2 workers tidak bermanfaat karena CPU bottleneck
# ─────────────────────────────────────────────────────────────────────────────
yolo_pool = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="yolo-worker",
)

# ─────────────────────────────────────────────────────────────────────────────
# LLM Pool — max 1 worker thread
#   - LLM (llama.cpp) hanya bisa generate satu respons sekaligus
#   - max_workers=1 mencegah antrian permintaan chat memblokir YOLO pool
#   - Permintaan chat ke-2 akan menunggu di queue internal executor ini,
#     bukan di asyncio event loop, sehingga WebSocket tetap responsif
# ─────────────────────────────────────────────────────────────────────────────
llm_pool = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="llm-worker",
)

# ─────────────────────────────────────────────────────────────────────────────
# Sensor Pool — max 1 worker thread
#   - Sensor prediction (sklearn RF) ringan, tapi tetap di pool terpisah
#   - Mencegah starvasi bila semua asyncio threads sedang handle HTTP request
# ─────────────────────────────────────────────────────────────────────────────
sensor_pool = ThreadPoolExecutor(
    max_workers=min(2, os.cpu_count() or 2),
    thread_name_prefix="sensor-worker",
)
