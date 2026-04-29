"""
api_client.py — Sends detection events and alerts to FastAPI backend
Uses background threads so API calls never block the detection loop
"""

import requests
import threading
from loguru import logger

API_BASE_URL = "http://localhost:8000"


def _post_in_background(url: str, payload: dict):
    """Send HTTP POST in a background thread — never blocks detection."""
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"API error {response.status_code}: {url}")
    except requests.exceptions.ConnectionError:
        logger.warning("API not reachable")
    except Exception as e:
        logger.error(f"API call failed: {e}")


def send_alert(alert: dict, snapshot_path=None):
    """Send alert to backend in background thread."""
    payload = {
        "alert_id":      alert["alert_id"],
        "session_id":    alert["session_id"],
        "frame_index":   alert["frame_index"],
        "timestamp":     alert["timestamp"],
        "camera_id":     alert.get("camera_id", "webcam-01"),
        "person":        alert["person"],
        "object":        alert["object"],
        "severity":      alert["severity"],
        "snapshot_path": str(snapshot_path) if snapshot_path else None,
    }
    thread = threading.Thread(
        target=_post_in_background,
        args=(f"{API_BASE_URL}/api/alerts/", payload),
        daemon=True
    )
    thread.start()
    logger.success(f"Alert queued to API: {alert['alert_id']}")


def send_detection(detection: dict):
    """Send detection to backend in background thread."""
    payload = {
        "session_id":  detection["session_id"],
        "frame_index": detection["frame_index"],
        "timestamp":   detection["timestamp"],
        "camera_id":   detection.get("camera_id", "webcam-01"),
        "class_name":  detection["class_name"],
        "confidence":  detection["confidence"],
        "bbox":        detection["bbox"],
    }
    thread = threading.Thread(
        target=_post_in_background,
        args=(f"{API_BASE_URL}/api/detections/", payload),
        daemon=True
    )
    thread.start()


def check_api_health() -> bool:
    """Check if backend API is running."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=3)
        if response.status_code == 200:
            logger.success("Backend API is reachable")
            return True
        return False
    except requests.exceptions.ConnectionError:
        logger.warning("Backend API not running — offline mode")
        return False