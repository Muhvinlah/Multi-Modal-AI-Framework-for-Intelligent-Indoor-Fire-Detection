# ==============================================================================
# Tujuan       : Production security utilities — password hashing, auth helper,
#                security headers middleware untuk Cloudflare Tunnel deployment
# Caller       : app.auth, main.py
# Dependensi   : bcrypt (langsung, tanpa passlib — passlib gak compatible bcrypt 4.1+)
# Main Functions: hash_password(), verify_password(), authenticate(),
#                SecurityHeadersMiddleware
# Side Effects : Baca env vars (ADMIN_USERNAME, ADMIN_PASSWORD_HASH)
# ==============================================================================

import os
import secrets
import bcrypt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


# ==============================================================================
# Password Hashing (bcrypt — langsung, tanpa passlib)
# ==============================================================================

# bcrypt has a hard 72-byte input limit. Passwords longer akan di-truncate.
_BCRYPT_MAX_BYTES = 72


def _prep_password(password: str) -> bytes:
    """Encode + truncate password ke max 72 bytes (bcrypt requirement)."""
    pwd_bytes = password.encode("utf-8")
    return pwd_bytes[:_BCRYPT_MAX_BYTES]


def hash_password(password: str, rounds: int = 12) -> str:
    """
    Hash password pakai bcrypt. Pakai untuk generate hash sekali,
    simpan output ke env var ADMIN_PASSWORD_HASH.

    rounds=12 → ~250ms per hash di CPU modern. Cukup secure, gak terlalu lambat.
    """
    pwd_bytes = _prep_password(password)
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifikasi password plain vs hash. Return False kalau hash invalid."""
    if not hashed:
        return False
    try:
        pwd_bytes = _prep_password(plain)
        return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ==============================================================================
# User Authentication (env-based, single admin for PBL)
# ==============================================================================
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

# Dev fallback flag - production HARUS set ENVIRONMENT=production
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"


def authenticate(username: str, password: str) -> bool:
    """
    Autentikasi admin login.
    Production: pakai ADMIN_PASSWORD_HASH dari env.
    Development: fallback ke admin/admin (KALAU ENVIRONMENT != production).
    """
    if not _IS_PRODUCTION and not ADMIN_PASSWORD_HASH:
        # Dev fallback — only when explicitly not in production
        return username == "admin" and password == "admin"

    if not ADMIN_PASSWORD_HASH:
        # Production tanpa hash = LOCKED OUT (safety)
        print("[Security] ⚠️ ADMIN_PASSWORD_HASH belum di-set di .env.production!")
        return False

    # Timing-safe comparison untuk username (prevent enumeration)
    if not secrets.compare_digest(username, ADMIN_USERNAME):
        # Tetap jalankan verify_password biar timing-nya seragam (constant time)
        verify_password(password, ADMIN_PASSWORD_HASH)
        return False

    return verify_password(password, ADMIN_PASSWORD_HASH)


# ==============================================================================
# Security Headers Middleware
# ==============================================================================
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Tambah security headers ke semua response.
    Aman dipasang di production behind Cloudflare Tunnel.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Limit referrer leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Disable unused features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # Content Security Policy — adjusted untuk Tailwind CDN + inline styles
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob: https:; "
            "media-src 'self' blob:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://cdn.tailwindcss.com https://cdn.jsdelivr.net "
            "https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' "
            "https://cdn.tailwindcss.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "connect-src 'self' wss: ws:; "
            "frame-ancestors 'self';"
        )

        return response


# ==============================================================================
# Cloudflare-aware Client IP Helper
# ==============================================================================
def get_real_client_ip(request: Request) -> str:
    """
    Get real client IP behind Cloudflare Tunnel.
    CF kirim header CF-Connecting-IP (lebih reliable dari X-Forwarded-For).
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip

    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()

    return request.client.host if request.client else "unknown"
