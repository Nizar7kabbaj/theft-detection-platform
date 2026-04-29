import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

"""
detect_alert.py — Phase 1 Step 2 + API Integration
Adds alert logic to detection:
- Detects when a person is close to an object
- Saves snapshot on alert
- Logs alerts to separate JSON file
- Sends alerts and detections to FastAPI backend
"""

import cv2
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from ultralytics import YOLO
from loguru import logger

from api_client import send_alert, send_detection, check_api_health

# ── Configuration ──────────────────────────────────────────────────────────────

RELEVANT_CLASSES = {
    0:  "person",
    24: "backpack",
    25: "umbrella",
    26: "handbag",
    28: "suitcase",
    39: "bottle",
    41: "cup",
    63: "laptop",
    67: "cell phone",
    73: "book",
}

SUSPICIOUS_OBJECTS = {24, 25, 26, 28, 39, 63, 67}

CONFIDENCE_THRESHOLD = 0.5
OVERLAP_THRESHOLD    = 0.0
ALERT_COOLDOWN       = 3.0

OUTPUT_DIR   = Path("ai-model/outputs/detections")
SNAPSHOT_DIR = Path("ai-model/outputs/snapshots")
LOG_DIR      = Path("ai-model/outputs/logs")
ALERT_DIR    = Path("ai-model/outputs/alerts")

# ── Setup ──────────────────────────────────────────────────────────────────────

def setup_directories():
    for d in [OUTPUT_DIR, SNAPSHOT_DIR, LOG_DIR, ALERT_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_model():
    logger.info("Loading YOLOv8 model...")
    model = YOLO("yolov8n.pt")
    model.to("cuda")
    logger.info(f"Model loaded on: {next(model.model.parameters()).device}")
    return model

# ── Geometry helpers ───────────────────────────────────────────────────────────

def get_box_area(box):
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def get_intersection_area(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return (ix2 - ix1) * (iy2 - iy1)


def get_iou(box_a, box_b):
    intersection = get_intersection_area(box_a, box_b)
    if intersection == 0:
        return 0.0
    area_a = get_box_area(box_a)
    area_b = get_box_area(box_b)
    union  = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def boxes_are_close(box_a, box_b, expand_px=60):
    ax1, ay1, ax2, ay2 = box_a
    expanded = (
        ax1 - expand_px,
        ay1 - expand_px,
        ax2 + expand_px,
        ay2 + expand_px
    )
    return get_intersection_area(expanded, box_b) > 0

# ── Drawing helpers ────────────────────────────────────────────────────────────

def draw_box(frame, box, label, confidence, color):
    x1, y1, x2, y2 = map(int, box)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    text = f"{label} {confidence:.0%}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
    cv2.putText(
        frame, text,
        (x1 + 2, y1 - 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6, (255, 255, 255), 1, cv2.LINE_AA
    )
    return frame


def draw_alert_banner(frame, person_label, object_label):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 40), (w, h), (0, 0, 180), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    alert_text = f"ALERT: {person_label} near {object_label}"
    cv2.putText(
        frame, alert_text,
        (10, h - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7, (255, 255, 255), 2, cv2.LINE_AA
    )
    return frame


def add_status_overlay(frame, frame_count, detection_count, alert_count, fps):
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], 32), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
    status = (
        f"Frame: {frame_count}  |  "
        f"Detections: {detection_count}  |  "
        f"Alerts: {alert_count}  |  "
        f"FPS: {fps:.1f}"
    )
    cv2.putText(
        frame, status,
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55, (255, 255, 255), 1, cv2.LINE_AA
    )
    return frame

# ── Alert logic ────────────────────────────────────────────────────────────────

def check_alerts(persons, objects, frame, frame_index, timestamp, session_id):
    alerts = []
    for person in persons:
        for obj in objects:
            if obj["class_id"] not in SUSPICIOUS_OBJECTS:
                continue
            is_close = boxes_are_close(
                person["bbox_list"],
                obj["bbox_list"],
                expand_px=80
            )
            if is_close:
                alert = {
                    "alert_id":    f"{session_id}_{frame_index}_{obj['class_id']}",
                    "session_id":  session_id,
                    "frame_index": frame_index,
                    "timestamp":   timestamp,
                    "person": {
                        "confidence": person["confidence"],
                        "bbox":       person["bbox"],
                    },
                    "object": {
                        "class_name": obj["class_name"],
                        "confidence": obj["confidence"],
                        "bbox":       obj["bbox"],
                    },
                    "severity": "HIGH" if obj["class_id"] in {63, 28} else "MEDIUM"
                }
                alerts.append(alert)
    return alerts

# ── Main detection function ────────────────────────────────────────────────────

def detect_with_alerts(model, source, api_available=False):
    """Run detection with alert logic on webcam or video file."""

    is_webcam = isinstance(source, int)

    if is_webcam:
        logger.info("Opening webcam — press Q to stop...")
        cap = cv2.VideoCapture(source)
    else:
        video_path = Path(str(source))
        if not video_path.exists():
            logger.error(f"Video not found: {video_path}")
            return
        logger.info(f"Opening video: {video_path}")
        cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        logger.error("Could not open video source")
        return

    fps_source  = cap.get(cv2.CAP_PROP_FPS) or 30
    width       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    session_id  = int(time.time())
    source_name = "webcam" if is_webcam else Path(str(source)).stem

    output_path = OUTPUT_DIR / f"alert_{source_name}_{session_id}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps_source, (width, height))

    all_detections  = []
    all_alerts      = []
    frame_count     = 0
    fps_display     = 0.0
    fps_timer       = time.time()
    last_alert_time = 0.0

    logger.info("Detection running. Press Q in video window or Ctrl+C to stop.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.info("End of video")
                break

            frame_count += 1
            timestamp   = datetime.now().isoformat()

            results = model(frame, verbose=False)
            result  = results[0]

            persons         = []
            objects         = []
            annotated_frame = frame.copy()

            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    class_id   = int(box.cls[0])
                    confidence = float(box.conf[0])
                    coords     = box.xyxy[0].tolist()

                    if class_id not in RELEVANT_CLASSES:
                        continue
                    if confidence < CONFIDENCE_THRESHOLD:
                        continue

                    class_name = RELEVANT_CLASSES[class_id]
                    bbox_dict  = {
                        "x1": int(coords[0]),
                        "y1": int(coords[1]),
                        "x2": int(coords[2]),
                        "y2": int(coords[3]),
                    }
                    bbox_list = [
                        int(coords[0]),
                        int(coords[1]),
                        int(coords[2]),
                        int(coords[3])
                    ]

                    detection = {
                        "class_id":   class_id,
                        "class_name": class_name,
                        "confidence": round(confidence, 4),
                        "bbox":       bbox_dict,
                        "bbox_list":  bbox_list,
                    }

                    if class_id == 0:
                        persons.append(detection)
                        color = (0, 0, 255)
                    else:
                        objects.append(detection)
                        color = (255, 100, 0)

                    # Build detection record
                    detection_record = {
                        "session_id":  session_id,
                        "frame_index": frame_count,
                        "timestamp":   timestamp,
                        "camera_id":   "webcam-01",
                        "class_name":  detection["class_name"],
                        "confidence":  detection["confidence"],
                        "bbox":        detection["bbox"],
                    }
                    all_detections.append(detection_record)

                    # Send every 10th detection to API to avoid overload
                    if api_available and frame_count % 10 == 0:
                        send_detection(detection_record)

                    annotated_frame = draw_box(
                        annotated_frame, coords, class_name, confidence, color
                    )

            now = time.time()
            if persons and objects and (now - last_alert_time) > ALERT_COOLDOWN:
                frame_alerts = check_alerts(
                    persons, objects,
                    annotated_frame, frame_count,
                    timestamp, session_id
                )

                if frame_alerts:
                    last_alert_time = now
                    all_alerts.extend(frame_alerts)

                    for alert in frame_alerts:
                        logger.warning(
                            f"ALERT [{alert['severity']}] — "
                            f"Person near {alert['object']['class_name']} "
                            f"at frame {frame_count}"
                        )

                        annotated_frame = draw_alert_banner(
                            annotated_frame,
                            "person",
                            frame_alerts[0]["object"]["class_name"]
                        )

                        # Save snapshot
                        snapshot_path = SNAPSHOT_DIR / f"alert_{session_id}_{frame_count}.jpg"
                        cv2.imwrite(str(snapshot_path), annotated_frame)
                        logger.info(f"Snapshot saved: {snapshot_path}")

                        # Save alert JSON locally
                        alert_path = ALERT_DIR / f"alert_{alert['alert_id']}.json"
                        with open(alert_path, "w") as f:
                            json.dump(alert, f, indent=2)

                        # Send alert to backend API
                        if api_available:
                            send_alert(alert, snapshot_path)

            if frame_count % 10 == 0:
                elapsed     = time.time() - fps_timer
                fps_display = 10 / elapsed if elapsed > 0 else 0
                fps_timer   = time.time()

            annotated_frame = add_status_overlay(
                annotated_frame,
                frame_count,
                len(all_detections),
                len(all_alerts),
                fps_display
            )

            writer.write(annotated_frame)
            cv2.imshow("Theft Detection — press Q to stop", annotated_frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                logger.info("Stopped by user")
                break

    except KeyboardInterrupt:
        logger.info("Stopped by Ctrl+C")

    finally:
        cap.release()
        writer.release()
        cv2.destroyAllWindows()

        session_log = {
            "session_id":       session_id,
            "source":           str(source),
            "total_frames":     frame_count,
            "total_detections": len(all_detections),
            "total_alerts":     len(all_alerts),
            "detections":       all_detections,
            "alerts":           all_alerts,
        }
        log_path = LOG_DIR / f"session_{source_name}_{session_id}.json"
        with open(log_path, "w") as f:
            json.dump(session_log, f, indent=2)

        logger.success(f"Session done — {frame_count} frames, {len(all_alerts)} alerts")
        logger.success(f"Output video:  {output_path}")
        logger.success(f"Session log:   {log_path}")
        logger.success(f"Snapshots in:  {SNAPSHOT_DIR}")

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Theft Detection with Alerts")
    parser.add_argument(
        "--source",
        default="1",
        help="Camera index (0,1,2) or path to video file"
    )
    args   = parser.parse_args()
    source = args.source

    setup_directories()
    model = load_model()

    # Check if backend API is running
    api_available = check_api_health()
    if not api_available:
        logger.warning("Running in offline mode — data saved locally only")

    if source.isdigit():
        detect_with_alerts(model, int(source), api_available)
    else:
        detect_with_alerts(model, source, api_available)


if __name__ == "__main__":
    main()