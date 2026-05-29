# app/chatbot_proxy.py
# ==============================================================================
# Tujuan : Thin proxy ke chatbot_service. Pakai circuit breaker pattern —
#          kalau chatbot service down, request langsung di-reject tanpa nungguin
#          timeout, jadi dashboard tetap responsif.
# Caller : main.py (router include)
# ==============================================================================
import os
import time
import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional

log = logging.getLogger(__name__)

router = APIRouter()

CHATBOT_URL = os.getenv("CHATBOT_SERVICE_URL", "http://localhost:8001")
CHATBOT_TIMEOUT = float(os.getenv("CHATBOT_TIMEOUT", "120"))

# === Circuit breaker state ===
class CircuitBreaker:
    """Simple state machine: CLOSED → OPEN → HALF_OPEN → CLOSED.

    - CLOSED  : normal, request lewat
    - OPEN    : reject langsung (failure threshold tercapai)
    - HALF_OPEN: trial request setelah cooldown
    """
    def __init__(self, fail_threshold: int = 3, cooldown_sec: int = 30):
        self.fail_threshold = fail_threshold
        self.cooldown_sec = cooldown_sec
        self.fail_count = 0
        self.opened_at = 0.0
        self.state = "CLOSED"

    def allow(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.opened_at >= self.cooldown_sec:
                self.state = "HALF_OPEN"
                return True
            return False
        return True  # HALF_OPEN

    def record_success(self):
        self.fail_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.fail_count += 1
        if self.fail_count >= self.fail_threshold:
            self.state = "OPEN"
            self.opened_at = time.time()
            print(f"[CircuitBreaker] OPEN — chatbot service mati. Cooldown {self.cooldown_sec}s")

breaker = CircuitBreaker()

# Reuse client (connection pool)
_client: Optional[httpx.AsyncClient] = None
def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=CHATBOT_URL, timeout=CHATBOT_TIMEOUT)
    return _client


class ChatProxyRequest(BaseModel):
    pertanyaan: str
    history: Optional[List[Dict[str, str]]] = None
    sensor_context: Optional[Dict] = None  # passthrough — chatbot service validate


@router.get("/api/chat/health")
async def chat_health():
    """Frontend bisa cek apakah chatbot tersedia sebelum show widget."""
    if not breaker.allow():
        return {"available": False, "reason": "circuit_open"}
    try:
        resp = await _get_client().get("/health", timeout=3.0)
        return {"available": resp.status_code == 200, **resp.json()}
    except Exception:
        return {"available": False, "reason": "unreachable"}


@router.post("/api/chat")
async def chat_proxy(req: ChatProxyRequest):
    if not breaker.allow():
        raise HTTPException(
            status_code=503,
            detail="Chatbot sedang offline. Dashboard tetap berjalan normal — coba lagi sebentar.",
        )

    # Strip frontend-only sensor fields that are not part of SensorContext schema
    _SENSOR_SCHEMA_FIELDS = {
        "camera_id", "mq2", "mq4", "mq5", "mq7", "mq135",
        "temperature", "humidity", "flame_detected",
    }
    payload = req.model_dump()
    if payload.get("sensor_context") is not None:
        payload["sensor_context"] = {
            k: v for k, v in payload["sensor_context"].items()
            if k in _SENSOR_SCHEMA_FIELDS
        }

    try:
        resp = await _get_client().post("/api/chat", json=payload)
        resp.raise_for_status()
        breaker.record_success()
        return resp.json()
    except httpx.TimeoutException:
        breaker.record_failure()
        raise HTTPException(504, "Chatbot terlalu lama merespons.")
    except httpx.HTTPStatusError as e:
        # 5xx dari chatbot service = service error → trip breaker
        if e.response.status_code >= 500:
            breaker.record_failure()
        log.error("[ChatProxy] chatbot_service %s: %s", e.response.status_code, e.response.text)
        raise HTTPException(e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        breaker.record_failure()
        raise HTTPException(503, f"Chatbot unreachable: {e}")