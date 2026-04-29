"""
detect_alert.py — Phase 1 Step 2
Adds alert logic to detection:
- Detects when a person is close to an object
- Saves snapshot on alert
- Logs alerts to separate JSON file
"""

import cv2
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from ultralytics import YOLO
from loguru import logger

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

# Only these classes trigger an alert when near a person
SUSPICIOUS_OBJECTS = {24, 25, 26, 28, 39, 63, 67}

CONFIDENCE_THRESHOLD = 0.5

# How much two boxes must overlap to trigger alert (0.0 to 1.0)
# 0.0 = just touching is enough
# 0.3 = must overlap 30%
OVERLAP_THRESHOLD = 0.0

# Minimum seconds between two alerts (avoid spam)
ALERT_COOLDOWN = 3.0

# Output directories
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
    logger.info("Model loaded successfully")
    return model

# ── Geometry helpers ───────────────────────────────────────────────────────────

def get_box_area(box):
    """Calculate area of a bounding box."""
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def get_intersection_area(box_a, box_b):
    """Calculate the overlapping area between two boxes."""
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
    """
    Calculate IoU (Intersection over Union) between two boxes.
    IoU = 0.0 means no overlap at all
    IoU = 1.0 means perfect overlap
    """
    intersection = get_intersection_area(box_a, box_b)
    if intersection == 0:
        return 0.0

    area_a = get_box_area(box_a)
    area_b = get_box_area(box_b)
    union  = area_a + area_b - intersection

    return intersection / union if union > 0 else 0.0


def boxes_are_close(box_a, box_b, expand_px=60):
    """
    Check if two boxes are close to each other.
    We expand box_a by expand_px pixels in all directions
    then check if it intersects with box_b.
    This catches cases where person is near but not touching the object.
    """
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
    """Draw a red alert banner at the bottom of the frame."""
    h, w = frame.shape[:2]

    # Red banner at bottom
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
    """
    Check if any person is close to any suspicious object.
    Returns list of alert dictionaries.
    """
    alerts = []

    for person in persons:
        for obj in objects:

            # Skip if object is not in suspicious list
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

def detect_with_alerts(model, source):
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

    # Output video writer
    output_path = OUTPUT_DIR / f"alert_{source_name}_{session_id}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps_source, (width, height))

    # Tracking variables
    all_detections = []
    all_alerts     = []
    frame_count    = 0
    fps_display    = 0.0
    fps_timer      = time.time()
    last_alert_time = 0.0

    logger.info("Detection with alerts running. Press Q to stop.")

    while True:
        ret, frame = cap.read()
        if not ret:
            logger.info("End of video")
            break

        frame_count += 1
        timestamp   = datetime.now().isoformat()

        # Run YOLOv8
        results = model(frame, verbose=False)
        result  = results[0]

        # Separate persons and objects
        persons = []
        objects = []
        annotated_frame = frame.copy()
        has_alert = False

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
                    color = (0, 0, 255)  # red for person
                else:
                    objects.append(detection)
                    color = (255, 100, 0)  # blue for object

                all_detections.append({
                    "frame_index": frame_count,
                    "timestamp":   timestamp,
                    **{k: v for k, v in detection.items() if k != "bbox_list"}
                })

                annotated_frame = draw_box(
                    annotated_frame, coords, class_name, confidence, color
                )

        # Check for alerts
        now = time.time()
        if persons and objects and (now - last_alert_time) > ALERT_COOLDOWN:
            frame_alerts = check_alerts(
                persons, objects,
                annotated_frame, frame_count,
                timestamp, session_id
            )

            if frame_alerts:
                has_alert       = True
                last_alert_time = now
                all_alerts.extend(frame_alerts)

                for alert in frame_alerts:
                    logger.warning(
                        f"ALERT [{alert['severity']}] — "
                        f"Person near {alert['object']['class_name']} "
                        f"at frame {frame_count}"
                    )

                    # Draw alert banner
                    annotated_frame = draw_alert_banner(
                        annotated_frame,
                        "person",
                        frame_alerts[0]["object"]["class_name"]
                    )

                    # Save snapshot
                    snapshot_path = SNAPSHOT_DIR / f"alert_{session_id}_{frame_count}.jpg"
                    cv2.imwrite(str(snapshot_path), annotated_frame)
                    logger.info(f"Snapshot saved: {snapshot_path}")

                    # Save individual alert JSON
                    alert_path = ALERT_DIR / f"alert_{alert['alert_id']}.json"
                    with open(alert_path, "w") as f:
                        json.dump(alert, f, indent=2)

        # Update FPS every 10 frames
        if frame_count % 10 == 0:
            elapsed     = time.time() - fps_timer
            fps_display = 10 / elapsed if elapsed > 0 else 0
            fps_timer   = time.time()

        # Add status bar
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

    # Cleanup
    cap.release()
    writer.release()
    cv2.destroyAllWindows()

    # Save full session log
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

    if source.isdigit():
        detect_with_alerts(model, int(source))
    else:
        detect_with_alerts(model, source)


if __name__ == "__main__":
    main()