# ==============================================================================
# Tujuan       : AI Engine - YOLO inference, sensor prediction, decision fusion
#                Model v3: multi-class (Clean/Smoke/Gasoline/Mixture)
#                Pipeline: RAW ADC → PPM → Model (training & inference pakai PPM)
# Caller       : app.websocket_handler
# Dependensi   : ultralytics (YOLO), joblib, numpy, cv2, app.config
# Main Functions: predict_yolo(), predict_sensor(), decision_fusion(),
#                 get_ppm_display(), raw_adc_to_ppm(), capture_anomaly()
# Side Effects : Load model files dari disk saat import
# ==============================================================================

import os
import math
import time
import warnings
import numpy as np
import joblib
import cv2

from app.config import YOLO_MODEL_PATH, XGBOOST_MODEL_PATH, get_thresholds

# Suppress sklearn version warning
try:
    from sklearn.exceptions import InconsistentVersionWarning
    warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
except ImportError:
    pass

# ==============================================================================
# Label Kelas (harus sama dengan urutan saat training)
# ==============================================================================
CLASS_NAMES = ["Clean", "Gasoline", "Mixture", "Smoke"]

# ==============================================================================
# Konversi RAW ADC → PPM (untuk display + input model)
# Tanpa kalibrasi manual — model yang mengklasifikasi murni.
# PPM = a * (voltage_ratio)^b langsung dari kurva datasheet.
# ==============================================================================
VCC_SENSOR = 5.0
VCC_ADC = 3.3
ADC_MAX = 4095.0

SENSOR_CURVES = {
    "mq4":  {"a": 1012.7, "b": -2.786, "label": "Metana (CH₄)"},
    "mq7":  {"a": 99.042, "b": -1.518, "label": "CO"},
    "mq5":  {"a": 1000.5, "b": -2.186, "label": "LPG"},
    "mq135": {"a": 110.47, "b": -2.862, "label": "Kualitas Udara"},
    "mq2":  {"a": 574.25, "b": -2.222, "label": "Gas Mudah Terbakar"},
    "mq3":  {"a": 0.3934, "b": -1.504, "label": "Alkohol"},
}


def raw_adc_to_ppm(sensor_key: str, raw_adc: float) -> float:
    """
    Konversi RAW ADC → PPM murni dari kurva datasheet.
    PPM = a * (voltage_ratio)^b
    Voltage ratio dipakai langsung sebagai proxy Rs/Ro.
    Tidak ada kalibrasi manual — model yang mengklasifikasi.
    """
    if sensor_key not in SENSOR_CURVES:
        return 0.0
    if raw_adc <= 0:
        raw_adc = 1
    if raw_adc >= ADC_MAX:
        raw_adc = ADC_MAX - 1

    vout = (raw_adc / ADC_MAX) * VCC_ADC
    voltage_ratio = (VCC_SENSOR - vout) / vout  # Proporsional Rs/RL

    a = SENSOR_CURVES[sensor_key]["a"]
    b = SENSOR_CURVES[sensor_key]["b"]

    try:
        ppm = a * math.pow(voltage_ratio, b)
    except (ValueError, OverflowError):
        ppm = 0.0

    return max(0.0, ppm)


def get_ppm_display(sensor_data: dict) -> dict:
    """
    Konversi semua sensor RAW ADC → PPM untuk tampilan frontend.

    Return: {
        "mq4":  {"ppm": 12.5, "label": "Metana (CH₄)"},
        "mq5":  {"ppm": 3.2,  "label": "LPG"},
        ...
    }
    """
    result = {}
    for key in ["mq4", "mq5", "mq135", "mq2", "mq7", "mq3"]:
        raw = sensor_data.get(key, 0)
        ppm = raw_adc_to_ppm(key, raw) if raw > 0 else 0.0
        label = SENSOR_CURVES.get(key, {}).get("label", key.upper())
        result[key] = {"ppm": round(ppm, 2), "raw": raw, "label": label}
    return result


# ==============================================================================
# Load Models
# ==============================================================================
yolo_model = None
sensor_model = None
scaler = None

SCALER_PATH = "models/scaler.pkl"


def load_models():
    """Load YOLO, Sensor Model, dan Scaler. Dipanggil saat startup."""
    global yolo_model, sensor_model, scaler

    # YOLO
    try:
        from ultralytics import YOLO
        if os.path.exists(YOLO_MODEL_PATH):
            yolo_model = YOLO(YOLO_MODEL_PATH)
            print(f"[AI] YOLOv11 loaded: {YOLO_MODEL_PATH}")
        else:
            print(f"[AI] YOLO model tidak ditemukan: {YOLO_MODEL_PATH}")
    except Exception as e:
        print(f"[AI] Error loading YOLO: {e}")

    # Sensor model (RF/XGBoost)
    try:
        if os.path.exists(XGBOOST_MODEL_PATH):
            sensor_model = joblib.load(XGBOOST_MODEL_PATH)
            print(f"[AI] Sensor model loaded: {XGBOOST_MODEL_PATH}")
            if hasattr(sensor_model, 'classes_'):
                print(f"[AI] Classes: {sensor_model.classes_}")
        elif os.path.exists("models/fire_detection_rf.pkl"):
            sensor_model = joblib.load("models/fire_detection_rf.pkl")
            print("[AI] Fallback: fire_detection_rf.pkl loaded")
        else:
            print("[AI] Tidak ada model sensor ditemukan")
    except Exception as e:
        print(f"[AI] Error loading sensor model: {e}")

    # Scaler
    try:
        if os.path.exists(SCALER_PATH):
            scaler = joblib.load(SCALER_PATH)
            print(f"[AI] Scaler loaded: {SCALER_PATH}")
        else:
            print(f"[AI] Scaler tidak ditemukan: {SCALER_PATH}")
    except Exception as e:
        print(f"[AI] Error loading scaler: {e}")

    # Buat folder captures
    os.makedirs("static/captures", exist_ok=True)


# ==============================================================================
# Prediction Functions
# ==============================================================================

def predict_yolo(frame) -> dict:
    """
    Jalankan YOLO pada frame kamera.

    Return: {
        "confidence": 85.2,      # Confidence tertinggi (0-100)
        "detections": [           # Semua deteksi
            {"class": "fire", "confidence": 85.2, "bbox": [x1,y1,x2,y2]},
            ...
        ]
    }
    """
    if yolo_model is None or frame is None:
        return {"confidence": 0.0, "detections": []}
    try:
        results = yolo_model.predict(frame, verbose=False)
        detections = []
        max_conf = 0.0
        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    conf = float(box.conf[0]) * 100
                    cls_id = int(box.cls[0])
                    cls_name = r.names.get(cls_id, str(cls_id))
                    bbox = box.xyxy[0].tolist()
                    detections.append({
                        "class": cls_name,
                        "confidence": round(conf, 1),
                        "bbox": [round(b) for b in bbox],
                    })
                    if conf > max_conf:
                        max_conf = conf
        return {"confidence": round(max_conf, 1), "detections": detections}
    except Exception as e:
        print(f"[AI] YOLO error: {e}")
        return {"confidence": 0.0, "detections": []}


def predict_sensor(sensor_data: dict) -> dict:
    """
    Prediksi multi-class dari data sensor MQ.

    Pipeline: RAW ADC (ESP32) → PPM (konversi) → Model predict_proba
    Fitur model: [mq4_ppm, mq5_ppm, mq135_ppm, mq2_ppm, mq7_ppm, mq3_ppm]

    Return: {
        "danger_prob": 72.5,
        "detected_class": "Smoke",
        "class_probs": {"Clean": 27.5, "Smoke": 45.0, ...}
    }
    """
    if sensor_model is None:
        return {
            "danger_prob": 0.0,
            "detected_class": "Clean",
            "class_probs": {c: 0.0 for c in CLASS_NAMES}
        }
    try:
        # Step 1: RAW ADC → PPM (urutan HARUS sama dengan training)
        features = np.array([[
            raw_adc_to_ppm("mq4",  sensor_data.get("mq4", 0)),
            raw_adc_to_ppm("mq5",  sensor_data.get("mq5", 0)),
            raw_adc_to_ppm("mq135", sensor_data.get("mq135", 0)),
            raw_adc_to_ppm("mq2",  sensor_data.get("mq2", 0)),
            raw_adc_to_ppm("mq7",  sensor_data.get("mq7", 0)),
            raw_adc_to_ppm("mq3",  sensor_data.get("mq3", 0)),
        ]])

        if scaler is not None:
            features = scaler.transform(features)

        proba = sensor_model.predict_proba(features)[0]
        classes = sensor_model.classes_ if hasattr(sensor_model, 'classes_') else list(range(len(proba)))

        # Map ke nama kelas
        class_probs = {}
        for i, cls_idx in enumerate(classes):
            name = CLASS_NAMES[int(cls_idx)] if int(cls_idx) < len(CLASS_NAMES) else f"Class_{cls_idx}"
            class_probs[name] = round(float(proba[i]) * 100, 1)

        # Pastikan semua kelas ada
        for c in CLASS_NAMES:
            if c not in class_probs:
                class_probs[c] = 0.0

        clean_prob = class_probs.get("Clean", 0.0)
        danger_prob = round(100.0 - clean_prob, 1)

        # Kelas tertinggi (exclude Clean jika danger > 50%)
        if danger_prob > 30:
            non_clean = {k: v for k, v in class_probs.items() if k != "Clean"}
            detected_class = max(non_clean, key=non_clean.get) if non_clean else "Clean"
        else:
            detected_class = "Clean"

        return {
            "danger_prob": danger_prob,
            "detected_class": detected_class,
            "class_probs": class_probs,
        }
    except Exception as e:
        print(f"[AI] Sensor model error: {e}")
        return {
            "danger_prob": 0.0,
            "detected_class": "Clean",
            "class_probs": {c: 0.0 for c in CLASS_NAMES}
        }


# Backward compatibility alias
def predict_xgboost(sensor_data: dict) -> float:
    """Backward compat: return danger_prob saja."""
    result = predict_sensor(sensor_data)
    return result["danger_prob"]


# ==============================================================================
# Decision Fusion & Status
# ==============================================================================

def decision_fusion(yolo_prob: float, sensor_prob: float) -> float:
    """
    Fusi berbobot antara YOLO (kamera) dan Sensor menggunakan bobot dinamis dari config.
    - Jika YOLO confidence >= yolo_threshold → pakai yolo_weight_high
    - Jika YOLO confidence < yolo_threshold  → pakai yolo_weight_low
    - Jika salah satu sumber tidak aktif (0), sumber lain dominan penuh.
    """
    if yolo_prob <= 0 and sensor_prob <= 0:
        return 0.0
    if yolo_prob <= 0:
        return round(sensor_prob, 1)
    if sensor_prob <= 0:
        return round(yolo_prob, 1)

    thresholds = get_thresholds()
    yolo_threshold = thresholds.get("yolo_threshold", 50)
    w_yolo = thresholds.get("yolo_weight_high", 0.7) \
        if yolo_prob >= yolo_threshold \
        else thresholds.get("yolo_weight_low", 0.3)
    w_sensor = round(1.0 - w_yolo, 2)

    return round((yolo_prob * w_yolo) + (sensor_prob * w_sensor), 1)


def get_status_label(prob_akhir: float) -> str:
    """Tentukan label status berdasarkan probabilitas dan threshold."""
    thresholds = get_thresholds()
    if prob_akhir < thresholds.get("prob_aman", 30):
        return "Aman"
    elif prob_akhir < thresholds.get("prob_waspada", 70):
        return "Waspada"
    else:
        return "Bahaya"


# ==============================================================================
# Capture & Annotate
# ==============================================================================

def capture_anomaly(frame, cam_name: str, status: str, yolo_result: dict,
                    sensor_result: dict, prob_akhir: float) -> str | None:
    """
    Simpan frame ke static/captures/ saat anomali terdeteksi.
    Return: path relatif ke file capture, atau None.
    """
    if frame is None or status == "Aman":
        return None

    try:
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # Gambar bounding box YOLO
        for det in yolo_result.get("detections", []):
            x1, y1, x2, y2 = det["bbox"]
            color = (0, 0, 255) if status == "Bahaya" else (0, 165, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"{det['class']} {det['confidence']:.0f}%"
            cv2.putText(annotated, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # Overlay status
        overlay_text = (
            f"{status} | {prob_akhir:.0f}% | "
            f"Gas: {sensor_result.get('detected_class', '?')}"
        )
        cv2.putText(annotated, overlay_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # Simpan
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{cam_name}_{ts}_{status}.jpg"
        filepath = os.path.join("static", "captures", filename)
        cv2.imwrite(filepath, annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return f"/static/captures/{filename}"
    except Exception as e:
        print(f"[AI] Capture error: {e}")
        return None