import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

"""
detect_alert.py — Phase 4 / TDP-32: Pose-based detection
- Uses YOLOv8-pose to extract 17 keypoints per person
- Detects bending posture (torso angle > 60° for 2+ seconds)
- Sends pose data + bend alerts to FastAPI backend
"""

import cv2
import json
import math
import time
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from ultralytics import YOLO
from loguru import logger

from api_client import send_alert, send_detection, check_api_health

# ── Configuration ────────────────────────────────────────────────────────

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle"
]

LEFT_SHOULDER  = 5
RIGHT_SHOULDER = 6
LEFT_HIP       = 11
RIGHT_HIP      = 12

CONFIDENCE_THRESHOLD     = 0.5
KEYPOINT_CONF_THRESHOLD  = 0.5
BEND_ANGLE_THRESHOLD     = 60.0   # degrees from vertical
BEND_DURATION_THRESHOLD  = 2.0    # seconds
ALERT_COOLDOWN           = 3.0

OUTPUT_DIR   = Path("ai-model/outputs/detections")
SNAPSHOT_DIR = Path("ai-model/outputs/snapshots")
LOG_DIR      = Path("ai-model/outputs/logs")
ALERT_DIR    = Path("ai-model/outputs/alerts")


# ── Setup ────────────────────────────────────────────────────────────────

def setup_directories():
    for d in [OUTPUT_DIR, SNAPSHOT_DIR, LOG_DIR, ALERT_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_model():
    logger.info("Loading YOLOv8-pose model...")
    model = YOLO("yolov8n-pose.pt")
    model.to("cuda")
    logger.info(f"Model loaded on: {next(model.model.parameters()).device}")
    return model


# ── Pose helpers ─────────────────────────────────────────────────────────

def extract_keypoints_data(kpts_xy, kpts_conf):
    """Convert YOLO keypoint tensors into a list of 17 dicts."""
    data = []
    for i in range(17):
        x = float(kpts_xy[i][0])
        y = float(kpts_xy[i][1])
        c = float(kpts_conf[i])
        data.append({
            "name":       KEYPOINT_NAMES[i],
            "x":          round(x, 2),
            "y":          round(y, 2),
            "confidence": round(c, 4),
        })
    return data


def compute_torso_angle(kpts_xy, kpts_conf):
    """
    Returns the lean angle from vertical, in degrees.
    Uses nose vs mid-shoulders (works for desk cams and full body).
    0  = head directly above shoulders (upright)
    60+ = leaning forward significantly
    Returns None if keypoints are not visible enough.
    """
    NOSE = 0
    needed = [NOSE, LEFT_SHOULDER, RIGHT_SHOULDER]
    for i in needed:
        if float(kpts_conf[i]) < KEYPOINT_CONF_THRESHOLD:
            return None

    nx = float(kpts_xy[NOSE][0])
    ny = float(kpts_xy[NOSE][1])
    sx = (float(kpts_xy[LEFT_SHOULDER][0]) + float(kpts_xy[RIGHT_SHOULDER][0])) / 2
    sy = (float(kpts_xy[LEFT_SHOULDER][1]) + float(kpts_xy[RIGHT_SHOULDER][1])) / 2

    dx = nx - sx
    dy = sy - ny  # image y grows downward, flip so up = positive
    if dx == 0 and dy == 0:
        return None

    # When upright: nose is above shoulders → dy positive, dx ~0 → angle ~0°
    # When leaning forward: nose moves ahead → dx grows → angle grows
    angle_rad = math.atan2(abs(dx), abs(dy))
    return math.degrees(angle_rad)


# ── Drawing helpers ──────────────────────────────────────────────────────

def draw_alert_banner(frame, label):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 40), (w, h), (0, 0, 180), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    cv2.putText(frame, f"ALERT: {label}", (10, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def add_status_overlay(frame, frame_count, person_count, alert_count, fps):
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], 32), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
    status = (
        f"Frame: {frame_count}  |  "
        f"Persons: {person_count}  |  "
        f"Alerts: {alert_count}  |  "
        f"FPS: {fps:.1f}"
    )
    cv2.putText(frame, status, (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


# ── Main detection loop ──────────────────────────────────────────────────

def detect_with_alerts(model, source, api_available=False):
    is_webcam = isinstance(source, int)

    if is_webcam:
        logger.info("Opening webcam — press Q to stop...")
        cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
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

    output_path = OUTPUT_DIR / f"pose_{source_name}_{session_id}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps_source, (width, height))

    all_detections  = []
    all_alerts      = []
    frame_count     = 0
    fps_display     = 0.0
    fps_timer       = time.time()
    last_alert_time = 0.0

    # Track per-person bend duration. Key = person index in this frame.
    bend_start_time = defaultdict(lambda: None)

    logger.info("Pose detection running. Press Q in video window to stop.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.info("End of video")
                break

            frame_count += 1
            timestamp   = datetime.now().isoformat()
            now         = time.time()

            results         = model(frame, verbose=False)
            result          = results[0]
            annotated_frame = result.plot()  # YOLO draws skeleton automatically

            persons_in_frame = []

            if result.keypoints is not None and result.boxes is not None and len(result.boxes) > 0:
                boxes_xyxy = result.boxes.xyxy.cpu().numpy()
                boxes_conf = result.boxes.conf.cpu().numpy()
                kpts_xy    = result.keypoints.xy.cpu().numpy()
                kpts_conf  = result.keypoints.conf.cpu().numpy() if result.keypoints.conf is not None else None

                for i in range(len(boxes_xyxy)):
                    box_conf = float(boxes_conf[i])
                    if box_conf < CONFIDENCE_THRESHOLD:
                        continue
                    if kpts_conf is None:
                        continue

                    coords  = boxes_xyxy[i].tolist()
                    person_kpts_xy   = kpts_xy[i]
                    person_kpts_conf = kpts_conf[i]

                    bbox_dict = {
                        "x1": int(coords[0]),
                        "y1": int(coords[1]),
                        "x2": int(coords[2]),
                        "y2": int(coords[3]),
                    }

                    keypoints_data = extract_keypoints_data(person_kpts_xy, person_kpts_conf)
                    torso_angle    = compute_torso_angle(person_kpts_xy, person_kpts_conf)

                    person_record = {
                        "session_id":  session_id,
                        "frame_index": frame_count,
                        "timestamp":   timestamp,
                        "camera_id":   "webcam-01",
                        "class_name":  "person",
                        "confidence":  round(box_conf, 4),
                        "bbox":        bbox_dict,
                        "keypoints":   keypoints_data,
                        "torso_angle": round(torso_angle, 2) if torso_angle is not None else None,
                    }
                    persons_in_frame.append(person_record)
                    all_detections.append(person_record)

                    # Send every 10th detection to API (avoid overload)
                    if api_available and frame_count % 10 == 0:
                        send_detection(person_record)

                    # Bend alert tracking per person index
                    if torso_angle is not None and torso_angle >= BEND_ANGLE_THRESHOLD:
                        if bend_start_time[i] is None:
                            bend_start_time[i] = now
                        bend_duration = now - bend_start_time[i]

                        if (bend_duration >= BEND_DURATION_THRESHOLD
                                and (now - last_alert_time) > ALERT_COOLDOWN):
                            last_alert_time = now
                            alert = {
                                "alert_id":    f"{session_id}_{frame_count}_{i}_bend",
                                "session_id":  session_id,
                                "frame_index": frame_count,
                                "timestamp":   timestamp,
                                "camera_id":   "webcam-01",
                                "person": {
                                    "confidence": round(box_conf, 4),
                                    "bbox":       bbox_dict,
                                },
                                "alert_type":  "bending",
                                "severity":    "MEDIUM",
                                "torso_angle": round(torso_angle, 2),
                                "keypoints":   keypoints_data,
                            }
                            all_alerts.append(alert)
                            logger.warning(
                                f"BEND ALERT — person {i} at {torso_angle:.1f}° "
                                f"for {bend_duration:.1f}s (frame {frame_count})"
                            )

                            annotated_frame = draw_alert_banner(
                                annotated_frame,
                                f"person bending {torso_angle:.0f}°"
                            )

                            snapshot_path = SNAPSHOT_DIR / f"alert_{session_id}_{frame_count}.jpg"
                            cv2.imwrite(str(snapshot_path), annotated_frame)
                            logger.info(f"Snapshot saved: {snapshot_path}")

                            alert_path = ALERT_DIR / f"alert_{alert['alert_id']}.json"
                            with open(alert_path, "w") as f:
                                json.dump(alert, f, indent=2)

                            if api_available:
                                send_alert(alert, snapshot_path)
                    else:
                        bend_start_time[i] = None

            # FPS update every 10 frames
            if frame_count % 10 == 0:
                elapsed     = time.time() - fps_timer
                fps_display = 10 / elapsed if elapsed > 0 else 0
                fps_timer   = time.time()

            annotated_frame = add_status_overlay(
                annotated_frame,
                frame_count,
                len(persons_in_frame),
                len(all_alerts),
                fps_display
            )

            writer.write(annotated_frame)
            cv2.imshow("Pose Detection — TDP-32 — press Q to stop", annotated_frame)

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
            "mode":             "pose",
            "total_frames":     frame_count,
            "total_detections": len(all_detections),
            "total_alerts":     len(all_alerts),
            "detections":       all_detections,
            "alerts":           all_alerts,
        }
        log_path = LOG_DIR / f"session_{source_name}_{session_id}.json"
        with open(log_path, "w") as f:
            json.dump(session_log, f, indent=2)

        logger.success(f"Session done — {frame_count} frames, {len(all_alerts)} bend alerts")
        logger.success(f"Output video: {output_path}")
        logger.success(f"Session log:  {log_path}")


# ── Entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pose-based Theft Detection (TDP-32)")
    parser.add_argument("--source", default="1",
                        help="Camera index (0,1,2) or path to video file")
    args   = parser.parse_args()
    source = args.source

    setup_directories()
    model = load_model()

    api_available = check_api_health()
    if not api_available:
        logger.warning("Running in offline mode — data saved locally only")

    if source.isdigit():
        detect_with_alerts(model, int(source), api_available)
    else:
        detect_with_alerts(model, source, api_available)


if __name__ == "__main__":
    main()