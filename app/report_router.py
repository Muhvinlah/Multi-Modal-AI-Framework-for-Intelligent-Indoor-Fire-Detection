# app/report_router.py
# ==============================================================================
# Tujuan : Serve generated DOCX reports via single-use token URL
#          Token registry in-memory; files auto-deleted after download or TTL
# Caller : main.py (router include), app/internal_api.py (register_report import)
# ==============================================================================
import os
import time
import threading
from typing import Dict, Tuple, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

router = APIRouter()

# {token: (file_path, created_at_epoch)}
_registry: Dict[str, Tuple[str, float]] = {}
_lock = threading.Lock()

_TTL = 300  # seconds — delete unretrieved files after 5 min


def _evict_expired() -> None:
    now = time.time()
    expired = [tok for tok, (_, ts) in _registry.items() if now - ts > _TTL]
    for tok in expired:
        path, _ = _registry.pop(tok)
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def register_report(docx_bytes: bytes, filename: str) -> Tuple[str, str]:
    """Persist DOCX bytes to a temp file and return (token, download_url)."""
    import tempfile
    import uuid

    _evict_expired()
    token = uuid.uuid4().hex

    tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False, prefix="report_")
    tmp.write(docx_bytes)
    tmp.close()

    with _lock:
        _registry[token] = (tmp.name, time.time())

    return token, f"/api/reports/download/{token}?filename={filename}"


@router.get("/api/reports/download/{token}")
async def download_report(
    token: str,
    background_tasks: BackgroundTasks,
    filename: str = "laporan.docx",
):
    """Single-use download — file is deleted after serving."""
    with _lock:
        entry = _registry.pop(token, None)

    if entry is None:
        raise HTTPException(404, "Laporan tidak ditemukan atau sudah kedaluwarsa (5 menit).")

    path, _ = entry
    if not os.path.exists(path):
        raise HTTPException(404, "File laporan tidak tersedia.")

    background_tasks.add_task(os.unlink, path)

    from fastapi.responses import FileResponse
    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
