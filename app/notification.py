# ==============================================================================
# Tujuan       : Kirim notifikasi Telegram saat deteksi anomali
# Caller       : app.websocket_handler
# Dependensi   : app.config (TELEGRAM_TOKEN, CHAT_ID, THROTTLE_SECONDS)
# Main Functions: kirim_notifikasi_telegram()
# Side Effects : HTTP call ke Telegram API
# ==============================================================================

import threading
import urllib.request
import urllib.parse
from collections import deque
from datetime import datetime
from typing import List, Dict
from app.config import TELEGRAM_TOKEN, CHAT_ID, THROTTLE_SECONDS

# Throttle per camera_id agar notifikasi tidak spam
_last_sent: dict = {}

# Riwayat alert in-memory (non-persistent) untuk tool query_alert_history
_recent_alerts: deque = deque(maxlen=50)
_alerts_lock = threading.Lock()


def get_recent_alerts(limit: int = 5) -> List[Dict]:
    """Public — ambil N alert terakhir (terbaru dulu). Non-persistent."""
    with _alerts_lock:
        items = list(_recent_alerts)[-limit:]
    return list(reversed(items))


def kirim_notifikasi_telegram(
    camera_name: str, status_alert: str, prob: float,
    sensor_summary: str
):
    """
    Kirim peringatan ke Telegram. Throttle per kamera.
    """
    global _last_sent
    now = datetime.now()

    # Throttle check per kamera
    last_time = _last_sent.get(camera_name)
    if last_time and (now - last_time).total_seconds() < THROTTLE_SECONDS:
        return

    # Catat ke riwayat alert in-memory (untuk tool query_alert_history)
    with _alerts_lock:
        _recent_alerts.append({
            "camera": camera_name,
            "status": status_alert,
            "prob": prob,
            "sensor": sensor_summary,
            "ts": now.isoformat(),
        })

    pesan = (
        f"🚨 PERINGATAN {status_alert.upper()}! 🚨\n\n"
        f"📷 Kamera: {camera_name}\n"
        f"Probabilitas Akhir: {prob}%\n"
        f"Sensor: {sensor_summary}\n"
        f"Waktu: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print(f"[Telegram] Token belum dikonfigurasi. Pesan: {pesan[:80]}...")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": CHAT_ID, "text": pesan}
    ).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            _last_sent[camera_name] = now
    except Exception as e:
        print(f"[Telegram] Gagal mengirim: {e}")
