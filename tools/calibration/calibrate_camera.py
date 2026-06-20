import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

DEVICE = "/dev/video2"
WIDTH = 1920
HEIGHT = 1080
PATTERN_SIZE = (9, 6)
SQUARE_SIZE_MM = 25.0
TARGET_CAPTURES = 25
ERROR_GATE_PX = 0.5

CAPTURE_DIR = Path(__file__).parent / "output" / "captures"
OUTPUT_FILE = Path(__file__).parent / "output" / "camera_intrinsics.yaml"


def open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {DEVICE}")
    return cap


def run_capture() -> int:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(int(p.stem) for p in CAPTURE_DIR.glob("*.png"))
    counter = existing[-1] + 1 if existing else 0

    cap = open_camera()
    print(f"camera open on {DEVICE} at {WIDTH}x{HEIGHT} mjpg")
    print("space saves a frame when board is detected, q quits")
    print(f"starting at {counter} existing captures, target {TARGET_CAPTURES}")

    detect_flags = (
        cv2.CALIB_CB_ADAPTIVE_THRESH
        + cv2.CALIB_CB_NORMALIZE_IMAGE
        + cv2.CALIB_CB_FAST_CHECK
    )

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("frame grab failed", file=sys.stderr)
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found, corners = cv2.findChessboardCorners(gray, PATTERN_SIZE, flags=detect_flags)

            preview = frame.copy()
            if found:
                cv2.drawChessboardCorners(preview, PATTERN_SIZE, corners, found)

            color = (0, 200, 0) if found else (0, 0, 200)
            status = f"captures {counter}/{TARGET_CAPTURES}  board {'detected' if found else 'not found'}"
            cv2.putText(preview, status, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            cv2.imshow("calibration capture", preview)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            if key == ord(" ") and found:
                path = CAPTURE_DIR / f"{counter:03d}.png"
                cv2.imwrite(str(path), frame)
                counter += 1
                print(f"saved {path.name}")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print(f"session ended, {counter} captures on disk")
    return 0


def run_calibrate() -> int:
    images = sorted(CAPTURE_DIR.glob("*.png"))
    if len(images) < 10:
        print(f"need at least 10 captures, found {len(images)}", file=sys.stderr)
        return 1

    object_template = np.zeros((PATTERN_SIZE[0] * PATTERN_SIZE[1], 3), np.float32)
    object_template[:, :2] = np.mgrid[0:PATTERN_SIZE[0], 0:PATTERN_SIZE[1]].T.reshape(-1, 2)
    object_template *= SQUARE_SIZE_MM

    refine_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    used: list[str] = []

    for path in images:
        img = cv2.imread(str(path))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, PATTERN_SIZE, None)
        if not found:
            print(f"skipping {path.name}: corners not found")
            continue
        refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), refine_criteria)
        object_points.append(object_template)
        image_points.append(refined)
        used.append(path.name)

    if len(object_points) < 10:
        print(f"only {len(object_points)} usable captures, need 10 or more", file=sys.stderr)
        return 1

    print(f"calibrating on {len(object_points)} images")
    rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        object_points, image_points, (WIDTH, HEIGHT), None, None
    )

    per_image: list[tuple[str, float]] = []
    for i, name in enumerate(used):
        projected, _ = cv2.projectPoints(
            object_points[i], rvecs[i], tvecs[i], camera_matrix, dist_coeffs
        )
        err = cv2.norm(image_points[i], projected, cv2.NORM_L2) / np.sqrt(len(projected))
        per_image.append((name, float(err)))

    mean_err = sum(e for _, e in per_image) / len(per_image)
    max_err = max(e for _, e in per_image)

    print("\nper-image reprojection error:")
    for name, err in per_image:
        marker = "  over gate" if err > ERROR_GATE_PX else ""
        print(f"  {name}: {err:.4f} px{marker}")

    print(f"\nmean: {mean_err:.4f} px")
    print(f"max:  {max_err:.4f} px")
    print(f"rms:  {rms:.4f} px")
    print(f"gate: {ERROR_GATE_PX} px")

    if mean_err > ERROR_GATE_PX:
        print(
            f"\nmean error {mean_err:.4f} exceeds gate {ERROR_GATE_PX}, refusing to write",
            file=sys.stderr,
        )
        return 1

    intrinsics = {
        "camera": {
            "model": "c922_pro",
            "resolution": [WIDTH, HEIGHT],
            "pixel_format": "mjpg",
        },
        "calibration": {
            "pattern_size": list(PATTERN_SIZE),
            "square_size_mm": SQUARE_SIZE_MM,
            "image_count": len(object_points),
            "reprojection_error_mean_px": float(mean_err),
            "reprojection_error_max_px": float(max_err),
            "reprojection_error_rms_px": float(rms),
        },
        "camera_matrix": camera_matrix.tolist(),
        "distortion_coefficients": dist_coeffs.flatten().tolist(),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w") as f:
        yaml.safe_dump(intrinsics, f, sort_keys=False, default_flow_style=None)

    print(f"\nwrote {OUTPUT_FILE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="calibrate_camera")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capture")
    sub.add_parser("calibrate")
    args = parser.parse_args()

    if args.command == "capture":
        return run_capture()
    if args.command == "calibrate":
        return run_calibrate()
    return 1


if __name__ == "__main__":
    sys.exit(main())
