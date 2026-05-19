# ==============================================================================
# Tujuan       : LSTM time-series anomaly detection untuk data sensor MQ
#                Maintains rolling buffer per kamera, inference on-demand
# Caller       : app.sensor (push), app.chatbot (inference)
# Dependensi   : tensorflow/keras (atau torch), numpy
# Main Functions: push_sample(), predict_anomaly(), load_lstm_model()
# Side Effects : Load .h5/.keras model ke memory saat startup
# ==============================================================================

import os
import json
import threading
from collections import deque
from typing import Dict, Optional, List
import numpy as np
import joblib

# --- Config ---
LSTM_MODEL_PATH = os.getenv("LSTM_MODEL_PATH", "models/lstm_anomaly.keras")
LSTM_SCALER_PATH = os.getenv("LSTM_SCALER_PATH", "models/lstm_scaler.pkl")
LSTM_META_PATH = os.getenv("LSTM_META_PATH", "models/lstm_threshold.json")
WINDOW_SIZE = 30
FEATURE_ORDER = ["mq135", "mq2", "mq3", "mq4", "mq5", "mq7", "temperature", "humidity"]
ANOMALY_THRESHOLD = 0.5   # Score >= 0.5 setelah normalize = anomaly

# --- State ---
_buffers: Dict[str, deque] = {}
_buffer_lock = threading.Lock()
_lstm_model = None
_lstm_scaler = None
_lstm_threshold_mse = None
_lstm_scale_k = None


def load_lstm_model():
    """Load autoencoder + scaler + threshold metadata."""
    global _lstm_model, _lstm_scaler, _lstm_threshold_mse, _lstm_scale_k

    if not os.path.exists(LSTM_MODEL_PATH):
        print(f"[LSTM] Model tidak ditemukan: {LSTM_MODEL_PATH} — mode degraded")
        return

    try:
        from tensorflow.keras.models import load_model
        _lstm_model = load_model(LSTM_MODEL_PATH, compile=False)
        print(f"[LSTM] Model loaded: {LSTM_MODEL_PATH}")

        if os.path.exists(LSTM_SCALER_PATH):
            _lstm_scaler = joblib.load(LSTM_SCALER_PATH)
            print(f"[LSTM] Scaler loaded: {LSTM_SCALER_PATH}")
        else:
            print(f"[LSTM] ⚠️ Scaler tidak ditemukan: {LSTM_SCALER_PATH}")

        if os.path.exists(LSTM_META_PATH):
            with open(LSTM_META_PATH) as f:
                meta = json.load(f)
            _lstm_threshold_mse = float(meta["threshold_mse_raw"])
            _lstm_scale_k = float(meta["scale_k"])
            print(f"[LSTM] Metadata loaded: threshold={_lstm_threshold_mse:.5f}, scale_k={_lstm_scale_k:.4f}")
        else:
            print(f"[LSTM] ⚠️ Metadata tidak ditemukan: {LSTM_META_PATH}")
    except Exception as e:
        print(f"[LSTM] Gagal load: {e}")


def push_sample(camera_id: str, sensor_data: dict) -> None:
    """Tambahkan 1 sample ke rolling buffer. Dipanggil dari app/sensor.py."""
    if not camera_id or not sensor_data:
        return
    sample = [float(sensor_data.get(k, 0.0)) for k in FEATURE_ORDER]
    with _buffer_lock:
        if camera_id not in _buffers:
            _buffers[camera_id] = deque(maxlen=WINDOW_SIZE)
        _buffers[camera_id].append(sample)


def _classify_severity(score: float) -> tuple:
    """Map score 0-1 ke severity label + warna untuk frontend."""
    if score < 0.3:
        return "normal", "green"
    elif score < 0.5:
        return "perhatian", "yellow"
    elif score < 0.8:
        return "waspada", "orange"
    else:
        return "anomaly_tinggi", "red"


def _top_contributing_features(x_scaled, recon, n: int = 3) -> list:
    """Cari N sensor dengan reconstruction error tertinggi (feature attribution)."""
    err_per_feat = np.mean(np.square(x_scaled - recon), axis=(0, 1))
    top_idx = np.argsort(err_per_feat)[-n:][::-1]
    return [
        {"feature": FEATURE_ORDER[i], "error": float(err_per_feat[i])}
        for i in top_idx
    ]


# === State tambahan untuk history tracking ===
_score_history: Dict[str, deque] = {}     # camera_id → deque of {ts, score, mse}
_SCORE_HISTORY_MAX = 1800                  # ~1 jam history kalau push tiap 2 detik
_history_lock = threading.Lock()


def _record_score(camera_id: str, score: float, mse: float):
    """Simpan score ke history. Dipanggil internal dari predict_anomaly."""
    import time
    if not camera_id:
        return
    with _history_lock:
        if camera_id not in _score_history:
            _score_history[camera_id] = deque(maxlen=_SCORE_HISTORY_MAX)
        _score_history[camera_id].append({
            "ts": time.time(),
            "score": float(score),
            "mse": float(mse),
        })


def query_score_history(camera_id: str, minutes: int = 10) -> List[Dict]:
    """Ambil score history N menit terakhir untuk 1 camera."""
    import time
    if not camera_id:
        return []
    cutoff = time.time() - (minutes * 60)
    with _history_lock:
        buf = _score_history.get(camera_id, deque())
        return [item for item in buf if item["ts"] >= cutoff]


def predict_anomaly(camera_id: str) -> dict:
    """Inference: reconstruct window, hitung MSE, normalize ke score 0-1."""
    with _buffer_lock:
        buf = _buffers.get(camera_id)
        if not buf or len(buf) < WINDOW_SIZE:
            return {
                "available": False,
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "samples_used": len(buf) if buf else 0,
                "reason": f"butuh {WINDOW_SIZE} samples, baru ada {len(buf) if buf else 0}",
            }
        window = np.array(list(buf), dtype=np.float32)

    if _lstm_model is None or _lstm_scaler is None or _lstm_threshold_mse is None:
        return {
            "available": False,
            "anomaly_score": 0.0,
            "is_anomaly": False,
            "samples_used": WINDOW_SIZE,
            "reason": "LSTM model/scaler/metadata belum lengkap",
        }

    try:
        # Step 1: Scale
        flat = window.reshape(-1, len(FEATURE_ORDER))
        scaled = _lstm_scaler.transform(flat).reshape(window.shape).astype(np.float32)
        x = scaled[np.newaxis, ...]   # (1, 30, 8)

        # Step 2: Reconstruct via autoencoder
        recon = _lstm_model.predict(x, verbose=0)

        # Step 3: MSE per window
        mse = float(np.mean(np.square(x - recon)))

        # Step 4: Sigmoid normalization → score 0-1
        score = 1.0 / (1.0 + np.exp(-_lstm_scale_k * (mse - _lstm_threshold_mse)))
        score = float(score)

        # Record ke history untuk query tren nanti
        _record_score(camera_id, score, mse)

        severity, color = _classify_severity(score)
        top_features = _top_contributing_features(x, recon)

        feat_names = ", ".join([f["feature"] for f in top_features])
        if score >= 0.8:
            reason_human = f"Pattern abnormal di sensor: {feat_names}"
        elif score >= 0.5:
            reason_human = f"Sedikit deviasi pada {feat_names}"
        else:
            reason_human = "Pattern sensor dalam range normal"

        return {
            "available": True,
            "anomaly_score": round(score, 4),
            "mse_raw": round(mse, 6),
            "is_anomaly": score >= ANOMALY_THRESHOLD,
            "severity": severity,
            "color": color,
            "top_features": top_features,
            "reason_human": reason_human,
            "samples_used": WINDOW_SIZE,
            "reason": "ok",
        }
    except Exception as e:
        return {
            "available": False,
            "anomaly_score": 0.0,
            "is_anomaly": False,
            "samples_used": WINDOW_SIZE,
            "reason": f"inference error: {e}",
        }


def get_buffer_size(camera_id: str) -> int:
    """Helper buat debugging — cek seberapa penuh buffer-nya."""
    with _buffer_lock:
        return len(_buffers.get(camera_id, []))