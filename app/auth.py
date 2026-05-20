# ==============================================================================
# Tujuan       : Autentikasi user (login, logout, JWT token) — PRODUCTION VERSION
#                Hardened untuk deployment via Cloudflare Tunnel
# Caller       : main.py (router include)
# Dependensi   : app.config (SECRET_KEY, ALGORITHM), app.security
# Main Functions: create_access_token(), get_current_user_from_cookie()
# Side Effects : Set/delete cookie (secure, httponly, samesite=lax)
# ==============================================================================

import os
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta, timezone
import jwt

from app.config import SECRET_KEY, ALGORITHM
from app.security import authenticate

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Cookie security flags — production HTTPS
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"
COOKIE_SECURE = _IS_PRODUCTION   # Only send over HTTPS in production
COOKIE_SAMESITE = "lax"          # CSRF protection
COOKIE_MAX_AGE = 7200             # 2 jam, match JWT expiry


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=2)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


@router.get("/")
async def get_dashboard(request: Request):
    user = await get_current_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"request": request, "username": user}
    )


@router.get("/login")
async def get_login_page(request: Request):
    user = await get_current_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"request": request}
    )


@router.post("/login")
async def login_process(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""

    if authenticate(username, password):
        access_token = create_access_token(data={"sub": username})
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            httponly=True,                    # JS gak bisa baca
            secure=COOKIE_SECURE,             # HTTPS-only di production
            samesite=COOKIE_SAMESITE,         # CSRF protection
            max_age=COOKIE_MAX_AGE,
            path="/",
        )
        return response

    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"request": request, "error": "Invalid credentials."}
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(
        "access_token",
        path="/",
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )
    return response
