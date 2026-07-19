# GPU baseline

The detection core runs two models on one card, a laptop RTX 3070 with 8GB. Pose stays resident and always on; the VLM judge sits behind it and gets whatever memory pose leaves free. Before any of that can be sized, the card has to be pinned to a known state and measured on the real path. A number taken at boost clocks or against a synthetic loop tells you nothing about what the system does under load. This chapter covers the host setup that pins the card and the measurement that sizes the VLM.

## Pinning the card

Two things move on their own and both have to be stopped. The GPU drops to a low-power state when idle, clocking down to 210 MHz on the graphics domain and 405 MHz on memory, and it ramps back up only when work arrives. Persistence mode is off by default and resets to off on every boot. Left alone, a measurement taken now runs at one clock and a demo tomorrow runs at another, and the first frame after an idle stretch pays a ramp cost that the tenth frame does not.

Persistence mode keeps the driver resident so the card doesn't tear down and rebuild its state between workloads. The clock lock pins the graphics and memory domains to the top of the supported table, 2100 MHz and 7001 MHz, so the card runs at a fixed ceiling instead of ramping through boost states. The lock is a ceiling, not a floor: an idle card still drops its clocks to save power, but when work arrives it goes straight to the pinned clock rather than climbing to it.

Neither survives a reboot on its own. On driver 595 the old applications-clock path is gone, and the replacement, `nvidia-smi -lgc` and `-lmc`, applies at runtime and does not persist. So the setup is a boot-time job: enable persistence, apply both locks, verify the persistence flag actually flipped. A helper script does the three steps and a systemd unit runs it after `nvidia-persistenced.service` on every boot.

```bash
nvidia-smi -pm 1
nvidia-smi -lgc 2100,2100
nvidia-smi -lmc 7001,7001
```

The unit is `Type=oneshot` with `RemainAfterExit=yes`, so it runs once at boot, exits, and shows as active rather than reading like a dead service. The helper verifies by reading the persistence flag back through the query API and exits non-zero if it didn't stick, which marks the unit failed and surfaces in `systemctl status`. A silent failure that leaves the card unpinned is worse than a loud one. The script and unit live in the repository and install to their system paths through an idempotent installer, so a rebuilt host is one clone and one command away from the same state.

The acceptance test is a cold reboot. After the reboot the service comes up on its own, the persistence flag reads Enabled, and the clock ceiling reads 2100/7001, with no manual step. The journal for the boot shows the helper running one second into user space.

## Measuring on the real path

The pose cost that matters is the cost the running system pays, not the cost of a model in isolation. So the measurement runs the full path: the camera publishes real frames off the device, the ai service pulls them, decodes, and runs the pose model with its tracker, exactly as it does in production. A timing pair wraps the model call and writes two numbers per frame to a file, and a separate sampler reads the card once a second for the length of the window.

The model call is `track`, not `predict`, so it runs the pose forward pass and the tracker association together. That is the honest per-frame cost, because the tracker runs on every frame in the live system and its cost is real. The timing captures two numbers: wall time around the whole call, which is what the latency budget sees, and the library's own reported inference time, which is the model forward pass alone. The gap between them is everything else the frame pays, decode and tracker and the moves back to CPU.

The first frames after startup pay costs the steady state does not: CUDA context setup, weights moving to the card, kernels compiling on first use. A thirty-second burn-in runs before the window opens, and the timing file is reset at the window boundary so only steady-state frames count. The window itself is sixty seconds with a person in the camera view, which trips the presence gate and ramps capture to 30fps, so the card measures under real load rather than at the idle capture rate.

## What the card does

Over the window the pipeline held 31.5fps, 1891 frames in sixty seconds. The pose path costs the following per frame:

| Measure | Wall (full call) | Library (model only) |
|---|---|---|
| p50 | 43.88 ms | 5.91 ms |
| p95 | 52.67 ms | 6.98 ms |
| p99 | 57.59 ms | 8.02 ms |
| mean | 44.95 ms | 6.14 ms |
| max | 184.80 ms | 135.23 ms |

The steady state is tight. From p50 to p95 the wall time spreads twenty percent, and p99 sits under 60ms. Against a fast-path budget of 500ms from trigger to provisional alert, pose is not the constraint. The single max of 184ms wall paired with 135ms library time is one frame in 1891, a one-off stall well past p99, most likely a weight page or a kernel autotune on a cold path. It sits below the percentile that sizing cares about.

The gap between the two columns is the finding. The model forward pass is about 6ms; the full call is about 44ms. Roughly 38ms per frame is not the model, it is decode, tracker association, and the tensor moves around them. This matters for what to optimize next: a TensorRT export converts the model graph and moves the 6ms number, not the 38ms. The larger cost is the tracker and framework path, and these numbers are the pre-optimization baseline that the export gets measured against.

The card samples, taken once a second across the window while pose ran:

| Measure | Value |
|---|---|
| Graphics clock | 1890 MHz, zero variance across 60 samples |
| Memory clock | 7001 MHz, zero variance across 60 samples |
| GPU utilization | 5% median, 16% peak |
| Memory used | 1216 MiB |
| Memory free | 6618 MiB |
| Temperature | 72 °C |
| Power draw | 54 W |

Two things stand out. The clocks held flat for the whole window, no throttling, which is the property the lock exists to guarantee. But the graphics clock ran at 1890 MHz, one step below the 2100 MHz ceiling, because utilization never rose past 16%. The pose workload is light enough on this card that the driver never needed the ceiling and settled on the lowest clock that met demand. The lock capped the top; the workload never reached for it. Temperature at 72°C and power at 54W confirm the clock choice was demand, not thermal or power throttling. A number taken at 2100 MHz would run marginally faster on the model portion, about eleven percent on the 6ms library time and almost nothing on the 44ms wall, not enough to move any decision.

## What this gates

With pose resident and running, the card holds 6618 MiB free in the worst sample of the window. That is the memory the VLM judge gets, and it is stable: memory used stayed inside a 36 MiB band across the whole run. The sizing choice is between a 4B model held resident and an 8B model loaded on demand.

A 4B model at a five-bit quantization sits near 4.5 to 5 GiB with its context, which fits resident against 6618 MiB with room to spare. An 8B model at any usable quantization needs more than 7 GiB, which does not fit alongside pose and forces on-demand loading, a multi-second cold load from disk on every trigger. That cold load lands directly on the fast path the design depends on, so the resident 4B is the choice: the judge stays warm on the card and its verdict cost is inference alone.

The decision is provisional on two counts. These numbers are pre-optimization, and the TensorRT export planned next shrinks the pose footprint, which frees memory and reopens the question of whether an 8B model fits resident once pose is leaner. And the VLM footprints here are estimates from typical quantized sizes, not a measurement of the actual model on this card. Before the load path is committed, the real model gets the same treatment pose got: loaded, measured resident with its context, and confirmed to fit alongside pose with margin. The number sizes the decision; it does not replace measuring the thing itself.
