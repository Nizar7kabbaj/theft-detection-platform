# Dataset Selection — PoseLift

**Ticket:** TDP-85
**Date:** 2026-05-05
**Status:** Selected for Sprint 5 demo

---

## Choice

**PoseLift** (TeCSAR-UNCC, WACV 2025) — pose-based shoplifting dataset.

- Source: https://github.com/TeCSAR-UNCC/PoseLift
- Paper: https://arxiv.org/abs/2501.06591
- Download: Google Drive folder linked from the README
- License: Academic / arXiv non-exclusive
- Size on disk: ~17 MB compressed, ~50 MB extracted
- Format: pre-extracted COCO17 keypoints (PKL + JSON) + frame-level labels (NPY)

---

## Why PoseLift and not a raw-video dataset

| Criterion | PoseLift | DCSASS / UCF-Crime / Kaggle staged |
|---|---|---|
| Preprocessing burden | None — keypoints already extracted | Days of GPU time to run YOLOv8 + ByteTrack on raw video |
| Tracking | ByteTrack person IDs already attached | Must implement BoT-SORT or DeepSORT |
| Labels | Frame-level binary (rare in this domain) | Typically video-level only |
| Privacy | Anonymized keypoints, no biometric pixels | Raw faces and bodies, GDPR-heavy |
| Realism | Real retail store, real customers | Often staged actors in a lab |
| Architecture fit | Format already matches our pose-LSTM pipeline | Format mismatch — would need conversion |

For a deadline-driven demo project, **the dataset format already matching our architecture** is more valuable than the dataset being more popular. We skip the entire video → keypoint preprocessing step that other datasets would force us into.

---

## Verified contents (from local inspection 2026-05-05)

| Folder | Count | Contents |
|---|---|---|
| `Pickle_files/Train/` | 104 `.pkl` | Pose sequences — designed by authors as **normal behavior only** |
| `Pickle_files/Test/` | 47 `.pkl` | Pose sequences — mixed normal + shoplifting frames |
| `Pickle_files/GT/` | 47 `.npy` | Ground-truth binary labels, one per Test file |
| `Json_files/data/PoseLift/` | 151 `.json` | Same data reformatted for the STG-NF benchmark code |
| `STG-NF/` | — | Reference unsupervised model from the paper authors |

**Total instances:** 151 (Train + Test). The README claims 153; actual file count is 151. Disclosed honestly — likely a 2-file cleanup between paper publication and dataset release. Negligible for our purposes.

**File naming pattern:** `<camera_id>_<video_id>.pkl`, where `camera_id` is 1–6 (six cameras across the store).

---

## Annotation format

Each `.pkl` file is a Python dictionary keyed by frame number. Per frame:
- **Person ID** — unique tracker ID (ByteTrack-assigned)
- **Bounding box** — XYWH format
- **Keypoints** — 17 COCO keypoints in XYC format (x, y, confidence)

Each `.npy` label file is a 1D NumPy array, one binary value per frame:
- `0` = normal frame
- `1` = shoplifting frame

Source video metadata: 1920×1080 resolution, 15 FPS, 6 indoor cameras.

---

## Architectural decision — supervised classifier for Sprint 5 demo

The dataset is **designed by its authors for unsupervised anomaly detection**: train only on normal behavior (Train/), then detect anomalies on Test/. This is why labels exist only for the Test split.

For Sprint 5 (client demo), we deliberately diverge from this design and use the **labeled Test split as supervised training data**, splitting it ourselves into train/val/test inside the Kaggle notebook. Trade-offs:

| | Supervised (Sprint 5 demo) | Unsupervised (post-meeting) |
|---|---|---|
| Training data | 47 labeled files split locally | 104 normal-only files |
| Output | Binary classifier (0/1 + confidence) | Continuous anomaly score |
| Demo metrics | Precision, recall, F1, confusion matrix | AUC-ROC, AUC-PR, EER |
| Comparable to paper | No | Yes |
| Demo readability for non-technical client | High — easy to explain | Lower — requires explaining anomaly scores |

The supervised approach is intentionally chosen for the **demo's communicability**: a non-technical client understands "the box is green or red, here is its accuracy" far more easily than "this is the negative log-likelihood under a normalizing flow." After the meeting, we return to the unsupervised approach to align with the dataset's intended use and produce paper-comparable benchmarks (post-meeting backlog).

This is documented as professional rescoping (lesson #16), not a failure of the original plan.

---

## Honest limitations to disclose at the meeting

1. **Sample size is small.** 151 instances total, 47 with frame-level labels. Standard for novel research datasets, but limits the absolute confidence of any metric we report.
2. **Single store, single geography.** Recorded in one US retail store. Domain shift is expected at any other store, with any other camera angle, lighting, or shelving layout.
3. **Item-value bias.** The dataset over-represents large-item theft (bottles, packaged goods) and under-represents palmed small items (chocolate bars, cosmetics). Our model will inherit this bias.
4. **Bounding-box-relative normalization required.** Raw pixel coordinates would teach the model that "shoplifting happens at x<300" — useless on any other camera. We normalize relative to the person's bounding box at both training and inference time.
5. **Camera-angle bias.** Six fixed angles. The webcam at the meeting will be at a different angle. We address this with normalization but cannot fully eliminate it without more diverse data.
6. **Pose-extraction failures cascade.** Keypoints are produced by HRNet on the raw videos; occlusion behind shelves causes NaN keypoints that we must sanitize before training (lesson #51).

---

## V2 roadmap (post-meeting)

After the client meeting, the upgrade path is the **RetailS** dataset from the same research group: ~20 million frames, multi-camera, semi-supervised. RetailS solves the sample-size and single-store limitations above. It also requires a real preprocessing pipeline, which is why it is V2 work, not V1 demo work.

---

## How to obtain the dataset

The repository ships with samples only. The full dataset is hosted on Google Drive and linked from the repo README.

```powershell
cd ai-model\data\raw
git clone https://github.com/TeCSAR-UNCC/PoseLift.git poselift
# Then download the Google Drive folder linked in poselift/README.md
# and extract into poselift/ — final structure is in the table above.
```

The `ai-model/data/raw/` folder is gitignored. Anyone cloning this project must download PoseLift themselves.