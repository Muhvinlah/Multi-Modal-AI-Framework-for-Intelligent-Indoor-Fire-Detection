# ==============================================================================
# Tujuan       : WebSocket handler + MJPEG stream untuk real-time monitoring
#                Multi-kamera, auto-capture anomali, Frigate-style data flow
# Caller       : main.py (router include), frontend via WebSocket + <img> tag
# Dependensi   : app.camera, app.ai_engine, app.config, app.notification
# Main Functions: websocket_monitor(), mjpeg_stream(), get_captures()
# Side Effects : Membaca frame kamera, capture anomali, notifikasi Telegram
#
# OPTIMISASI (v2):
#   - YOLO TIDAK lagi dijalankan di dalam mjpeg_stream per-frame.
#     Stream sekarang hanya encode JPEG + overlay dari cache.
#   - _yolo_cache: dict bersama antara websocket_monitor dan mjpeg_stream
#   - Semua YOLO inference melalui yolo_pool (max 2 thread, terpisah)
#   - WebSocket ping setiap 10 detik mencegah browser disconnect
# ==============================================================================

import asyncio
import json
import time
import cv2
import os
import glob
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse

from app.camera import camera_manager
from app.ai_engine import (
    predict_yolo, predict_sensor, decision_fusion, get_status_label,
    get_ppm_display, capture_anomaly
)
from app.notification import kirim_notifikasi_telegram
from app.config import get_thresholds, get_sensor_data, get_cameras
from app.executors import yolo_pool, sensor_pool

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Shared state
# ─────────────────────────────────────────────────────────────────────────────

# Throttle auto-capture: max 1 capture per 10 detik per kamera
_last_capture_time: dict = {}
CAPTURE_COOLDOWN = 10  # detik

# YOLO cache — diisi oleh websocket_monitor, dibaca oleh mjpeg_stream
# Format: { cam_id: {"detections": [...], "confidence": 0.0} }
_yolo_cache: dict = {}


# ==============================================================================
# MJPEG Stream Endpoint — continuous video stream via <img> tag
# OPTIMISASI: TIDAK menjalankan YOLO. Overlay dari _yolo_cache.
# ==============================================================================

@router.get("/stream/{cam_id}")
async def mjpeg_stream(cam_id: str):
    """
    MJPEG stream untuk kamera tertentu.
    Frontend: <img src="/stream/cam_01">
    YOLO overlay diambil dari cache (diisi websocket_monitor), bukan per-frame.
    """
    async def generate():
        while True:
            frame = camera_manager.get_frame(cam_id)
            if frame is not None:
                # Gambar overlay dari cache — TANPA menjalankan YOLO ulang
                cached = _yolo_cache.get(cam_id, {})
                for det in cached.get("detections", []):
                    x1, y1, x2, y2 = det["bbox"]
                    color = (0, 0, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label = f"{det['class']} {det['confidence']:.0f}%"
                    cv2.putText(frame, label, (x1, y1 - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    jpeg.tobytes() +
                    b'\r\n'
                )
            await asyncio.sleep(0.1)  # ~10 FPS

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ==============================================================================
# Snapshot Endpoint — single JPEG frame, lightweight for thumbnails
# ==============================================================================

from fastapi.responses import Response

@router.get("/snapshot/{cam_id}")
async def snapshot(cam_id: str):
    """
    Ambil satu frame JPEG dari kamera — bukan stream berkelanjutan.
    Digunakan oleh thumbnail strip di dashboard (di-refresh tiap beberapa detik).
    Jauh lebih hemat resource dibanding membuka MJPEG stream per thumbnail.
    """
    frame = camera_manager.get_frame(cam_id)
    if frame is None:
        return Response(status_code=204)  # No Content — kamera belum siap

    # Resize ke ukuran thumbnail (160x90) agar response tetap kecil
    thumb = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
    _, jpeg = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 55])
    return Response(
        content=jpeg.tobytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


# ==============================================================================
# Manual Capture Endpoint
# ==============================================================================

@router.get("/api/capture/{cam_id}")
async def manual_capture(cam_id: str):
    """Capture frame saat ini dari kamera tertentu."""
    frame = camera_manager.get_frame(cam_id)
    if frame is None:
        return JSONResponse({"error": "Kamera tidak tersedia"}, status_code=404)

    cameras = get_cameras()
    cam_name = cameras.get(cam_id, {}).get("name", cam_id)

    # Simpan capture
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{cam_name}_{ts}_manual.jpg"
    os.makedirs("static/captures", exist_ok=True)
    filepath = os.path.join("static", "captures", filename)
    cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

    return JSONResponse({
        "status": "ok",
        "path": f"/static/captures/{filename}",
        "timestamp": datetime.now().isoformat(),
    })


# ==============================================================================
# Captures List API
# ==============================================================================

@router.get("/api/captures")
async def get_captures(limit: int = 20):
    """Ambil daftar capture terbaru."""
    captures_dir = "static/captures"
    if not os.path.exists(captures_dir):
        return JSONResponse({"captures": []})

    files = glob.glob(os.path.join(captures_dir, "*.jpg"))
    files.sort(key=os.path.getmtime, reverse=True)

    captures = []
    for f in files[:limit]:
        fname = os.path.basename(f)
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        captures.append({
            "filename": fname,
            "path": f"/static/captures/{fname}",
            "timestamp": mtime.isoformat(),
        })

    return JSONResponse({"captures": captures})


# ==============================================================================
# WebSocket Monitor — data sensor + AI results (tanpa frame)
# OPTIMISASI:
#   - YOLO via yolo_pool (dedicated threads, max 2)
#   - Sensor via sensor_pool (dedicated threads)
#   - _yolo_cache diisi setiap siklus YOLO
#   - Ping setiap 10 detik mencegah browser disconnect
# ==============================================================================

@router.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    """
    WebSocket utama: kirim data sensor + AI ke client setiap cycle.
    """
    await websocket.accept()
    last_yolo_time: dict = {}
    last_yolo_result: dict = {}
    last_frame: dict = {}  # Cache frame terbaru per kamera untuk capture
    loop = asyncio.get_running_loop()
    last_ping_time = loop.time()
    PING_INTERVAL = 10.0  # detik

    try:
        while True:
            loop_start = loop.time()
            thresholds = get_thresholds()
            cameras = get_cameras()
            current_time = loop.time()

            # ── Ping keepalive ─────────────────────────────────────────────
            # Kirim ping JSON setiap PING_INTERVAL agar browser tidak
            # memutus koneksi karena dianggap idle (browser biasanya 30s,
            # tapi reverse proxy / Nginx bisa 10s).
            if current_time - last_ping_time >= PING_INTERVAL:
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
                last_ping_time = current_time

            cameras_data = []

            for cam_id, cam_cfg in cameras.items():
                if not cam_cfg.get("enabled", True):
                    continue

                cam_name = cam_cfg.get("name", cam_id)

                # ── Sensor data ────────────────────────────────────────────
                sensor = get_sensor_data(cam_id)
                has_sensor = bool(sensor)

                # ── YOLO inference (rate limited, via yolo_pool) ───────────
                yolo_interval = thresholds.get("yolo_interval", 3.0)
                last_t = last_yolo_time.get(cam_id, 0)

                if current_time - last_t >= yolo_interval:
                    frame = camera_manager.get_frame(cam_id)
                    if frame is not None:
                        last_frame[cam_id] = frame
                        # Submit ke dedicated yolo_pool, bukan asyncio default pool
                        yolo_result = await loop.run_in_executor(
                            yolo_pool, predict_yolo, frame
                        )
                        last_yolo_result[cam_id] = yolo_result
                        # Update shared cache untuk mjpeg_stream overlay
                        _yolo_cache[cam_id] = yolo_result
                    last_yolo_time[cam_id] = current_time

                yolo_result = last_yolo_result.get(cam_id, {"confidence": 0.0, "detections": []})
                prob_yolo = yolo_result["confidence"]

                # ── Sensor prediction (via sensor_pool) ───────────────────
                sensor_result = {"danger_prob": 0.0, "detected_class": "Clean", "class_probs": {}}
                ppm_display = {}
                temperature = 0.0
                humidity = 0.0

                if has_sensor:
                    sensor_result = await loop.run_in_executor(
                        sensor_pool, predict_sensor, sensor
                    )
                    ppm_display = get_ppm_display(sensor)
                    temperature = sensor.get("temperature", 0.0)
                    humidity = sensor.get("humidity", 0.0)

                prob_sensor = sensor_result["danger_prob"]

                # ── Decision Fusion ────────────────────────────────────────
                prob_akhir = decision_fusion(prob_yolo, prob_sensor)
                status = get_status_label(prob_akhir)

                # ── Auto-Capture on Anomaly ────────────────────────────────
                capture_path = None
                capture_frame = last_frame.get(cam_id)
                if status != "Aman" and capture_frame is not None:
                    now = loop.time()
                    last_cap = _last_capture_time.get(cam_id, 0)
                    if now - last_cap >= CAPTURE_COOLDOWN:
                        capture_path = await loop.run_in_executor(
                            None,  # capture adalah I/O ringan — pakai default pool
                            capture_anomaly, capture_frame, cam_name, status,
                            yolo_result, sensor_result, prob_akhir
                        )
                        if capture_path:
                            _last_capture_time[cam_id] = now

                # ── Notification ───────────────────────────────────────────
                if status == "Bahaya":
                    detected = sensor_result.get("detected_class", "?")
                    sensor_str = f"Gas: {detected} | Prob: {prob_akhir:.0f}%"
                    # ensure_future wraps a Future (run_in_executor) correctly
                    # create_task only accepts coroutines — this was the bug
                    asyncio.ensure_future(loop.run_in_executor(
                        None,
                        kirim_notifikasi_telegram,
                        cam_name, status, prob_akhir, sensor_str
                    ))

                cam_data = {
                    "cam_id": cam_id,
                    "cam_name": cam_name,
                    "prob_yolo": prob_yolo,
                    "yolo_detections": yolo_result.get("detections", []),
                    "prob_sensor": prob_sensor,
                    "detected_class": sensor_result.get("detected_class", "Clean"),
                    "class_probs": sensor_result.get("class_probs", {}),
                    "prob_akhir": prob_akhir,
                    "status": status,
                    "sensor_raw": sensor if has_sensor else None,
                    "sensor_ppm": ppm_display if has_sensor else None,
                    "temperature": temperature,
                    "humidity": humidity,
                    "flame_detected": bool(sensor.get("flame_detected")) if has_sensor else False,
                    "capture": capture_path,
                }
                cameras_data.append(cam_data)

            # Kirim data
            await websocket.send_text(json.dumps({
                "type": "data",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "cameras": cameras_data,
                "thresholds": thresholds,
            }))

            elapsed = loop.time() - loop_start
            sleep_time = max(0, thresholds.get("sensor_interval", 2.0) - elapsed)
            await asyncio.sleep(sleep_time)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WebSocket] Error: {e}")


# --- Legacy WebSocket (Diperbarui juga untuk kehati-hatian) ---
@router.websocket("/ws/sensor")
async def websocket_legacy(websocket: WebSocket):
    """Backward-compatible WebSocket untuk single kamera."""
    await websocket.accept()
    last_yolo_time = 0
    last_yolo_prob = 0.0
    loop = asyncio.get_running_loop()

    try:
        while True:
            loop_start = loop.time()
            thresholds = get_thresholds()
            cameras = get_cameras()
            current_time = loop.time()

            cam_id = None
            for cid, cfg in cameras.items():
                if cfg.get("enabled", True):
                    cam_id = cid
                    break

            sensor = get_sensor_data(cam_id) if cam_id else {}

            yolo_interval = thresholds.get("yolo_interval", 3.0)
            if current_time - last_yolo_time >= yolo_interval and cam_id:
                frame = camera_manager.get_frame(cam_id)
                if frame is not None:
                    yolo_result = await loop.run_in_executor(yolo_pool, predict_yolo, frame)
                    last_yolo_prob = yolo_result["confidence"]
                last_yolo_time = current_time

            prob_sensor = 0.0
            if sensor:
                sensor_res = await loop.run_in_executor(sensor_pool, predict_sensor, sensor)
                prob_sensor = sensor_res["danger_prob"]

            prob_akhir = decision_fusion(last_yolo_prob, prob_sensor)
            status = get_status_label(prob_akhir)

            await websocket.send_text(json.dumps({
                "type": "data",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "sensor": sensor if sensor else None,
                "temperature": sensor.get("temperature", 0.0) if sensor else 0.0,
                "humidity": sensor.get("humidity", 0.0) if sensor else 0.0,
                "prob_yolo": last_yolo_prob,
                "prob_xgboost": prob_sensor,
                "prob_akhir": prob_akhir,
                "status": status,
            }))

            elapsed = loop.time() - loop_start
            sleep_time = max(0, thresholds.get("sensor_interval", 2.0) - elapsed)
            await asyncio.sleep(sleep_time)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS Legacy] Error: {e}")