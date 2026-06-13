# app/internal_api.py
# ==============================================================================
# Tujuan : Internal API endpoints untuk chatbot_service — fetch real-time data
#          dari dashboard. Semua di-prefix /api/internal.
# Caller : chatbot_service/chat_tools.py (via httpx), chatbot_service/rag_engine.py
# ==============================================================================

import os
from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import get_sensor_data, get_cameras

router = APIRouter(prefix="/api/internal")

_INTERNAL_TOKEN = os.getenv("DASHBOARD_API_KEY", "")


def _verify(x_internal_token: str = Header(default="")):
    if _INTERNAL_TOKEN and x_internal_token != _INTERNAL_TOKEN:
        raise HTTPException(401, "Invalid internal token")


@router.get("/sensor-snapshot", dependencies=[Depends(_verify)])
async def sensor_snapshot(camera_id: str = None):
    data = get_sensor_data()
    if camera_id:
        return data.get(camera_id, {})
    return data


@router.get("/camera-list", dependencies=[Depends(_verify)])
async def camera_list():
    cameras = get_cameras()
    return [
        {"cam_id": cam_id, "name": cam_cfg.get("name", cam_id), "enabled": cam_cfg.get("enabled", True)}
        for cam_id, cam_cfg in cameras.items()
    ]


@router.get("/lstm-history", dependencies=[Depends(_verify)])
async def lstm_history(camera_id: str = "cam_01", minutes: int = 10):
    try:
        from app.lstm_anomaly import query_score_history
        history = query_score_history(camera_id, minutes)
        return {"camera_id": camera_id, "minutes": minutes, "history": history}
    except Exception as e:
        return {"camera_id": camera_id, "minutes": minutes, "history": [], "error": str(e)}


@router.get("/alert-history", dependencies=[Depends(_verify)])
async def alert_history(limit: int = 10):
    try:
        from app.notification import get_recent_alerts
        alerts = get_recent_alerts(limit)
        return {"alerts": alerts}
    except Exception as e:
        return {"alerts": [], "error": str(e)}


@router.get("/generate-report", dependencies=[Depends(_verify)])
async def generate_report(
    report_type: str = "sensor",   # "sensor" | "incident"
    camera_id: str = "all",
    minutes: int = 60,
    limit: int = 20,
):
    """Generate a DOCX report and return a single-use download URL."""
    from datetime import datetime
    from app.report_router import register_report
    from app.docx_report import generate_sensor_report, generate_incident_report
    from app.config import get_sensor_data

    ts = datetime.now().strftime("%Y%m%d_%H%M")

    try:
        if report_type == "sensor":
            sensor_data = get_sensor_data()
            docx_bytes = generate_sensor_report(sensor_data, camera_id)
            filename = f"Status_Sensor_{ts}.docx"

        elif report_type == "incident":
            try:
                from app.notification import get_recent_alerts
                alerts = get_recent_alerts(limit)
            except Exception:
                alerts = []

            try:
                from app.lstm_anomaly import query_score_history
                cam = camera_id if camera_id != "all" else "cam_01"
                lstm_hist = {"history": query_score_history(cam, minutes)}
            except Exception:
                lstm_hist = {"history": []}

            docx_bytes = generate_incident_report(alerts, lstm_hist, camera_id)
            filename = f"Laporan_Insiden_{ts}.docx"

        else:
            return {"ok": False, "error": f"report_type tidak dikenal: {report_type}. Gunakan 'sensor' atau 'incident'."}

        token, download_url = register_report(docx_bytes, filename)
        return {"ok": True, "token": token, "download_url": download_url, "filename": filename, "report_type": report_type}

    except Exception as e:
        return {"ok": False, "error": f"Gagal generate laporan: {e}"}
