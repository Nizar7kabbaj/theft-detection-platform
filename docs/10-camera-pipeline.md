# Camera pipeline

The inference path starts at the camera. A Logitech C922 Pro Stream Webcam on USB feeds 1920x1080 MJPG frames to the ai-service container, which runs YOLOv8-pose to extract keypoints and forwards them to the downstream classifier. The lens of the C922 is wide, and wide lenses bend straight lines. A doorframe near the edge of the frame curves outward by several pixels. Pose keypoints land on the bent body, not the real one, and the classifier learns from positions that drift further from truth the closer a person stands to the edge of the view.

This chapter covers the operator workflow that produces the intrinsic calibration the ai-service uses to undistort frames before pose extraction. Multi-camera sync, adaptive framerate, and the rest of the inference-input pipeline will land here as separate sections in later tickets.

## Intrinsic calibration

The output of calibration is two pieces of math. The camera matrix holds the lens's focal length in pixels (fx, fy) and the optical center (cx, cy). The distortion coefficients hold five numbers (k1, k2, p1, p2, k3) that describe how the lens bends light radially and tangentially. With both, the pipeline can run `cv2.undistort` on every frame and recover straight lines.

The technique is classical and unchanged since Zhang's 2000 paper: show the camera a target with known geometry from many angles, solve for the lens parameters that minimize reprojection error.

### Target

Printed 9x6 chessboard on A4 paper, glued flat to cardboard. The pattern size refers to the inner corners — the intersections where four squares meet — not the squares themselves. A 9x6 inner-corner pattern is a board of 10 squares across and 7 down. The board has to stay flat. Curl in the paper translates directly into pixels of reprojection error, and the gate at the end of the script rejects bad calibrations before they ship.

The pattern image is the stock OpenCV chessboard at `https://github.com/opencv/opencv/blob/master/doc/pattern.png`. Square size is recorded in the output but doesn't affect the intrinsic solve — it only scales the translation vectors, which the script discards.

### Tool layout

The tool lives at `tools/calibration/` outside any service. Calibration is a one-off operator workflow, not runtime code, so it stays out of the docker stack and runs from a host venv.

```
tools/calibration/
├── calibrate_camera.py
├── requirements.txt
└── output/              # gitignored
    ├── captures/        # .png frames from the capture phase
    └── camera_intrinsics.yaml
```

The venv lives at `tools/calibration/.venv` and holds three packages: `opencv-python`, `numpy`, `PyYAML`. The repo `.gitignore` covers `tools/calibration/output/` and `.venv/` so neither leaves the laptop.

The script has two subcommands. `capture` opens the camera, draws the corner overlay on every frame the chessboard is detected, and saves a PNG on each spacebar press. `calibrate` reads the saved PNGs, runs `cv2.calibrateCamera`, prints per-image reprojection error, and writes the YAML if the gate passes. Splitting capture from calibrate means a failing calibration can be fixed by deleting bad frames and rerunning the math, without reshooting the good ones.

### Device

The C922 enumerates on `/dev/video2` with the integrated laptop webcam on `/dev/video0`. The script pins the device, requests MJPG at 1920x1080, and opens with the V4L2 backend explicitly:

```python
cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
```

MJPG hits 30 fps at 1080p on USB 2.0 bandwidth. YUYV at the same resolution drops to 5 fps because the uncompressed bitrate doesn't fit the bus. Calibrating at the same format the inference pipeline will consume in production means the intrinsics describe the right lens-plus-codec combination.

### Capture session

Run from the venv:

```
python calibrate_camera.py capture
```

A preview window opens. The status bar across the top reads either `board not found` in red or `board detected` in green, with a count of frames saved so far. Pressing space saves a frame to `output/captures/NNN.png` when the board is detected and does nothing when it isn't. Pressing q closes the session.

Variety is what determines calibration quality. The target list:

- Five frames roughly centered, at three distances (close, medium, far).
- Eight frames with the board in each corner and edge of the view.
- Eight frames with the board tilted left, right, forward, back.
- Four frames with the board rotated in the image plane.

Twenty-five total is the working number. Ten is the OpenCV-documented minimum. Past twenty-five the gain per extra frame falls off fast and the risk of adding a bad frame goes up.

Three things to control during the session: light, flatness, stillness. Even lighting on the board keeps the corner detector happy. A flat board keeps the geometry true. Holding still for the half-second before pressing space keeps motion blur out of the corners — the preview hides motion blur because it's only 30 fps with no shutter indication.

### Calibration and the gate

```
python calibrate_camera.py calibrate
```

The script reads every PNG in `output/captures/`, re-detects corners on each (the in-session detection isn't trusted — the saved frame is what gets calibrated against), refines corner positions to subpixel accuracy with `cv2.cornerSubPix`, and feeds the lists into `cv2.calibrateCamera` along with the known 3D positions of the chessboard grid.

The gate is at 0.5 px mean reprojection error. The script computes per-image error as the L2 norm of (projected − measured) divided by `sqrt(N_corners)`, which makes per-image numbers comparable to the RMS that `calibrateCamera` returns aggregated. The original formula in the first draft divided by `N_corners` instead of `sqrt(N_corners)` and reported errors about seven times smaller than reality, which would have let bad calibrations pass the gate. The fix is a one-line change but the difference is real.

The output looks like this:

```
calibrating on 19 images
per-image reprojection error:
  000.png: 0.1047 px
  002.png: 0.0911 px
  ...
mean: 0.1787 px
max:  0.3935 px
rms:  0.1979 px
gate: 0.5 px
wrote /home/nizar/theft-detection-platform/tools/calibration/output/camera_intrinsics.yaml
```

If the mean exceeds the gate, the script prints the error breakdown and refuses to write the YAML. The repair is to delete the frames marked `over gate` and rerun calibrate. A bad calibration that ships is worse than no calibration — it bends the image the wrong way and pose accuracy drops further than it would have with a raw frame.

### Output format

YAML, plain nested lists, written with `yaml.safe_dump`. The shape is:

```yaml
camera:
  model: c922_pro
  resolution: [1920, 1080]
  pixel_format: mjpg
calibration:
  pattern_size: [9, 6]
  square_size_mm: 25.0
  image_count: 19
  reprojection_error_mean_px: 0.1787
  reprojection_error_max_px: 0.3935
  reprojection_error_rms_px: 0.1979
camera_matrix:
  - [1431.52, 0.0, 952.69]
  - [0.0, 1431.99, 539.78]
  - [0.0, 0.0, 1.0]
distortion_coefficients: [0.0708, -0.3641, -0.0006, 0.0025, 0.6104]
```

Plain lists rather than OpenCV's `FileStorage` XML for two reasons: a YAML loader exists in every language the downstream code might be written in, and a human can read the file and spot bad numbers without parsing tooling. The metrics block at the top means a reviewer can answer "is this calibration trustworthy" by reading the first few lines.

### Sanity check on the numbers

A clean calibration of the C922 at 1080p has predictable shape. Focal lengths near 1430 pixels, almost equal between fx and fy. Optical center within a few pixels of (960, 540). Distortion coefficients small, with k1 near zero and k2 mildly negative. The numbers above match those expectations; a calibration that doesn't (focal length under 1000 or over 2000, optical center far from image center, distortion coefficients in the single digits) is wrong even if the gate passed.

### Promoting the output

The script writes to `tools/calibration/output/camera_intrinsics.yaml`, which is gitignored. After review, the operator copies the file by hand to `ai-service/config/camera_intrinsics.yaml`, which is committed. The two-step is deliberate: the gate keeps bad math from being written at all, the manual copy keeps mistakes recoverable, and the commit history shows which calibration was active for which inference run.

Wiring the YAML into the ai-service frame preprocessor is a separate ticket in the ML rebuild epic, alongside the ST-GCN integration. The calibration file sits in `ai-service/config/` waiting for the loader.

## Lessons that cost time

The first capture session saved zero frames. The preview window was open and the status line said `board not found` because the camera was pointed at a window, not a printed chessboard. The detector needs an actual paper target with the right inner-corner count — 9x6 inner corners means a board of 10x7 squares, not 9x6 squares. A real wooden chess set won't work either; the squares are recessed and the corners aren't sharp enough.

The reprojection error formula in the first draft of the script divided the L2 norm by `N_corners` instead of `sqrt(N_corners)`. That makes per-image error about seven times smaller than the true RMS, which would have let a 3.5 px calibration pass a 0.5 px gate. The fix is one character (`np.sqrt`), but only catching it before the first real calibration kept the gate honest. The two formulas live a syntax change apart and produce numbers that look plausible in both forms — the only way to catch the wrong one is to compare per-image error against the `rms` value that `calibrateCamera` returns and notice they don't agree.

The capture counter in the first draft of `run_capture` was `len(list(CAPTURE_DIR.glob("*.png")))`. After deleting bad frames in the middle of the numbered sequence, the next session restarted numbering at the new file count and overwrote the surviving good frames. The fix is finding the highest existing number and counting from there:

```python
existing = sorted(int(p.stem) for p in CAPTURE_DIR.glob("*.png"))
counter = existing[-1] + 1 if existing else 0
```

Gaps in the filename sequence stay as gaps. Nothing gets overwritten.

The first session produced 25 frames but a mean reprojection error of 1.9 px — almost four times the gate. A cluster of seven consecutive frames was all over 3 px, and a few outliers were over 5 px. The pattern matched a stretch of the session where the printed board was held closer to a window and partly in shadow, with the paper curling slightly at the edges. Deleting the catastrophic frames and recapturing the rest under flat light with the board taped firm dropped the mean to 0.18 px on the next solve. Bad frames don't average out — they pull the optimizer toward a wrong solution, and the only fix is removing them from the input set.
