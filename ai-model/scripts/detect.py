"""
detect.py — Phase 1 theft detection script
Runs YOLOv8 on an image, video file, or webcam.
Saves annotated output and a JSON log of detections.
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
    76: "scissors",
    77: "teddy bear",
}

CONFIDENCE_THRESHOLD = 0.5

OUTPUT_DIR = Path("ai-model/outputs/detections")
LOG_DIR    = Path("ai-model/outputs/logs")

# ── Helper functions ────────────────────────────────────────────────────────────

def setup_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_model():
    logger.info("Loading YOLOv8 model...")
    model = YOLO("yolov8n.pt")
    logger.info("Model loaded successfully")
    return model


def is_relevant(class_id):
    return class_id in RELEVANT_CLASSES


def draw_detection(frame, box, class_name, confidence, is_person):
    x1, y1, x2, y2 = map(int, box)
    color = (0, 0, 255) if is_person else (255, 100, 0)

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    label = f"{class_name} {confidence:.0%}"
    (label_w, label_h), _ = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1
    )
    cv2.rectangle(
        frame,
        (x1, y1 - label_h - 8),
        (x1 + label_w + 4, y1),
        color, -1
    )
    cv2.putText(
        frame, label,
        (x1 + 2, y1 - 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6, (255, 255, 255), 1, cv2.LINE_AA
    )
    return frame


def add_status_overlay(frame, frame_count, detection_count, fps):
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], 32), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

    status = f"Frame: {frame_count}  |  Detections: {detection_count}  |  FPS: {fps:.1f}"
    cv2.putText(
        frame, status,
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55, (255, 255, 255), 1, cv2.LINE_AA
    )
    return frame


def process_results(results, frame_index, timestamp):
    detections = []
    result = results[0]

    if result.boxes is None or len(result.boxes) == 0:
        return detections, result.orig_img.copy()

    frame = result.orig_img.copy()

    for box in result.boxes:
        class_id   = int(box.cls[0])
        confidence = float(box.conf[0])

        if not is_relevant(class_id) or confidence < CONFIDENCE_THRESHOLD:
            continue

        class_name = RELEVANT_CLASSES[class_id]
        is_person  = (class_id == 0)
        coords     = box.xyxy[0].tolist()

        detection = {
            "frame_index": frame_index,
            "timestamp":   timestamp,
            "class_id":    class_id,
            "class_name":  class_name,
            "confidence":  round(confidence, 4),
            "bbox": {
                "x1": int(coords[0]),
                "y1": int(coords[1]),
                "x2": int(coords[2]),
                "y2": int(coords[3]),
            }
        }
        detections.append(detection)
        frame = draw_detection(frame, coords, class_name, confidence, is_person)

    return detections, frame


# ── Main detection functions ────────────────────────────────────────────────────

def detect_on_image(model, image_path):
    logger.info(f"Running detection on image: {image_path}")

    image_path = Path(image_path)
    if not image_path.exists():
        logger.error(f"Image not found: {image_path}")
        return

    results   = model(str(image_path), verbose=False)
    timestamp = datetime.now().isoformat()
    detections, annotated_frame = process_results(results, 0, timestamp)

    output_path = OUTPUT_DIR / f"detected_{image_path.stem}_{int(time.time())}.jpg"
    cv2.imwrite(str(output_path), annotated_frame)

    log_data = {
        "source":     str(image_path),
        "timestamp":  timestamp,
        "detections": detections,
        "total":      len(detections),
    }
    log_path = LOG_DIR / f"log_{image_path.stem}_{int(time.time())}.json"
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)

    logger.success(f"Detected {len(detections)} objects")
    logger.success(f"Annotated image saved: {output_path}")
    logger.success(f"Detection log saved:   {log_path}")

    cv2.imshow("Detection Result — press any key to close", annotated_frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def detect_on_video(model, source):
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
    source_name = "webcam" if is_webcam else Path(source).stem
    output_path = OUTPUT_DIR / f"detected_{source_name}_{session_id}.mp4"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps_source, (width, height))

    all_detections = []
    frame_count    = 0
    fps_display    = 0.0
    fps_timer      = time.time()

    logger.info("Detection running. Press Q to stop.")

    while True:
        ret, frame = cap.read()
        if not ret:
            logger.info("End of video reached")
            break

        frame_count += 1
        timestamp   = datetime.now().isoformat()
        results     = model(frame, verbose=False)
        detections, annotated_frame = process_results(results, frame_count, timestamp)
        all_detections.extend(detections)

        if frame_count % 10 == 0:
            elapsed     = time.time() - fps_timer
            fps_display = 10 / elapsed if elapsed > 0 else 0
            fps_timer   = time.time()

        annotated_frame = add_status_overlay(
            annotated_frame, frame_count, len(all_detections), fps_display
        )

        writer.write(annotated_frame)
        cv2.imshow("Theft Detection — press Q to stop", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            logger.info("Stopped by user")
            break

    cap.release()
    writer.release()
    cv2.destroyAllWindows()

    log_data = {
        "source":           str(source),
        "session_id":       session_id,
        "total_frames":     frame_count,
        "total_detections": len(all_detections),
        "detections":       all_detections,
    }
    log_path = LOG_DIR / f"log_{source_name}_{session_id}.json"
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)

    logger.success(f"Done: {frame_count} frames, {len(all_detections)} detections")
    logger.success(f"Output video: {output_path}")
    logger.success(f"Log file:     {log_path}")


# ── Entry point ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Theft Detection — Phase 1")
    parser.add_argument(
        "--source",
        default="0",
        help="'0' for webcam, path to image, or path to video"
    )
    args = parser.parse_args()

    setup_directories()
    model  = load_model()
    source = args.source

    if source.isdigit():
        detect_on_video(model, int(source))
    elif source.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
        detect_on_image(model, source)
    else:
        detect_on_video(model, source)


if __name__ == "__main__":
    main()