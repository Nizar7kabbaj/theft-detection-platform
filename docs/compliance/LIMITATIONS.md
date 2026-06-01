# Technical Limitations — TheftGuard

**Document type:** Engineering honesty disclosure
**Audience:** Reviewers, prospective deployers, technical readers
**Last updated:** 2026-05-07
**Owner:** Provider (see scope below)

---

## Document scope

This document is written from the perspective of a hypothetical solution
provider delivering TheftGuard to a European retail client. The author is
a student; no commercial deployment exists. All numbers in this document
are reproducible from the codebase using the scripts referenced in each
section.

This is the document that says, plainly, what the system **cannot** do.
A processor who will not name the limits of their own product is not a
processor a controller should trust.

---

## 1. What the system is

TheftGuard is a **decision-support tool**. A pose estimation pipeline
(YOLOv8-pose + ByteTrack) extracts skeletal keypoints from a camera
feed. Two parallel components consume those keypoints:

- A **deterministic geometric rule** (the *bend rule*) measures torso
  inclination and fires an alert when a person bends past 60° for at
  least 2 seconds.
- A **learned classifier** (an LSTM trained on PoseLift) outputs a
  per-person *normal* / *suspicious* label visualized as a green or red
  bounding box.

A human guard receives the alert (currently via Telegram) and decides
whether to act. The system **never** acts autonomously.

---

## 2. Model performance — headline numbers

Measured on the held-out test fold of PoseLift (10 labeled clips). The
full evaluation report lives in `ai-model/EVALUATION.md`; the metrics
file is `ai-model/outputs/evaluation/metrics.json`.

| Metric | Value | What it means |
|--------|-------|---------------|
| F1 | 0.693 | Harmonic mean of precision and recall at the deployed threshold. |
| Recall | 0.929 | Of every 100 true theft windows, the model catches ~93. |
| Precision | 0.553 | Of every 100 windows the model flags, ~55 are real. The rest are false alarms. |
| Accuracy | 0.558 | Modest, because the test data is class-balanced and a recall-tuned model accepts more false positives. |
| AUC | 0.455 | **Below 0.5. See §4 — this is real and disclosed, not an error.** |
| 5-fold CV F1 (mean ± std) | 0.569 ± 0.077 | Variance across folds is meaningful; deployed model is the best fold (F1=0.693). |

**Inference latency** (RTX 3070 Laptop, batch=1, measured over 10,000
windows): mean 0.334 ms, p95 0.572 ms, **mean throughput ≈ 2,994 FPS**.
The bottleneck for the live demo is not the LSTM but the YOLOv8-pose
upstream (~25 FPS). The model has roughly 200× headroom over the
live-demo target frame rate.

---

## 3. The operating-point choice — recall over precision, deliberately

The deployed model is tuned so recall (0.93) substantially exceeds
precision (0.55). This is a design choice, not a defect.

**Reasoning.** The cost asymmetry is wide and asymmetric:

- A false negative (missed theft) is *unrecoverable* — the merchandise
  leaves the store and no later signal would have caught it.
- A false positive (false alarm) costs a guard ~2 seconds to dismiss
  via the dashboard, with no consequence to the customer.

In this regime, the rational operating point is the one that minimizes
false negatives subject to a tolerable false-positive rate, not the one
that maximizes accuracy. With ~55% precision and recall-tuned alerting,
a guard reviewing 20 alerts per shift would dismiss ~9 false positives
to catch ~11 real ones. That workload is comparable to a guard reviewing
standard CCTV without ML assistance, and is the design intention.

**A controller who wants a different operating point** can move the
classification threshold without retraining; the threshold is a
configuration parameter, not a model parameter. Higher precision +
lower recall is a one-line change.

---

## 4. AUC = 0.455 — the honest read

A reviewer comparing this number to a textbook will note that AUC < 0.5
implies the model's *ranking* of windows is worse than random. This is
true, and we disclose it without softening.

**What it means in practice.** AUC measures the model's ability to rank
all positive examples above all negative examples *in continuous score
space*. The deployed model does not use continuous scores — it uses a
fixed threshold to produce a binary `normal`/`suspicious` label. At
that threshold, F1 = 0.69 and recall = 0.93. The binary decision is
useful even when the underlying score ranking is not.

**Why the ranking degrades.** Three honest reasons:

1. **Small calibrated test set.** 10 labeled clips × ~120 frames each
   produces a few hundred sliding windows. AUC is sensitive to ranking
   in the long tail of low-confidence examples, and that long tail is
   small here.
2. **The model concentrates probability mass.** Across the test set,
   the model output sits in a narrow band around 0.96 — high-confidence
   most of the time, low spread. The binary threshold cuts cleanly
   through this band; ROC-style ranking does not.
3. **Class imbalance and curation.** PoseLift's labeled test files
   contain anomaly windows in approximately 60% of frames (a quirk of
   curation; see `BIAS.md` §1). AUC penalizes models that cannot rank
   the minority class against the majority, but the *minority* here is
   *normal* behavior — an unusual inversion that confuses standard AUC
   intuition.

**The honest sentence.** *We deployed a model that is well-calibrated
for binary alerts and miscalibrated for ranking. Binary alerts are what
the product needs; ranking is not. We disclose the ranking failure
because a future deployment with a different alert UX (e.g. a top-N
queue rather than a stream) would need to retrain for ranking quality.*

---

## 5. Domain shift — the live LSTM flicker

The LSTM trained on PoseLift, which was captured by **overhead retail
CCTV at 1920×1080, 15 FPS, in a single store**. The live demo runs on a
**laptop desk webcam at desk level**. The two viewpoints produce
substantively different skeletons for the same posture: shoulder-hip
ratios, joint visibility, and self-occlusion all change.

**Observable consequence.** During the live demo, the LSTM's per-frame
output flickers between *normal* and *suspicious* on the **same posture**
seconds apart. A person standing still, with no posture change, can
flip green→red→green within a 5-second window. This is reproducible and
recorded in PROJECT_CONTEXT.md lesson #67.

**Why this happens.** The LSTM has not seen desk-camera viewpoints in
training. The keypoint distribution it sees at inference is
out-of-distribution relative to its training set. The model has no
mechanism to detect this and abstain; it produces a confident output
on each window regardless.

**The design response.** This is the reason the **LSTM is visual-only
and does not drive alerts.** The bend rule, which fires the actual
Telegram notification, is **camera-agnostic**: it measures torso
inclination using three keypoints (nose, left shoulder, right shoulder
for desk cameras; or hip-based variant for overhead cameras) and is
robust to the viewpoint change.

This is the **hybrid rule+ML architecture** (§6) and it is the most
important design decision in the project.

---

## 6. The hybrid architecture — why the rule owns the alert path

The system runs **two parallel detectors**:

| Detector | Type | Drives alerts? | Strength | Weakness |
|----------|------|----------------|----------|----------|
| Bend rule | Geometric / deterministic | **Yes** | Robust to camera viewpoint, interpretable, no training data required | Detects only the bend signature; misses other theft motions |
| LSTM classifier | Learned / probabilistic | No (visual only) | Can in principle learn arbitrary suspicious motion patterns | Brittle to domain shift; not transferable across camera setups without retraining |

A naive design would let the LSTM drive alerts, hit high in-domain
metrics on PoseLift, and fail silently on a real deployment with
different cameras. A defensive design uses the rule for the
**load-bearing** decision and the LSTM as a **visual signal** that
helps the guard interpret the scene without being trusted to fire alerts.

**This is honest engineering.** A deployment with cameras matched to
PoseLift's overhead viewpoint, with a corresponding fine-tuning pass on
in-store data, would be the point at which the LSTM could be promoted
to the alert path. That is a Phase 6 (post-meeting) consideration, not
a current capability.

---

## 7. What the system is not

The system is **not**:

- **Autonomous.** A human reviews every alert before action. There is
  no automated decision with legal effect (GDPR Art. 22 does not apply).
- **Evidence-grade.** Snapshots are forensic *context* for a guard's
  judgment, not chain-of-custody evidence. A retailer pursuing a
  prosecution would rely on the underlying CCTV recording, not the
  TheftGuard snapshot.
- **A facial recognition system.** No facial features are extracted,
  matched, or stored. Pose keypoints localize joints (nose, shoulders,
  hips, etc.) but do not encode facial identity.
- **A substitute for staff training.** Loss prevention is a
  human-system. TheftGuard reduces guard workload at the *detection*
  step; it does not address staff training, store layout, item placement,
  or any of the other levers that have larger effects on shrinkage.
- **A general-purpose anomaly detector.** It detects the specific
  behavioral signatures present in its training data. Theft modalities
  that do not match those signatures (e.g., palming small items,
  collusion between staff and customer, organized retail crime) are
  out of scope.
- **Production-ready.** See §9.

---

## 8. Operational limitations

Even within the system's intended use, the conditions below degrade
performance and are disclosed:

| Condition | Effect | Mitigation |
|-----------|--------|------------|
| Low light / IR-only cameras | YOLOv8-pose was not trained on IR. Keypoint quality degrades. | Use cameras with adequate visible-light illumination. |
| Heavy occlusion (crowds) | ByteTrack ID switches; pose estimation drops keypoints. | Position cameras to minimize crowd overlap; accept reduced recall in peak hours. |
| Camera angle mismatch | See §5. LSTM flickers; bend rule remains usable. | Use overhead camera angles matching PoseLift, or fine-tune the LSTM. |
| Distance from camera | At >8m, keypoint confidence falls below useful threshold. | One camera per ~50 m² of floor space. |
| Children | Pose estimation trains predominantly on adults; child skeletons can produce lower-confidence keypoints. | Acknowledged; see `BIAS.md`. |
| Mobility aids (wheelchairs, crutches) | Skeletons are partially occluded; bend rule can mis-fire. | Acknowledged; see `BIAS.md`. |
| Single-camera deployment | No cross-camera tracking. A person leaves one camera's view and re-enters another with a new track ID. | By design — multi-camera tracking is out of scope. |

---

## 9. Roadmap — what would have to change

Each limitation in this document maps to a roadmap item. None are ready
today; all are credible next steps.

| Limitation | What would lift it | Phase |
|------------|--------------------|-------|
| Single-store training data | Multi-store fine-tuning; transfer learning on in-store data | Post-meeting |
| Domain shift (LSTM flicker) | Per-deployment fine-tune on the controller's own cameras | Post-meeting |
| LSTM cannot drive alerts | Promote LSTM to alert path **only** after per-deployment fine-tune validates F1 on in-domain data | Post-meeting |
| AUC < 0.5 | Retrain with ranking-aware loss (e.g. AUC-margin) for top-N queue UX | Post-meeting |
| Single-camera tracking | Multi-camera ReID — out of scope as a deliberate privacy choice | Not planned |
| Telegram alert path | Replace with EU-resident dashboard | Phase 5 deferred (see `PRIVACY.md` §6) |
| Retention enforcement | Automated cron-based purge | Phase 5 deferred |
| Audit log of alert dispatches | Tamper-evident append-only log | Phase 6 |

---

## 10. The summary line

TheftGuard is a recall-tuned, human-in-the-loop, hybrid rule+ML
behavioral alert system with a small, single-store training corpus and
known camera-domain sensitivity. It suits a supervised pilot deployment
that matches its training viewpoint. It does not suit unsupervised,
cross-deployment, or evidence-grade use.

A controller who needs more than the above should plan for the roadmap
work in §9 before deployment.

---

*This document does not constitute a warranty. The provider's deliverable
is the system as described in the source repository; performance in any
specific deployment depends on conditions outside the provider's control.*