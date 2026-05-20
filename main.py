# ==============================================================================
# Tujuan       : Entry point aplikasi Sistem Deteksi Kebakaran
#                Import semua router dari app/ dan start FastAPI
# Caller       : uvicorn (CLI)
# Dependensi   : app.auth, app.sensor, app.websocket_handler, app.chatbot,
#                app.pdf_export, app.ai_engine, app.camera, app.config
# Main Functions: lifespan(), app
# Side Effects : Load AI models, start kamera, load chatbot
# ==============================================================================

import os
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# --- Suppress noisy logs ---
os.environ["OPENCV_LOG_LEVEL"] = "FATAL"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
warnings.filterwarnings("ignore")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown lifecycle."""
    # --- STARTUP ---
    from app.ai_engine import load_models
    from app.chatbot import load_chatbot
    from app.camera import camera_manager
    from app.config import get_cameras

    print("=" * 50)
    print("🔥 Sistem Deteksi Kebakaran - Starting...")
    print("=" * 50)

    # 1. Load AI Models (YOLO + XGBoost)
    load_models()

    # 2. Load Chatbot (SLM + ChromaDB)
    load_chatbot()

    from app.lstm_anomaly import load_lstm_model
    load_lstm_model()

    # 2b. Init feedback DB (Sprint 4)
    from app.feedback import init_db as init_feedback_db
    init_feedback_db()

    # 3. Start kamera dari konfigurasi tersimpan
    cameras = get_cameras()
    if cameras:
        camera_manager.sync_with_config(cameras)
        print(f"[Startup] {len(cameras)} kamera dimulai")
    else:
        print("[Startup] Belum ada kamera dikonfigurasi. Tambah via dashboard.")

    print("=" * 50)
    print("✅ Sistem siap! Jalankan server via: uvicorn main:app --reload")
    print("=" * 50)

    yield

    # --- SHUTDOWN ---
    camera_manager.stop_all()
    print("[Shutdown] Semua kamera dihentikan.")


# --- Inisialisasi FastAPI ---
app = FastAPI(
    title="PBL Sem 6 - Sistem Deteksi Kebakaran",
    lifespan=lifespan,
)

# === Production Middleware ===
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.security import SecurityHeadersMiddleware

_ENV = os.getenv("ENVIRONMENT", "development").lower()
_ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

if _ENV == "production":
    # 1. Reject request dengan Host header asing
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS)

    # 2. Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. CORS — restrict ke domain sendiri
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"https://{h}" for h in _ALLOWED_HOSTS if "." in h],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    print(f"[Startup] Production mode aktif. Allowed hosts: {_ALLOWED_HOSTS}")

# --- Static Files ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Include Routers ---
from app.auth import router as auth_router
from app.sensor import router as sensor_router
from app.websocket_handler import router as ws_router
from app.chatbot import router as chat_router
from app.pdf_export import router as pdf_router
from app.feedback import router as feedback_router

app.include_router(auth_router)
app.include_router(sensor_router)
app.include_router(ws_router)
app.include_router(chat_router)
app.include_router(pdf_router)
app.include_router(feedback_router)