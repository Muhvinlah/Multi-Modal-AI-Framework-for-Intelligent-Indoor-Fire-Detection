# ==============================================================================
# Tujuan       : Export riwayat sensor ke CSV
# Caller       : main.py (router include), frontend
# Dependensi   : csv (stdlib)
# Main Functions: GET /api/download-history
# Side Effects : Buat file CSV sementara
# ==============================================================================

import csv
import os
import tempfile
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse

from app.config import get_sensor_data, get_cameras

router = APIRouter()


@router.get("/api/download-history")
async def download_history(background_tasks: BackgroundTasks):
    """Generate dan download CSV laporan sensor dengan data real."""
    now = datetime.now()

    headers = [
        "Timestamp", "Camera ID", "Camera Name",
        "MQ-2 Raw", "MQ-2 PPM", "MQ-3 Raw", "MQ-3 PPM",
        "MQ-4 Raw", "MQ-4 PPM", "MQ-5 Raw", "MQ-5 PPM",
        "MQ-7 Raw", "MQ-7 PPM", "MQ-135 Raw", "MQ-135 PPM",
        "Temperature (C)", "Humidity (%)", "Flame Detected",
        "Detected Class", "Sensor Danger Prob (%)",
    ]

    cameras = get_cameras()
    rows = []

    for cam_id, cam_cfg in cameras.items():
        sensor = get_sensor_data(cam_id)
        raw = sensor.get("raw", {}) if isinstance(sensor, dict) else {}
        ppm = sensor.get("ppm", {}) if isinstance(sensor, dict) else {}

        # Fallback: top-level keys if raw/ppm nested structure not present
        def _raw(key):
            return raw.get(key, sensor.get(f"{key}_raw", ""))

        def _ppm(key):
            v = ppm.get(key)
            if isinstance(v, dict):
                return v.get("ppm", "")
            return v if v is not None else sensor.get(f"{key}_ppm", "")

        rows.append([
            now.strftime("%Y-%m-%d %H:%M:%S"),
            cam_id,
            cam_cfg.get("name", cam_id),
            _raw("mq2"),   _ppm("mq2"),
            _raw("mq3"),   _ppm("mq3"),
            _raw("mq4"),   _ppm("mq4"),
            _raw("mq5"),   _ppm("mq5"),
            _raw("mq7"),   _ppm("mq7"),
            _raw("mq135"), _ppm("mq135"),
            sensor.get("temperature", ""),
            sensor.get("humidity", ""),
            sensor.get("flame_detected", ""),
            sensor.get("detected_class", ""),
            sensor.get("danger_prob", ""),
        ])

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8-sig"
    )
    writer = csv.writer(tmp)
    writer.writerow(headers)
    writer.writerows(rows)
    tmp.close()

    background_tasks.add_task(os.unlink, tmp.name)

    return FileResponse(
        path=tmp.name,
        media_type="text/csv; charset=utf-8",
        filename=f"Laporan_Sensor_{now.strftime('%Y%m%d_%H%M')}.csv",
    )
