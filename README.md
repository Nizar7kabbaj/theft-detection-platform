# 🛡️ Real-Time AI Theft Detection Platform

> Pose-based shoplifting detection with a full Azure data pipeline, deployed
> end-to-end from camera to alert in under 2 seconds.

[![Status](https://img.shields.io/badge/status-active-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()
[![Python](https://img.shields.io/badge/python-3.11-blue)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-009688)]()
[![React](https://img.shields.io/badge/React-18-61DAFB)]()
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)]()
[![Azure](https://img.shields.io/badge/Azure-EventHub-0078D4)]()
[![PyTorch](https://img.shields.io/badge/PyTorch-LSTM-EE4C2C)]()

---

## 🎯 What this is

A production-grade AI surveillance platform that detects shoplifting behavior
in real time from a live camera feed, streams events into the cloud, persists
them for analytics, and notifies a human guard via Telegram for review.

The system is built on the principle that **shoplifting is a behavior over
time, not a single-frame visual** — so it uses **pose-based sequence
classification** instead of frame-by-frame object detection. This is the
current state-of-the-art approach (WACV 2025) and is fundamentally more
accurate, more privacy-preserving, and more explainable than pixel-based CCTV
analytics.

---

## 🏗️ Architecture
  ┌────────────┐
  │   Camera   │  (RTSP / webcam)
  └─────┬──────┘
        │
        ▼
  ┌────────────────────────┐
  │  YOLOv8-Pose (GPU)     │  COCO17 keypoints @ 30 FPS
  │  + ByteTrack tracking  │
  └─────┬──────────────────┘
        │
        ▼
  ┌────────────────────────┐
  │   LSTM Classifier      │  pose-sequence binary classification
  │   (PyTorch, 63K params)│  ~2-second sliding window
  └─────┬──────────────────┘
        │
        ├──────────────────────────► Azure Event Hub (Kafka API)
        │                            (real-time stream, partitioned)
        ▼
  ┌────────────────────────┐
  │   FastAPI Backend      │
  │  (BackgroundTasks)     │
  └─────┬─────────┬────────┘
        │         │
        ▼         ▼
  ┌────────┐  ┌──────────────┐
  │ MongoDB│  │ Telegram Bot │ (human-in-the-loop alert)
  │  Atlas │  │  → guard     │
  └────────┘  └──────────────┘
        │
        ▼
  ┌────────────────────────┐
  │  React Dashboard       │  live alerts, history, analytics
  │  (TS + Tailwind)       │
  └────────────────────────┘

### Why pose-based?

| Approach | Accuracy | Privacy | Domain shift | Compute |
|---|---|---|---|---|
| Single-frame CNN | Low | Faces leak | Severe | Heavy |
| 3D CNN (video) | Medium | Faces leak | Severe | Very heavy |
| **Pose-based LSTM (this project)** | **High** | **GDPR-by-design** | **Robust** | **Light** |

Pose extraction discards everything except joint positions — no faces, no
clothing, no skin tone, no biometric pixels ever leave the camera. This is a
**fundamental architectural privacy advantage**, not a bolt-on feature.

---

## 🧠 Machine Learning

- **Dataset:** PoseLift (TeCSAR-UNCC, WACV 2025) — 47 labeled retail
  shoplifting instances with pre-extracted COCO17 keypoints and ByteTrack IDs
- **Model:** 2-layer LSTM, hidden size 64, ~63K trainable parameters
- **Training:** 5-fold cross-validation on Kaggle Tesla T4
- **Preprocessing:** bbox-relative keypoint normalization + NaN sanitization
- **Honest results:**
  - 5-fold CV F1 = **0.57 ± 0.08** (small dataset → high variance, openly disclosed)
  - Deployed model F1 = **0.69**, recall = **0.93**
  - Recall > precision by design (a guard can dismiss a false alarm in
    seconds; a missed theft is unrecoverable)

The training notebook, trained weights, metadata sidecar, and 5-fold CV plots
are all version-controlled in this repo for full reproducibility.

---

## ⚙️ Tech stack

**AI & Computer Vision**
- PyTorch · YOLOv8-pose · Ultralytics · OpenCV · NumPy

**Backend**
- FastAPI · Pydantic · Motor (async MongoDB) · BackgroundTasks · Uvicorn

**Frontend**
- React 18 · TypeScript · Tailwind CSS · Recharts · Axios

**Data & Cloud**
- Azure Event Hub (Kafka API) · MongoDB Atlas · Azure for Students

**Infra & DevOps**
- Docker · Docker Compose (multi-stage builds, dev/prod overlays)
- Git Flow · GitHub PR workflow · Jira (Scrum, story-pointed sprints)
- Planned: Terraform · Azure DevOps CI/CD · AKS · Databricks · APIM ·
  Power BI · Service Bus · DevSecOps (Trivy, Snyk, Checkov, Gitleaks)

**Notifications**
- Telegram Bot API (multipart photo upload, BackgroundTasks)

---

## 🚀 Quick start

```powershell
# 1. Clone
git clone https://github.com/Nizar7kabbaj/theft-detection-platform.git
cd theft-detection-platform

# 2. Create your .env (see backend/.env.example)
# 3. Start the full stack
docker compose up --build

# Backend:  http://localhost:8000/docs
# Frontend: http://localhost:8080

# 4. Run AI on your webcam (separate terminal, host machine, GPU required)
venv\Scripts\activate
python ai-model\scripts\detect_alert.py --source 1
```

---

## 📊 Project status

**Currently active sprint: Demo Prep (Sprint 5)** — preparing a defensible
client demo with trained classifier, live webcam overlay, evaluation metrics,
Power BI mockup, and ethical/legal disclosure.

**Completed phases:**
- ✅ Phase 1 — AI foundation (YOLOv8 + GPU + 30 FPS pipeline)
- ✅ Phase 2 — FastAPI backend + MongoDB Atlas
- ✅ Phase 3 — React TypeScript dashboard
- ✅ Phase 4 — End-to-end integration + Docker Compose + Telegram alerts
- 🚧 Phase 5 — Real-time streaming + ML classifier (in progress)
- ⏳ Phase 6 — Full Azure deployment via Terraform + AKS
- ⏳ Phase 7 — Documentation, ADRs, demo video, final report

**Live numbers:**
- 14+ merged PRs across feature branches (Git Flow)
- 60+ Jira tickets, every commit and branch traceable to a ticket ID
- 30 FPS sustained on RTX 3070 with concurrent inference + streaming

---

## ⚠️ Honest limitations (because I believe in honest engineering)

- **Dataset size:** 47 labeled instances is small. CV variance is real and
  documented (F1 = 0.57 ± 0.08).
- **Single retail environment:** PoseLift was filmed in one store. Domain
  shift is expected on any other camera.
- **Item-value bias:** dataset over-represents large-item theft and
  under-represents palmed small items.
- **Demo-mode supervised training:** PoseLift is designed for unsupervised
  anomaly detection. Supervised mode is used here for client-communicable
  metrics; unsupervised is the post-meeting iteration.

These are documented in detail in [`docs/LEGAL_ETHICAL.md`](docs/LEGAL_ETHICAL.md)
(Phase 5) along with GDPR / Swiss FADP considerations and
human-in-the-loop architecture rationale.

---

## 👤 Author

**Nizar Kabbaj** — DevOps & Data Engineering · Morocco → Switzerland
- 🐙 GitHub: [@Nizar7kabbaj](https://github.com/Nizar7kabbaj)
- 💼 Portfolio target role: Ingénieur DevOps Azure Data

This project was built end-to-end as a portfolio piece covering the full
modern data engineering stack: AI/CV, backend, frontend, real-time
streaming, cloud architecture, IaC, CI/CD, and observability.

If you're a recruiter or hiring manager, the entire 60+ ticket backlog,
sprint history, ADRs, and decision log are public — every architectural
trade-off is documented, including the ones I got wrong and reverted.

---

## 📜 License

MIT — see [LICENSE](LICENSE).

You are free to use, study, fork, and adapt this code with attribution.
If this project helps you, a ⭐ on GitHub is appreciated.
