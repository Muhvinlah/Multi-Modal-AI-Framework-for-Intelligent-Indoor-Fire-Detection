"""
Standalone camera client for remote fire detection system.
Run this script on any external laptop with a webcam.
Sends frames to the server at https://firedetection.my.id/api/camera-frame

Usage:
    pip install -r requirements.txt
    python camera_client.py
"""

import time
import sys

import cv2
import requests

SERVER_URL = "https://firedetection.my.id/api/camera-frame"
FPS_INTERVAL = 0.1  # ~10 FPS
JPEG_QUALITY = 70
RESOLUTION = (640, 480)


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam. Check that camera index 0 is available.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])

    print(f"[INFO] Camera opened at {RESOLUTION[0]}x{RESOLUTION[1]}")
    print(f"[INFO] Sending frames to {SERVER_URL}")
    print("[INFO] Press Ctrl+C to stop.")

    frame_count = 0

    try:
        while True:
            loop_start = time.time()

            ret, frame = cap.read()
            if not ret:
                print("[WARN] Failed to read frame from webcam, retrying...")
                time.sleep(FPS_INTERVAL)
                continue

            ok, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            if not ok:
                print("[WARN] Failed to encode frame, skipping...")
                continue

            try:
                resp = requests.post(
                    SERVER_URL,
                    files={"frame": ("frame.jpg", buf.tobytes(), "image/jpeg")},
                    timeout=5,
                )
                frame_count += 1
                print(
                    f"[OK] Frame #{frame_count} sent — "
                    f"server: {resp.status_code} {resp.json().get('message', '')}"
                )
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] POST failed: {e}")

            elapsed = time.time() - loop_start
            sleep_time = max(0.0, FPS_INTERVAL - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[INFO] Stopping camera client.")
    finally:
        cap.release()
        print("[INFO] Camera released.")


if __name__ == "__main__":
    main()
