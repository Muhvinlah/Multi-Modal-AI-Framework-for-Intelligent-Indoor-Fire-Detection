# ==============================================================================
# Tujuan       : Remote camera streaming — terima frame dari laptop eksternal,
#                jalankan YOLO, simpan frame teranotasi, stream ke dashboard.
# Caller       : main.py (router include)
# Dependensi   : app.ai_engine (predict_yolo), app.executors (yolo_pool)
# Endpoints    : POST /api/camera-frame, GET /api/camera-stream
# ==============================================================================

import asyncio
import threading

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from app.ai_engine import predict_yolo
from app.executors import yolo_pool

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Shared state
# ─────────────────────────────────────────────────────────────────────────────

_latest_frame: bytes | None = None
_frame_lock = threading.Lock()


# ==============================================================================
# POST /api/camera-frame — receive frame from external laptop
# ==============================================================================

@router.post("/api/camera-frame")
async def receive_camera_frame(frame: UploadFile = File(...)):
    """
    Terima frame JPEG dari kamera eksternal (laptop teman).
    Jalankan YOLO inference, simpan annotated frame ke shared buffer.
    """
    global _latest_frame

    raw_bytes = await frame.read()
    np_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if img is None:
        raise HTTPException(status_code=400, detail="Frame tidak bisa di-decode")

    # YOLO inference via dedicated thread pool (same pattern as websocket_handler)
    loop = asyncio.get_running_loop()
    yolo_result = await loop.run_in_executor(yolo_pool, predict_yolo, img)

    # Annotate bounding boxes
    annotated = img.copy()
    for det in yolo_result.get("detections", []):
        x1, y1, x2, y2 = det["bbox"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
        label = f"{det['class']} {det['confidence']:.0f}%"
        cv2.putText(annotated, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
    jpeg_bytes = buf.tobytes()

    with _frame_lock:
        _latest_frame = jpeg_bytes

    return JSONResponse({"status": "ok", "message": "Frame received"})


# ==============================================================================
# GET /api/camera-stream — MJPEG stream to dashboard
# ==============================================================================

@router.get("/api/camera-stream")
async def camera_stream():
    """
    MJPEG stream dari frame kamera remote yang paling baru.
    Frontend: <img src="/api/camera-stream">
    """
    async def generate():
        while True:
            with _frame_lock:
                frame_bytes = _latest_frame

            if frame_bytes is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" +
                    frame_bytes +
                    b"\r\n"
                )
            else:
                await asyncio.sleep(0.05)
                continue

            await asyncio.sleep(0.1)  # ~10 FPS

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
