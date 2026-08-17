from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

DEVICE_INDEX = 0
WARMUP_SECONDS = 3.0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
OUTPUT_PATH = Path("ml/outputs/webcam-validation/concealment_test.jpg")


def main() -> int:
    capture = cv2.VideoCapture(DEVICE_INDEX, cv2.CAP_V4L2)
    if not capture.isOpened():
        print(f"cannot open /dev/video{DEVICE_INDEX}", file=sys.stderr)
        return 1
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    print(f"warming up for {WARMUP_SECONDS:.0f} seconds, hold the object in view")
    deadline = time.time() + WARMUP_SECONDS
    frame = None
    while time.time() < deadline:
        ok, latest = capture.read()
        if ok:
            frame = latest
    capture.release()
    if frame is None:
        print("no frame captured", file=sys.stderr)
        return 1
    height, width = frame.shape[:2]
    mean_value = float(frame.mean())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(OUTPUT_PATH), frame):
        print(f"cannot write {OUTPUT_PATH}", file=sys.stderr)
        return 1
    print(f"saved {OUTPUT_PATH} {width}x{height} mean brightness {mean_value:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
