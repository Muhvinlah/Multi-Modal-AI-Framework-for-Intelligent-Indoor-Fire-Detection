# ==============================================================================
# Tujuan       : Endpoint HTTP untuk terima data sensor dari ESP32
#                Menyediakan API CRUD kamera & threshold untuk dashboard
# Caller       : ESP32 via HTTP POST, dashboard via fetch()
# Dependensi   : app.config, app.camera
# Main Functions: POST /api/sensor, GET/POST /api/cameras, GET/POST /api/thresholds
# Side Effects : Update state di app.config, sync kamera
# ==============================================================================

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional, Dict
from datetime import datetime
from app.lstm_anomaly import push_sample
import threading
import time

from app.config import (
    get_cameras, add_camera, remove_camera,
    get_thresholds, set_thresholds,
    update_sensor_data, get_sensor_data,
)
from app.camera import camera_manager

router = APIRouter()


# --- Model Pydantic ---

# Rate limiting: max 1 request per IP per MIN_INTERVAL seconds
_sensor_rate: dict = {}  # { ip: last_accept_timestamp }
MIN_INTERVAL = 1.0        # ESP32 sends every 2s, reject anything faster than 1s


class SensorPayload(BaseModel):
    """Data yang dikirim ESP32 setiap 2 detik."""
    camera_id: str
    mq135: float = 0.0
    mq2: float = 0.0
    mq3: float = 0.0
    mq4: float = 0.0
    mq5: float = 0.0
    mq7: float = 0.0
    temperature: float = 0.0
    humidity: float = 0.0

    @field_validator('mq135', 'mq2', 'mq3', 'mq4', 'mq5', 'mq7', mode='before')
    @classmethod
    def clamp_adc(cls, v):
        """ADC nilai harus 0–4095 (12-bit ESP32)."""
        v = float(v)
        return max(0.0, min(4095.0, v))

    @field_validator('temperature', mode='before')
    @classmethod
    def validate_temp(cls, v):
        """Suhu realistis: -40°C s/d 125°C (batas sensor DHT22/DS18B20)."""
        v = float(v)
        if not (-40.0 <= v <= 125.0):
            return 0.0  # Nilai tidak masuk akal, abaikan
        return v

    @field_validator('humidity', mode='before')
    @classmethod
    def validate_humidity(cls, v):
        """Kelembapan harus 0–100%."""
        v = float(v)
        return max(0.0, min(100.0, v))


class CameraPayload(BaseModel):
    cam_id: str
    name: str
    rtsp_url: str


class ThresholdPayload(BaseModel):
    prob_aman: Optional[float] = None
    prob_waspada: Optional[float] = None
    yolo_weight_high: Optional[float] = None
    yolo_weight_low: Optional[float] = None
    yolo_threshold: Optional[float] = None
    yolo_interval: Optional[float] = None
    sensor_interval: Optional[float] = None


# --- Endpoint Sensor ESP32 ---

@router.post("/api/sensor")
async def receive_sensor_data(payload: SensorPayload, request: Request):
    """
    Terima data dari ESP32 dan simpan ke memory.
    - Rate limited: max 1 request/detik per IP
    - Validated: nilai ADC, suhu, dan kelembapan dicek range-nya
    - All-zero guard: payload kosong (ESP32 belum siap) diabaikan
    """
    # --- Rate limiting ---
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    last_seen = _sensor_rate.get(client_ip, 0)
    if now - last_seen < MIN_INTERVAL:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Min interval: {MIN_INTERVAL}s"
        )
    _sensor_rate[client_ip] = now

    # --- All-zero guard (ESP32 belum kirim data nyata) ---
    sensor_values = [payload.mq135, payload.mq2, payload.mq3,
                     payload.mq4, payload.mq5, payload.mq7]
    if all(v == 0.0 for v in sensor_values):
        return {"status": "ignored", "reason": "all_zero", "camera_id": payload.camera_id}

    data = {
        "mq135": payload.mq135,
        "mq2": payload.mq2,
        "mq3": payload.mq3,
        "mq4": payload.mq4,
        "mq5": payload.mq5,
        "mq7": payload.mq7,
        "temperature": payload.temperature,
        "humidity": payload.humidity,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    update_sensor_data(payload.camera_id, data)
    push_sample(payload.camera_id, data)
    _cache_snapshot(payload.camera_id, data)

    cameras = get_cameras()
    if payload.camera_id not in cameras:
        print(
            f"[Sensor] WARNING: camera_id '{payload.camera_id}' not in registered cameras "
            f"{list(cameras.keys())}. Data stored but won't appear on dashboard."
        )
        return {"status": "ok", "camera_id": payload.camera_id, "warning": "camera_id not registered"}

    return {"status": "ok", "camera_id": payload.camera_id}


@router.get("/api/sensor/{camera_id}")
async def get_latest_sensor(camera_id: str):
    """Ambil data sensor terbaru untuk kamera tertentu."""
    data = get_sensor_data(camera_id)
    if not data:
        return {"status": "no_data", "camera_id": camera_id}
    return {"status": "ok", "camera_id": camera_id, "data": data}


# --- Endpoint Kamera CRUD ---

@router.get("/api/cameras")
async def list_cameras():
    """Daftar semua kamera yang terdaftar."""
    return {"cameras": get_cameras()}


@router.post("/api/cameras")
async def add_new_camera(payload: CameraPayload):
    """Tambah kamera baru dan langsung start stream."""
    add_camera(payload.cam_id, payload.name, payload.rtsp_url)
    camera_manager.add_camera(payload.cam_id, payload.rtsp_url)
    return {"status": "added", "cam_id": payload.cam_id}


@router.delete("/api/cameras/{cam_id}")
async def delete_camera(cam_id: str):
    """Hapus kamera."""
    remove_camera(cam_id)
    camera_manager.remove_camera(cam_id)
    return {"status": "removed", "cam_id": cam_id}


# --- Endpoint Threshold ---

@router.get("/api/thresholds")
async def get_current_thresholds():
    """Ambil semua threshold yang aktif."""
    return {"thresholds": get_thresholds()}


@router.post("/api/thresholds")
async def update_thresholds(payload: ThresholdPayload):
    """Update threshold dari dashboard."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        set_thresholds(updates)
    return {"status": "updated", "thresholds": get_thresholds()}


# === In-memory cache untuk latest sensor reading per camera ===
_latest_snapshots: Dict[str, Dict] = {}
_snapshot_lock = threading.Lock()


def _cache_snapshot(camera_id: str, data: Dict):
    """Internal — dipanggil dari endpoint POST sensor data."""
    if not camera_id:
        return
    with _snapshot_lock:
        _latest_snapshots[camera_id] = {**data, "updated_at": time.time()}


def get_latest_snapshot(camera_id: Optional[str]) -> Optional[Dict]:
    """Public — query latest sensor data untuk 1 camera."""
    with _snapshot_lock:
        if not camera_id:
            # Return first available camera kalau nggak spesifik
            for cid, snap in _latest_snapshots.items():
                return {**snap, "camera_id": cid}
            return None
        return _latest_snapshots.get(camera_id)