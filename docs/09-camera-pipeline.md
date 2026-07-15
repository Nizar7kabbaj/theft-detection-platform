# Camera pipeline

The inference path starts at the camera. A Logitech C922 Pro Stream Webcam on USB feeds 1920x1080 MJPG frames into the box, where the camera service grabs them, encodes each to JPEG, and forwards them to the ai-service for pose extraction. This chapter covers that camera service — how it holds the device open, how it survives the device dropping off the bus, how it paces itself between idle and active, and how it hands frames to the two consumers downstream. The lens calibration workflow that produces the undistortion math lives at the end of the chapter, since it runs once as an operator task rather than as part of the running pipeline.

The service is one process per camera. It pins one V4L2 device, runs a capture thread that never stops while the container is up, and pushes each encoded frame two ways: into a local buffer that a gRPC forwarder drains toward the ai-service, and onto a Redis stream that later consumers read. Everything else — the framerate controller, the reconnection handler, the stream transport — hangs off that spine.

## The capture spine

The service boots in `app/main.py`, which builds the pieces and wires them together in one place. A `CameraDevice` holds the V4L2 handle. A `ForwardBuffer` holds encoded frames waiting to be sent. A `CaptureLoop` runs the grab-encode-push cycle on its own thread. A `Forwarder` drains the buffer over gRPC. Two more pieces — a `RateController` and a `FramePublisher` — attach to the same boot and have their own sections below. Main constructs all of them, installs SIGTERM and SIGINT handlers that set a stop event, starts the loop and the publisher, and runs the forwarder as an async task until the stop event fires. Shutdown reverses the order: stop the forwarder, cancel its task, stop the loop, stop the publisher.

Splitting capture from forwarding is the core shape. The capture thread runs synchronously — OpenCV's `read()` blocks, and blocking calls don't belong on the asyncio event loop. So capture lives on a daemon thread and drops each frame into the buffer. The forwarder runs on the event loop and pulls from the buffer at its own pace. The buffer is the seam between a blocking producer and an async consumer, and it's what lets a slow or failed forward avoid stalling the grab.

### Holding the device

`CameraDevice` opens the camera with the V4L2 backend named explicitly, then negotiates the format the pipeline needs:

```python
capture = cv2.VideoCapture(self._device_path, cv2.CAP_V4L2)
capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._frame_width)
capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._frame_height)
capture.set(cv2.CAP_PROP_FPS, self._target_fps)
capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
```

MJPG is the format that fits USB 2.0 bandwidth at 1080p. YUYV uncompressed at the same resolution drops to 5 fps because the raw bitrate doesn't fit the bus, so the camera is asked for MJPG and the negotiated fps is checked against the target — if the driver hands back less than asked, the open logs a warning rather than failing silently.

`BUFFERSIZE 1` is the choice that matters most for a detection pipeline. OpenCV defaults to a small internal frame queue, and on a camera that queue fills with stale frames when the consumer falls behind. A detection running a few frames in the past is worse than one that skips — the alert is late and the skeleton is on a body that already moved. Setting the driver buffer to one frame means `read()` always returns the newest grab, and frames the pipeline can't keep up with are dropped at the source instead of pooling.

The device tracks a session id that increments on every successful open. Each frame carries the session id it was captured under, so a consumer can tell frames from before a reconnect apart from frames after — the frame index resets to zero on reopen, and without the session id two frames could share an index.

The device is pinned by its stable by-id path, not `/dev/video2`:

```
/dev/v4l/by-id/usb-046d_C922_Pro_Stream_Webcam_3521BF9F-video-index0
```
The `/dev/videoN` numbers are assigned in enumeration order and shift when USB devices are plugged, unplugged, or the machine reboots with a different device present. The C922 that was `video2` yesterday can be `video0` today. The by-id path is tied to the device's own identifier and doesn't move, so the container always opens the right camera regardless of what else is on the bus.

### Cache and forward

The buffer is a bounded `deque` behind a lock, with two drop policies. It caps at a fixed depth, and when it's full the oldest frame falls off as a new one arrives — overflow counted, newest kept. On the read side it drops frames older than a max age before returning one, so a consumer that catches up after a stall gets a fresh frame, not a backlog of stale ones. Both drop counts and the running depth are exposed as counters for the metrics layer.

```python
def push(self, frame: CapturedFrame) -> None:
    with self._lock:
        if len(self._frames) == self._frames.maxlen:
            self._dropped_overflow_total += 1
        self._frames.append(frame)
        self._captured_total += 1
```

Each buffered frame is a frozen record carrying the JPEG payload, the session id, the frame index, the camera id, a wall-clock timestamp for the downstream proto, and a monotonic capture time for the age check. Wall-clock and monotonic both exist on purpose — wall-clock is what the ai-service needs to stamp the detection, monotonic is what the buffer needs to measure age, because wall-clock can jump backward on an NTP correction and monotonic can't.

The `Forwarder` opens an async gRPC channel to the ai-service and loops: pull a fresh frame, convert it to a `Frame` proto, call `Analyze` with a one-second timeout, count the result. The timeout is not optional — a lazy gRPC channel hangs on the first call if the peer is gone, and without the timeout a dead ai-service freezes the forward loop rather than failing it. On an RPC error the forwarder counts the failure, drops the channel, sleeps with exponential backoff capped at a ceiling, and reconnects. Backoff resets to its floor on the first frame that gets through.

### How the container boots

The image runs Python 3.12 slim with `libgl1` and `libglib2.0-0` for OpenCV, as a non-root user with uid 1000. The container reaches the camera device through three settings that have to agree:

```yaml
user: "1000:1000"
group_add:
  - "44"
device_cgroup_rules:
  - "c 81:* rmw"
volumes:
  - /dev:/dev
```

The `/dev` mount gives the container the device nodes. Group 44 is `video` on the host — the process has to be in that group to open a V4L2 device, and adding it with `group_add` avoids running as root. The cgroup rule is the piece that's easy to miss: `c 81:* rmw` grants the container read, write, and mknod on character devices with major number 81, which is the V4L2 range. Without it the device node is visible through the `/dev` mount but every open returns a permission error, because the container's device cgroup denies access by default. Major 81, any minor, so it covers the camera wherever it enumerates.

Liveness is the heartbeat file. The capture loop touches `/tmp/camera_heartbeat` on every encode and on every reconnect retry, and the container's healthcheck tests that the file exists and is less than ten seconds old. This is deliberately not a check on the metrics endpoint. The metrics server answers from the asyncio main thread, and the capture that actually produces frames runs on a separate daemon thread — if that thread dies, the HTTP server keeps returning 200 while the camera produces nothing. A metrics-endpoint healthcheck would report healthy through exactly the failure that matters. The heartbeat is touched by the capture thread itself, so a stalled or dead capture thread lets the file go stale and the container is marked unhealthy within ten seconds.

## Adaptive framerate

Running the camera at 30 fps all day is wasted work. An empty room produces the same nothing at 30 fps as at 15, but at twice the frames to grab, encode, forward, and run pose over. So the service runs slow when nothing's happening and speeds up the moment a person appears: 15 fps idle, 30 fps active.

The decision doesn't live in the camera. The camera can't tell a person from a coat rack — that judgment is the ai-service's job, and it already makes it on every frame it analyzes. Each `Analyze` response carries a `detection_present` flag, and the forwarder feeds that flag straight into the rate controller:

```python
detection = await self._stub.Analyze(self._to_proto(record), timeout=1.0)
self._rate_controller.observe(detection.detection_present)
```

The controller turns a stream of present/absent flags into an fps target. Present means active. Absent doesn't immediately mean idle — it means active until the room has been empty for the dwell window, then idle:

```python
def observe(self, present: bool) -> None:
    now = time.monotonic()
    if present:
        self._last_present_monotonic = now
        desired = self._active_fps
    elif now - self._last_present_monotonic < self._dwell_seconds:
        desired = self._active_fps
    else:
        desired = self._idle_fps
```

The dwell is the part that matters. Without it, a single frame where the detector loses the person — someone turns side-on, walks behind a shelf, the pose confidence dips for one frame — drops the camera to 15 fps mid-incident, exactly when the extra frames are most needed. The dwell holds active fps for three seconds past the last positive detection, so a brief dropout doesn't downshift. Three seconds is long enough to ride through the gaps a pose detector leaves on a real body and short enough that an empty room settles back to idle without a noticeable tail.

The controller only calls `set_pace` when the target actually changes, so a room full of people generates one rate change on entry, not one per frame. Each change is logged and the current fps is exposed as a metric, so the idle-active pattern over a day is visible on the dashboard — how often the room goes active, how long it stays, whether the dwell is tuned right for the space.

One asymmetry is deliberate. Entry is instant — the first positive detection jumps straight to 30 fps, no dwell, no ramp — because the frames captured in the first moment of an incident are the ones the classifier needs most. Exit is lazy, gated by the dwell. The cost of speeding up a beat early is a few extra frames; the cost of slowing down a beat early is a gap in the record of an event in progress. The controller is built to never pay the second cost.

## Reconnection

USB cameras drop off the bus. The cable gets nudged, the hub browns out for a moment, the kernel re-enumerates the device under load. On a pipeline that has to run unattended, a dropped camera can't mean a dead service that needs a human to restart it. The service has to notice the device is gone, wait for it to come back, reopen it, and carry on — without the container exiting.

Two things fail when the camera drops, and both route to the same recovery. A cold start where the device isn't ready yet, and a mid-run grab that returns nothing because the device vanished under a running loop. The capture loop handles both the same way:

```python
def start(self) -> None:
    self._touch_heartbeat()
    if not self._device.open():
        self._device.reopen_with_backoff(on_retry=self._touch_heartbeat)
    ...

def _run(self) -> None:
    while self._running.is_set():
        ...
        frame = self._device.read()
        if frame is None:
            logger.warning("grab failed camera=%s, reopening", self._camera_id)
            self._device.reopen_with_backoff(on_retry=self._touch_heartbeat)
            self._frame_index = 0
            continue
```

A failed grab returns `None`, the loop logs it, and hands off to `reopen_with_backoff`. Recovery happens on the capture thread itself — the loop blocks inside the reopen until the device comes back. Nothing else runs on that thread, so there's nothing to race, and the buffer downstream simply stops receiving frames until capture resumes. The forwarder keeps draining whatever's left in the buffer and then idles, so a gone camera doesn't cascade into a forwarder error.

The reopen retries with exponential backoff:

```python
def reopen_with_backoff(self, on_retry=None) -> None:
    delay = self._reopen_backoff
    while True:
        if on_retry is not None:
            on_retry()
        logger.warning("device reopen in %.1fs", delay)
        time.sleep(delay)
        if self.open():
            return
        delay = min(delay * 2, self._reopen_backoff_max)
```

The delay starts at one second and doubles on each failed attempt up to an eight-second ceiling. The doubling keeps a device that's genuinely gone from spinning the CPU on open attempts, and the ceiling keeps the recovery latency bounded — once the camera is back, the service picks it up within eight seconds at worst, not on an ever-growing delay. Every `open` runs the full negotiation again: MJPG, resolution, `BUFFERSIZE 1`, and a fresh session id, so a frame captured after the reconnect is stamped with a session distinct from the frames before it.

The `on_retry` callback is the piece that keeps the container alive through a long outage. Recovery blocks the capture thread, and the capture thread is what touches the heartbeat file — so a reconnect loop that ran silent would let the heartbeat go stale and the healthcheck would kill the container mid-recovery, right when it's doing the correct thing. Passing `_touch_heartbeat` as `on_retry` means every retry pass refreshes the heartbeat. The container stays healthy while it waits for a camera that's unplugged for a minute, and only goes unhealthy if the capture thread itself dies — which is the case the heartbeat is there to catch. Recovering from a missing device and dying from a broken thread stay distinguishable.

The frame index resetting to zero on reconnect is intentional and pairs with the session id. Index counts frames within a session; session distinguishes one continuous run of the device from the next. A consumer that sees index jump back to zero knows a reconnect happened and can treat the new session as a fresh sequence rather than assuming frames went missing.

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
