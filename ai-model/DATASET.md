# Dataset Selection — PoseLift

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
- Format: pre-extracted COCO17 keypoints (PKL + JSON) plus frame-level labels (NPY)

---

## Why PoseLift over raw-video datasets

| Criterion | PoseLift | DCSASS / UCF-Crime / Kaggle staged |
|---|---|---|
| Preprocessing burden | None. Keypoints already extracted | Days of GPU time to run YOLOv8 + ByteTrack on raw video |
| Tracking | ByteTrack person IDs already attached | Must implement BoT-SORT or DeepSORT |
| Labels | Frame-level binary (rare in this domain) | Video-level only |
| Privacy | Anonymized keypoints, no biometric pixels | Raw faces and bodies, GDPR-heavy |
| Realism | Real retail store, real customers | Staged actors in a lab |
| Architecture fit | Already matches our pose-LSTM pipeline | Would require conversion |

Format compatibility is what decided it. PoseLift skips the entire video-to-keypoint preprocessing step that every other candidate requires. On a deadline-driven demo, that's the trade-off that matters.

---

## Verified contents (local inspection, 2026-05-05)

| Folder | Count | Contents |
|---|---|---|
| `Pickle_files/Train/` | 104 `.pkl` | Pose sequences. **Normal behavior only**, by author design |
| `Pickle_files/Test/` | 47 `.pkl` | Pose sequences. Mixed normal + shoplifting frames |
| `Pickle_files/GT/` | 47 `.npy` | Ground-truth binary labels, one per Test file |
| `Json_files/data/PoseLift/` | 151 `.json` | Same data reformatted for the STG-NF benchmark |
| `STG-NF/` | — | Reference unsupervised model from the paper authors |

**Total instances: 151.** The README claims 153. The actual file count is 151, a 2-file cleanup between paper publication and dataset release. Negligible for our purposes, but noted.

**File naming pattern:** `<camera_id>_<video_id>.pkl`, camera IDs 1-6 (six cameras across the store).

---

## Annotation format

Each `.pkl` file is a Python dictionary keyed by frame number. Per frame:

- **Person ID** — unique tracker ID (ByteTrack-assigned)
- **Bounding box** — XYWH format
- **Keypoints** — 17 COCO keypoints in XYC format (x, y, confidence)

Each `.npy` label file is a 1D NumPy array, one binary value per frame:

- `0` = normal frame
- `1` = shoplifting frame

Source video metadata: 1920×1080, 15 FPS, 6 indoor cameras.

---

## Why we're using a supervised classifier for the Sprint 5 demo

The dataset was designed for unsupervised anomaly detection: train on normal behavior (Train/), flag anomalies on Test/. Labels only exist for the Test split, by design.

For Sprint 5, we break from that design deliberately. We take the 47 labeled Test files and split them ourselves into train/val/test inside the Kaggle notebook, treating it as a supervised binary classification problem.

| | Supervised (Sprint 5 demo) | Unsupervised (post-meeting) |
|---|---|---|
| Training data | 47 labeled files, split locally | 104 normal-only files |
| Output | Binary classifier (0/1 + confidence) | Continuous anomaly score |
| Demo metrics | Precision, recall, F1, confusion matrix | AUC-ROC, AUC-PR, EER |
| Paper-comparable | No | Yes |
| Client readability | High | Low |

Communicability is the reason. A non-technical client understands "green box or red box, here's its accuracy." Negative log-likelihood under a normalizing flow means nothing to them. After the meeting, we return to the unsupervised approach to align with the dataset's intended use and produce paper-comparable benchmarks. Intentional rescoping, not a plan failure.

---

## Limitations to disclose at the meeting

1. **Small sample size.** 151 instances total, 47 with frame-level labels. Standard for novel research datasets, but every metric we report carries that caveat.
2. **Single store, single geography.** One US retail store. Expect domain shift at any other store: different camera angles, lighting, shelf layout.
3. **Item-value bias.** The dataset skews toward large-item theft (bottles, packaged goods). Palmed small items like chocolate bars and cosmetics are underrepresented. Our model inherits this.
4. **Bounding-box-relative normalization is required.** Without it, the model learns "shoplifting happens at x<300", which is useless on any other camera. We normalize relative to each person's bounding box at both training and inference time.
5. **Camera-angle bias.** Six fixed angles, none matching the webcam at the meeting. Normalization helps but doesn't fully solve it without more diverse data.
6. **Pose-extraction failures cascade.** HRNet produced keypoints from the raw videos; occlusion behind shelves causes NaN keypoints that need sanitizing before training.

---

## V2 path (post-meeting)

The upgrade is **RetailS**, from the same research group: ~20 million frames, multi-camera, semi-supervised. It solves the sample-size and single-store problems above. It also requires a real preprocessing pipeline, which is why it's V2 and not V1.

---

## How to get the dataset

The repo ships with samples only. The full dataset is on Google Drive, linked from the README.

```bash
cd ai-model/data/raw
git clone https://github.com/TeCSAR-UNCC/PoseLift.git poselift
# Download the Google Drive folder linked in poselift/README.md
# Extract into poselift/ — final structure matches the table above.
```

`ai-model/data/raw/` is gitignored. Anyone cloning this project downloads PoseLift separately.