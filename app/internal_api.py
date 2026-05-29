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


@router.get("/rag-retrieve", dependencies=[Depends(_verify)])
async def rag_retrieve(query: str):
    """Sprint 1: delegate ke app.rag_engine yang sudah ada di dashboard."""
    try:
        from app.rag_engine import retrieve
        result = retrieve(query)
        return {"context": result.get("context", ""), "sources": result.get("chunks", [])}
    except Exception as e:
        return {"context": "", "sources": [], "error": str(e)}
