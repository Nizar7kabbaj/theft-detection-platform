from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

DEFAULT_DEVICE = "/dev/v4l/by-id/usb-046d_C922_Pro_Stream_Webcam_3521BF9F-video-index0"
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720


def capture(device: str, delay: float, warmup: float) -> cv2.typing.MatLike | None:
    for remaining in range(int(delay), 0, -1):
        print(f"capturing in {remaining}")
        time.sleep(1)
    stream = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not stream.isOpened():
        print(f"cannot open {device}", file=sys.stderr)
        return None
    stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    stream.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    stream.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    deadline = time.monotonic() + warmup
    frame = None
    while time.monotonic() < deadline:
        ok, latest = stream.read()
        if ok:
            frame = latest
    stream.release()
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--warmup", type=float, default=3.0)
    args = parser.parse_args()

    frame = capture(args.device, args.delay, args.warmup)
    if frame is None:
        print("no frame captured", file=sys.stderr)
        return 1
    height, width = frame.shape[:2]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), frame):
        print(f"cannot write {args.output}", file=sys.stderr)
        return 1
    print(f"saved {args.output} {width}x{height} mean brightness {float(frame.mean()):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
