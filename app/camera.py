# ==============================================================================
# Tujuan       : Manager kamera RTSP/ONVIF, ambil frame dari multiple kamera
# Caller       : app.websocket_handler, app.ai_engine
# Dependensi   : cv2, threading, app.config
# Main Functions: CameraManager.start(), .get_frame(), .stop()
# Side Effects : Membuka koneksi RTSP via OpenCV
# ==============================================================================

import cv2
import threading
import time
from typing import Optional
import numpy as np


class CameraStream:
    """Satu koneksi RTSP/kamera yang berjalan di thread terpisah."""

    def __init__(self, cam_id: str, rtsp_url: str):
        self.cam_id = cam_id
        self.rtsp_url = rtsp_url
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._retry_delay = 5  # detik sebelum reconnect

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def _capture_loop(self):
        """Loop utama: buka RTSP → baca frame terus menerus."""
        while self._running:
            cap = None
            try:
                # Buka kamera RTSP (atau webcam jika URL = angka)
                if self.rtsp_url.isdigit():
                    cap = cv2.VideoCapture(int(self.rtsp_url), cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(self.rtsp_url)

                if not cap.isOpened():
                    print(f"[Camera {self.cam_id}] Gagal membuka: {self.rtsp_url}")
                    time.sleep(self._retry_delay)
                    continue

                print(f"[Camera {self.cam_id}] Terhubung: {self.rtsp_url}")

                while self._running:
                    ret, frame = cap.read()
                    if not ret:
                        print(f"[Camera {self.cam_id}] Frame lost, reconnecting...")
                        break
                    with self._lock:
                        self._frame = frame

            except Exception as e:
                print(f"[Camera {self.cam_id}] Error: {e}")
            finally:
                if cap:
                    cap.release()

            if self._running:
                time.sleep(self._retry_delay)


class CameraManager:
    """Mengelola banyak kamera RTSP secara bersamaan."""

    def __init__(self):
        self._streams: dict[str, CameraStream] = {}
        self._lock = threading.Lock()

    def add_camera(self, cam_id: str, rtsp_url: str):
        """Tambah dan start kamera baru."""
        with self._lock:
            if cam_id in self._streams:
                self._streams[cam_id].stop()
            stream = CameraStream(cam_id, rtsp_url)
            self._streams[cam_id] = stream
            stream.start()

    def remove_camera(self, cam_id: str):
        """Stop dan hapus kamera."""
        with self._lock:
            stream = self._streams.pop(cam_id, None)
            if stream:
                stream.stop()

    def get_frame(self, cam_id: str) -> Optional[np.ndarray]:
        """Ambil frame terbaru dari kamera tertentu."""
        with self._lock:
            stream = self._streams.get(cam_id)
        if stream:
            return stream.get_frame()
        return None

    def get_all_camera_ids(self) -> list:
        with self._lock:
            return list(self._streams.keys())

    def stop_all(self):
        """Stop semua kamera."""
        with self._lock:
            for stream in self._streams.values():
                stream.stop()
            self._streams.clear()

    def sync_with_config(self, cameras_config: dict):
        """
        Sinkronkan kamera aktif dengan konfigurasi dari dashboard.
        Tambah kamera baru, hapus yang sudah tidak ada.
        """
        with self._lock:
            config_ids = set()
            for cam_id, cfg in cameras_config.items():
                if cfg.get("enabled", True):
                    config_ids.add(cam_id)
                    if cam_id not in self._streams:
                        stream = CameraStream(cam_id, cfg["rtsp_url"])
                        self._streams[cam_id] = stream
                        stream.start()

            # Hapus kamera yang sudah tidak ada di config
            to_remove = [cid for cid in self._streams if cid not in config_ids]
            for cid in to_remove:
                stream = self._streams.pop(cid)
                stream.stop()


# Singleton global
camera_manager = CameraManager()
