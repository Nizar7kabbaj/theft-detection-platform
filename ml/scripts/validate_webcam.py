from __future__ import annotations
import argparse
import subprocess
import time
from pathlib import Path
import cv2


REQUEST_W, REQUEST_H, REQUEST_FPS = 1920, 1080, 30
BURST_FRAMES = 150  # ~5s at 30FPS
SAVE_FRAME_AT = 75
OUTPUT_DIR = Path("ai-model/outputs/webcam-validation")
C922_DEVICE = "/dev/video2"


def set_c922_exposure(mode: str) -> None:
    if mode == "manual":
        subprocess.run(
            ["v4l2-ctl", f"--device={C922_DEVICE}",
             "--set-ctrl=auto_exposure=1"], check=False)
        subprocess.run(
            ["v4l2-ctl", f"--device={C922_DEVICE}",
             "--set-ctrl=exposure_time_absolute=200"], check=False)
    elif mode == "auto":
        subprocess.run(
            ["v4l2-ctl", f"--device={C922_DEVICE}",
             "--set-ctrl=auto_exposure=3"], check=False)
    else:
        raise ValueError(f"unknown exposure mode: {mode}")


def probe_index(index: int, output_dir: Path) -> dict:
    result = {
        "index": index,
        "opened": False,
        "fourcc_set": False,
        "actual_w": None,
        "actual_h": None,
        "actual_fourcc": None,
        "measured_fps": None,
        "frames_captured": 0,
        "saved_to": None,
        "notes": "",
    }

    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        result["notes"] = "VideoCapture.isOpened() returned False"
        return result

    result["opened"] = True

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    result["fourcc_set"] = cap.set(cv2.CAP_PROP_FOURCC, fourcc)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, REQUEST_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, REQUEST_H)
    cap.set(cv2.CAP_PROP_FPS, REQUEST_FPS)

    result["actual_w"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    result["actual_h"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
    result["actual_fourcc"] = "".join(
        chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4)
    )

    for _ in range(10):
        cap.read()

    start = time.perf_counter()
    saved_path = None
    for i in range(BURST_FRAMES):
        ok, frame = cap.read()
        if not ok:
            result["notes"] = f"frame {i} read failed"
            break
        result["frames_captured"] += 1
        if i == SAVE_FRAME_AT:
            output_dir.mkdir(parents=True, exist_ok=True)
            saved_path = output_dir / f"opencv_index_{index}.jpg"
            cv2.imwrite(str(saved_path), frame)
            result["saved_to"] = str(saved_path)
    elapsed = time.perf_counter() - start

    if result["frames_captured"] > 0:
        result["measured_fps"] = result["frames_captured"] / elapsed

    cap.release()
    return result


def print_row(r: dict) -> None:
    if not r["opened"]:
        print(f"  index {r['index']}: NOT OPENED ({r['notes']})")
        return
    fps_str = f"{r['measured_fps']:.1f}" if r["measured_fps"] else "n/a"
    print(
        f"  index {r['index']}: opened=YES "
        f"format={r['actual_fourcc']} "
        f"resolution={r['actual_w']}x{r['actual_h']} "
        f"frames={r['frames_captured']}/{BURST_FRAMES} "
        f"measured_fps={fps_str} "
        f"saved={r['saved_to'] or 'none'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-index", type=int, default=4,
        help="Probe indices 0..max-index-1 (default 4 = video0..video3)",
    )
    parser.add_argument(
        "--manual-exposure", action="store_true",
        help="Force C922 manual exposure (short fixed) to bypass the "
             "exposure_dynamic_framerate cap. Used to test hardware FPS "
             "ceiling. Auto-exposure is restored before exit.",
    )
    args = parser.parse_args()

    if args.manual_exposure:
        print("Mode: MANUAL EXPOSURE (hardware FPS ceiling test)")
        set_c922_exposure("manual")
    else:
        print("Mode: AUTO EXPOSURE (operational FPS, matches detect_alert.py)")

    print(f"Requesting: {REQUEST_W}x{REQUEST_H} MJPG {REQUEST_FPS} FPS")
    print(f"Burst: {BURST_FRAMES} frames per index after 10-frame warm-up")
    print(f"Output dir: {OUTPUT_DIR}")
    print()
    print("Results:")
    try:
        for idx in range(args.max_index):
            r = probe_index(idx, OUTPUT_DIR)
            print_row(r)
    finally:
        if args.manual_exposure:
            set_c922_exposure("auto")
            print()
            print("(C922 auto-exposure restored)")
    print()
    print("Visual confirmation: open each opencv_index_N.jpg to identify")
    print("which physical camera corresponds to which OpenCV index.")


if __name__ == "__main__":
    main()
