# ==============================================================================
# Tujuan       : Konfigurasi global sistem (JWT, Telegram, kamera, threshold)
#                Menyediakan state management untuk konfigurasi dinamis via dashboard
# Caller       : Semua modul di app/
# Dependensi   : os, dotenv
# Main Functions: get_config(), update_cameras(), update_thresholds()
# Side Effects : Baca file .env
# ==============================================================================

import os
import json
import threading
from dotenv import load_dotenv

load_dotenv(override=True)

# --- Keamanan & JWT ---
SECRET_KEY = os.getenv("SECRET_KEY", "pbl-sem-6-rahasia-banget")
ALGORITHM = "HS256"

# --- Telegram ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
THROTTLE_SECONDS = 50

# --- Path Model ---
YOLO_MODEL_PATH = "models/best.pt"
XGBOOST_MODEL_PATH = "models/fire_detection_rf.pkl"
CHATBOT_MODEL_PATH = os.getenv("CHATBOT_MODEL_PATH", "models/tinyllama-1.1b-chat.Q4_K_M.gguf")

# --- ChromaDB ---
CHROMA_DB_PATH = "./chroma_db_native"
CHROMA_COLLECTION = "k3_knowledge"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# ==============================================================================
# Konfigurasi Dinamis (bisa diubah via Dashboard)
# Thread-safe menggunakan Lock
# ==============================================================================
_config_lock = threading.Lock()

# Konfigurasi Kamera (bisa ditambah/hapus via dashboard)
# Format: { "cam_id": { "name": "...", "rtsp_url": "rtsp://...", "enabled": True } }
_cameras: dict = {}

# Konfigurasi Threshold (bisa diubah via dashboard)
_thresholds: dict = {
    "prob_aman": 30,       # Di bawah ini = Aman
    "prob_waspada": 70,    # Di bawah ini = Waspada, di atas = Bahaya
    "yolo_weight_high": 0.7,   # Bobot YOLO saat YOLO confidence tinggi
    "yolo_weight_low": 0.3,    # Bobot YOLO saat YOLO confidence rendah
    "yolo_threshold": 50,      # Batas YOLO dianggap "high confidence"
    "yolo_interval": 3.0,      # Interval inference YOLO (detik)
    "sensor_interval": 2.0,    # Interval baca sensor (detik)
}

# Data sensor terbaru dari ESP32 (per camera_id)
# Format: { "cam_01": { "mq135": 0, "mq2": 0, ..., "timestamp": "..." } }
_sensor_data: dict = {}

# File persisten untuk simpan konfigurasi
_CONFIG_FILE = "config_state.json"


def _load_persisted_config():
    """Load konfigurasi dari file JSON jika ada."""
    global _cameras, _thresholds
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r") as f:
                data = json.load(f)
                _cameras.update(data.get("cameras", {}))
                _thresholds.update(data.get("thresholds", {}))
    except Exception:
        pass


def _save_config():
    """Simpan konfigurasi ke file JSON."""
    try:
        with open(_CONFIG_FILE, "w") as f:
            json.dump({"cameras": _cameras, "thresholds": _thresholds}, f, indent=2)
    except Exception:
        pass


# --- Getter / Setter thread-safe ---

def get_cameras() -> dict:
    with _config_lock:
        return dict(_cameras)


def set_cameras(cameras: dict):
    global _cameras
    with _config_lock:
        _cameras = cameras
        _save_config()


def add_camera(cam_id: str, name: str, rtsp_url: str):
    with _config_lock:
        _cameras[cam_id] = {"name": name, "rtsp_url": rtsp_url, "enabled": True}
        _save_config()


def remove_camera(cam_id: str):
    with _config_lock:
        _cameras.pop(cam_id, None)
        _save_config()


def get_thresholds() -> dict:
    with _config_lock:
        return dict(_thresholds)


def set_thresholds(thresholds: dict):
    global _thresholds
    with _config_lock:
        _thresholds.update(thresholds)
        _save_config()


def get_sensor_data(cam_id: str = None) -> dict:
    with _config_lock:
        if cam_id:
            return dict(_sensor_data.get(cam_id, {}))
        return dict(_sensor_data)


def update_sensor_data(cam_id: str, data: dict):
    with _config_lock:
        _sensor_data[cam_id] = data


# Load persisted pada import
_load_persisted_config()
