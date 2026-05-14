# ==============================================================================
# Tujuan       : Autentikasi user (login, logout, JWT token)
# Caller       : main.py (router include)
# Dependensi   : app.config (SECRET_KEY, ALGORITHM)
# Main Functions: create_access_token(), get_current_user_from_cookie()
# Side Effects : Set/delete cookie
# ==============================================================================

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import jwt

from app.config import SECRET_KEY, ALGORITHM

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=2)
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
    if form.get("username") == "admin" and form.get("password") == "admin":
        access_token = create_access_token(data={"sub": "admin"})
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="access_token", value=f"Bearer {access_token}", httponly=True
        )
        return response
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"request": request, "error": "Invalid credentials."}
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response
