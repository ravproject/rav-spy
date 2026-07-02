"""
Webcam Surveillance — motion detection, interval capture, timelapse.
Extends agent/webcam.py and agent/guard.py.
"""
import os
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime
from loguru import logger

_motion_active = False
_interval_active = False
_motion_task = None
_interval_task = None
_capture_dir = Path.home() / ".config" / "rav-spy" / "webcam_captures"


async def _motion_loop(alert_callback, sensitivity: int = 5):
    """Motion detection loop using OpenCV."""
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV not installed")
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return

    ret, prev_frame = cap.read()
    if not ret:
        cap.release()
        return

    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.GaussianBlur(prev_gray, (21, 21), 0)

    while _motion_active:
        ret, frame = cap.read()
        if not ret:
            await asyncio.sleep(0.1)
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        diff = cv2.absdiff(prev_gray, gray)
        thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_detected = False
        for contour in contours:
            if cv2.contourArea(contour) < 500 * sensitivity:
                continue
            motion_detected = True
            break

        if motion_detected:
            _capture_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = _capture_dir / f"motion_{ts}.jpg"
            cv2.imwrite(str(path), frame)
            logger.info(f"Motion detected: {path}")
            if alert_callback:
                await alert_callback(str(path))
            await asyncio.sleep(2)

        prev_gray = gray
        await asyncio.sleep(0.3)

    cap.release()


async def _interval_loop(interval_seconds: int, total_shots: int):
    """Capture webcam photo at regular interval."""
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV not installed")
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return

    shots = 0
    while _interval_active and shots < total_shots:
        ret, frame = cap.read()
        if ret:
            _capture_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = _capture_dir / f"interval_{ts}.jpg"
            cv2.imwrite(str(path), frame)
            shots += 1
        await asyncio.sleep(interval_seconds)

    cap.release()
    return shots


async def motion_start(sensitivity: int = 5, callback=None):
    global _motion_active, _motion_task
    if _motion_active:
        return "Motion detection sudah aktif."

    _motion_active = True
    _motion_task = asyncio.create_task(_motion_loop(callback, sensitivity))
    return f"Webcam motion detection started (sensitivity: {sensitivity})."


async def motion_stop():
    global _motion_active, _motion_task
    _motion_active = False
    if _motion_task:
        _motion_task.cancel()
        _motion_task = None
    return "Motion detection stopped."


async def interval_start(seconds: int = 10, count: int = 10):
    global _interval_active, _interval_task
    if _interval_active:
        return "Interval capture sudah aktif."

    _interval_active = True
    _interval_task = asyncio.create_task(_interval_loop(seconds, count))
    return f"Interval capture: {count} photos every {seconds}s."


async def interval_stop():
    global _interval_active, _interval_task
    _interval_active = False
    if _interval_task:
        _interval_task.cancel()
        _interval_task = None
    return "Interval capture stopped."
