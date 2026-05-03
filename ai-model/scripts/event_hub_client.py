"""
event_hub_client.py — TDP-43: Publisher wrapper for Azure Event Hub.

Sends pose detection events and bend alerts to the pose-events Event Hub.
All sends run in background threads to never block the 30 FPS detection loop.
Failures are logged but never raised — Event Hub outage must not crash the AI.
"""

import os
import json
import threading
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
from azure.eventhub import EventHubProducerClient, EventData
from azure.eventhub.exceptions import EventHubError

SCHEMA_VERSION = "1.0"

_env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_env_path)

_connection_string = os.getenv("EVENTHUB_CONNECTION_STRING")
_producer = None


def init_publisher() -> bool:
    """Open the Event Hub producer connection. Call once at startup."""
    global _producer

    if not _connection_string:
        logger.warning("EVENTHUB_CONNECTION_STRING not set — publisher disabled")
        return False

    try:
        _producer = EventHubProducerClient.from_connection_string(_connection_string)
        logger.success("Event Hub publisher initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Event Hub publisher: {e}")
        _producer = None
        return False


def close_publisher() -> None:
    """Close the producer connection cleanly. Call once at shutdown."""
    global _producer
    if _producer is None:
        return
    try:
        _producer.close()
        logger.info("Event Hub publisher closed")
    except Exception as e:
        logger.error(f"Error closing Event Hub publisher: {e}")
    finally:
        _producer = None


def _build_envelope(event_type: str, event_id: str, payload: dict) -> dict:
    """Wrap a payload in the standard event envelope."""
    return {
        "event_type":     event_type,
        "schema_version": SCHEMA_VERSION,
        "event_id":       event_id,
        "session_id":     payload.get("session_id"),
        "frame_index":    payload.get("frame_index"),
        "timestamp":      payload.get("timestamp"),
        "camera_id":      payload.get("camera_id", "webcam-01"),
        "payload":        payload,
    }


def _send_in_background(envelope: dict) -> None:
    """Send one event in a background thread. Never raises."""
    if _producer is None:
        return

    try:
        body = json.dumps(envelope)
        batch = _producer.create_batch()
        batch.add(EventData(body))
        _producer.send_batch(batch)
    except EventHubError as e:
        logger.error(f"Event Hub send failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected publish error: {e}")


def publish_detection_event(detection: dict) -> None:
    """Publish a detection event to Event Hub (non-blocking)."""
    if _producer is None:
        return

    event_id = f"{detection['session_id']}_{detection['frame_index']}_detection"
    envelope = _build_envelope("detection", event_id, detection)

    thread = threading.Thread(
        target=_send_in_background,
        args=(envelope,),
        daemon=True,
    )
    thread.start()


def publish_alert_event(alert: dict) -> None:
    """Publish an alert event to Event Hub (non-blocking)."""
    if _producer is None:
        return

    event_id = alert.get("alert_id", f"{alert['session_id']}_{alert['frame_index']}_alert")
    envelope = _build_envelope("alert", event_id, alert)

    thread = threading.Thread(
        target=_send_in_background,
        args=(envelope,),
        daemon=True,
    )
    thread.start()
    logger.success(f"Alert queued to Event Hub: {event_id}")