# Backend architecture

theft-detection-platform detects shoplifting from in-store camera feeds. Each store runs an edge box that captures video, gates every frame through a light detector at 15 fps, and wakes a heavier pose classifier only once a person stands in frame. Confirmed events leave the box for a cloud backend that stores them, fans them out to a dashboard over WebSocket, and dispatches alerts. Training, drift detection, and federated rounds run as a separate plane that feeds models back to the edge through a registry.

This document describes the services, the contracts between them, and the diagrams that fix the structure.

## Overview

The system divides into five planes.

The inference plane runs detection: frame capture, the detection gate, the heavy pose classifier, an input validator that screens for adversarial keypoints, the model server, and the API backend that frontends speak to.

The identity, security, and compliance plane holds authentication, the tamper-evident audit log, and the personal-data lifecycle service.

The data plane moves operational records into a medallion lake and serves analytics back to the dashboard.

The ML platform plane owns experiment tracking, the feature store, drift detection, labeling, training orchestration, and federated learning across edge boxes.

The frontend is a single Next.js dashboard, black-boxed here behind its HTTP and WebSocket contracts.

Two stores back the running system: MongoDB for operational state, Redis for cache, queues, pub/sub, and counters. PostgreSQL backs MLflow and Label Studio only. Azure Blob and a Delta Lake medallion hold artifacts and analytics. Frames never leave the edge box; only events and telemetry cross to the cloud, over Azure Event Hub.

## Design decisions

**Three-service detection split.** Detection runs across camera-service, detect-gate-service, and ai-service rather than one process. The pose classifier is heavy. Running it on every frame of an empty shop floor wastes the GPU. detect-gate-service holds an always-on yolov8n-detect pass at 15 fps as a gate; ai-service runs PoseConv3D only after the gate signals a person. Splitting capture from gating from classification lets each scale and fail on its own, and keeps the GPU idle until there is something to classify.

**Frames stay local, events egress.** camera-service owns the V4L2 handle and an in-store ring buffer. detect-gate-service pulls the 15 fps gate feed over local gRPC inside the box; ai-service pulls the active window on wake the same way. No frame crosses the network. Azure Event Hub carries edge-to-cloud event and telemetry egress only. Sending raw video to the cloud would cost bandwidth the deployment does not have and would drag personal imagery across a network boundary for no inference benefit.

**Presence is a bidirectional stream.** detect-gate-service and ai-service exchange presence over a gRPC bidi stream defined in `presence.proto`. A stream amortizes connection cost across a high-frequency event flow, gives backpressure, and returns an explicit ack per event. A lost person-entered event means the heavy path never wakes, so the ack matters.

**Rate changes hop edge-local.** When presence flips, detect-gate-service signals camera-service directly on the box to change capture rate. This is the hot loop and it stays off the cloud path. Operator rate overrides are a separate, slower channel.

**Operator control is edge-initiated.** The backend controls cameras over a gRPC bidi stream in `camera_control.proto`, but the edge box opens the connection outbound. The in-store box sits behind NAT; an edge-initiated stream removes the need for inbound reachability. Pending commands queue in Redis under `camera_pending:{camera_id}` so a backend restart does not drop them. This channel carries control only; frame data uses the local path.

**detect-gate-service self-hosts its model.** The gate runs yolov8n inside detect-gate-service and does not call the model server. Triton holds the heavy pose models only, called by ai-service. The gate runs constantly and must not take a network hop per frame; the heavy models change through the registry and belong behind a server that can swap them without a restart.

**ai-service reports to the backend only.** Heavy inference results go to the backend. ai-service does not call the notification service directly. One service owns dispatch orchestration, so the alert path has a single place to apply policy, idempotency, and retries.

**Defense sits before the classifier.** ai-service calls adversarial-defense-service over `defense.proto` before running the heavy classifier. The validator checks keypoint geometry, anatomical bounds, and frame-to-frame velocity, and screens for FGSM and PGD patterns. It returns three verdicts, not two: accept, reject, and degraded-accept, so a mildly suspicious frame still reaches the classifier carrying a confidence penalty rather than being dropped. The call is unary because it sits on the synchronous critical path, and the server is stateless because velocity context rides in the request.

**The audit log is hash-chained and append-only.** Every internal service writes auditable events to audit-service over `audit.proto`. Each event chains to the previous by hash. There is no update and no delete endpoint, and a verify call walks the chain to prove it intact. Event payloads use a typed `oneof`, not an untyped struct, so every audit category passes through the proto type system.

**Auth is gRPC between services, HTTP for people.** auth-service mints and refreshes JWTs over HTTP for login, logout, refresh, and me. Service-to-service token verification runs over gRPC in `auth.proto`. The frontend never speaks gRPC, so login stays on HTTP; backend services call VerifyToken on every authenticated request. Verification returns eight distinct statuses rather than a boolean, because expired, revoked, malformed, and disabled each drive a different downstream response.

**PostgreSQL is scoped to two tenants.** MLflow tracking and Label Studio metadata each get a database on one PostgreSQL instance. MongoDB stays the application database; Redis stays cache and pub/sub. PostgreSQL is not a general store, only the relational backing those two tools require.

**Federated learning has a dedicated edge agent.** federated-edge-client runs on the in-store box and pairs with the cloud-side federated-aggregator-service. It is its own service, not folded into camera-service, because federated rounds have their own lifecycle, their own failure modes, and their own model-pull path independent of capture.

**Typed contracts over untyped payloads.** Every internal proto carries typed messages rather than `google.protobuf.Struct`. The cost is one extra message per category; the gain is that the wire format is checked and self-documenting across all internal services.

## Service inventory

Twenty-one services across the five planes, plus the data stores, the observability plane, and the security plane.

### Inference plane

| Service | Role | Interfaces | Depends on |
|---|---|---|---|
| camera-service | Edge capture. Owns the V4L2 handle, the adaptive capture loop (15 fps idle, 60 fps active), the in-store ring buffer, and cache-and-forward during cloud outages. | local gRPC frame source; edge-initiated control stream to backend | USB camera, detect-gate-service |
| detect-gate-service | Always-on yolov8n-detect at 15 fps. Owns the presence state machine (instant entry, 30-frame debounced exit). | gRPC bidi presence stream to ai-service; edge-local rate signal to camera-service | camera-service, ai-service |
| ai-service | Heavy-path inference. Holds per-session and per-track tracker state, drives the classifier, reports events to the backend. | gRPC :50051 (Analyze); presence stream; calls defense and model server | detect-gate-service, adversarial-defense-service, model-serving-service |
| adversarial-defense-service | Pre-inference validator. Checks keypoint geometry, anatomical bounds, velocity; screens FGSM and PGD. | gRPC `defense.proto` ValidateKeypoints | none (stateless) |
| model-serving-service | NVIDIA Triton. Holds the pose models, swaps them from the registry without restart. | gRPC and HTTP (Triton native) | MLflow registry, Azure Blob |
| backend | FastAPI. HTTP and WebSocket to the frontend, orchestrates downstream gRPC services, owns operational data and fan-out. | HTTP `/api/v1/*`, WebSocket `/ws`; gRPC clients | MongoDB, Redis, ai-service, notification-service, auth-service, audit-service, analytics-service |
| notification-service | Multi-channel dispatch. Resolves channel preferences, enqueues delivery on Redis. | gRPC :50052 from backend, HTTP :8000 from Alertmanager | MongoDB, Redis |
| notification-worker | Celery worker. Pops jobs, calls the channel adapter, owns retry, backoff, and dead-letter handling. | Redis broker; Telegram, push, SMTP adapters | Redis, snapshot directory |

### Identity, security, and compliance plane

| Service | Role | Interfaces | Depends on |
|---|---|---|---|
| auth-service | Identity and access. argon2 hashing, JWT mint and refresh, HttpOnly cookies with CSRF, RBAC, lockout counters. | HTTP login/logout/refresh/me; gRPC `auth.proto` | MongoDB |
| audit-service | Tamper-evident log. Hash-chained append-only events, compliance reads, chain verification. | gRPC `audit.proto` AppendEvent / QueryEvents / VerifyChain | MongoDB |
| privacy-service | Personal-data lifecycle. Face blurring before snapshots leave the inference plane, retention sweep, right-to-erasure cascade. | HTTP erasure endpoint | MongoDB, Delta Lake, Azure Blob, audit-service |

### Data plane

| Service | Role | Interfaces | Depends on |
|---|---|---|---|
| ingest-service | Extract-load. Streams Mongo change streams and Redis pub/sub into the bronze tier, with scheduled batch for gaps. | Mongo change streams, Redis pub/sub, Delta Lake write | MongoDB, Redis, Delta Lake |
| analytics-service | Transform-and-serve. PySpark bronze to silver to gold, BI views over HTTP, weekly PDF report. | HTTP to backend analytics endpoints; report handoff to notification-service | Delta Lake, notification-service |

### ML platform plane

| Service | Role | Interfaces | Depends on |
|---|---|---|---|
| MLflow | Tracking server and model registry. | HTTP API | PostgreSQL, Azure Blob |
| feature-store-service | Feast. Online features in Redis for inference, offline in Delta Lake for training. | feature read and write | Redis, Delta Lake |
| drift-detection-service | KS-test on keypoint distributions against a baseline, alerts on shift. | emits to Alertmanager | baseline store |
| label-studio-service | Label Studio. Labeled datasets export to the silver tier. | HTTP; Delta Lake export | PostgreSQL, Delta Lake |
| training-orchestrator-service | Argo Workflows. Wraps training stages, triggered by drift, schedule, or manual run. | Argo on AKS; logs to MLflow | MLflow, drift-detection-service |
| federated-aggregator-service | Flower server. Coordinates federated rounds with edge clients. | Flower protocol | federated-edge-client |
| federated-edge-client | Edge agent for federated learning. Runs on the in-store box, contributes local updates to a round, pulls aggregated models. | Flower protocol to aggregator | federated-aggregator-service |

### Frontend

| Service | Role | Interfaces |
|---|---|---|
| frontend | Next.js dashboard: live event view, configuration, analytics. | HTTP `/api/v1/*`, WebSocket `/ws` |

### Data stores

MongoDB 7 holds operational state for backend, auth-service, audit-service, notification-service, and privacy-service. Redis 7 is the Celery broker, pub/sub fan-out, cache, rate limiter, refresh-token blocklist, lockout counters, anomaly-score cache, and the feature store online layer. PostgreSQL backs MLflow tracking and Label Studio metadata as two separate databases. Azure Blob holds DVC and MLflow artifacts, model weights, snapshots, and Delta Lake storage. Delta Lake runs a bronze, silver, gold medallion on Blob.

### Observability plane

Prometheus, Grafana, Loki, Alloy as the OTLP collector with every service exporting to `http://theft-alloy:4318`, Tempo, Alertmanager, and the exporters for node, MongoDB, Redis, and GPU, alongside netdata and portainer.

### Security plane

OPA Gatekeeper as admission controller, Istio for the service mesh and mTLS, and Kubernetes NetworkPolicies as the firewall. Declared here, walked in a later sprint.

## Contracts

Every arrow between services. gRPC channels are insecure today; Istio adds mTLS in a later sprint. Three overlays apply to every service and are listed once at the end.

### Frontend to backend

| Source | Target | Transport | Contract | Trigger |
|---|---|---|---|---|
| frontend | backend | HTTPS via Traefik | `/api/v1/cameras` CRUD JSON | dashboard action |
| frontend | backend | HTTPS via Traefik | `/api/v1/detections` CRUD and `/detections/analyze` multipart frame | dashboard action, debug upload |
| frontend | backend | HTTPS via Traefik | `/api/v1/alerts` CRUD and PATCH `/{id}/acknowledge` | guard interaction |
| frontend | backend | HTTPS via Traefik | `GET /api/v1/stats` returns `StatsResponse` | dashboard refresh |
| frontend | backend | WebSocket via Traefik | `/ws/alerts` and `/ws/cameras`, `{event, data}` envelope with ping heartbeat | connect, then push per upstream event |

### Edge frame and presence

| Source | Target | Transport | Contract | Trigger |
|---|---|---|---|---|
| camera-service | detect-gate-service | local gRPC intra-box | 15 fps gate feed pull | continuous on the box |
| camera-service | ai-service | local gRPC intra-box | active-window frame pull | on wake |
| detect-gate-service | ai-service | gRPC bidi stream | `presence.proto StreamPresence` | presence transition |
| detect-gate-service | camera-service | edge-local gRPC | capture-rate change | presence transition |

### Backend orchestration

| Source | Target | Transport | Contract | Trigger |
|---|---|---|---|---|
| backend | ai-service | gRPC unary :50051, keepalive 30s/10s, 8 MB max | `inference.proto Analyze(Frame)` returns `Detection` | frame analysis request |
| backend | notification-service | gRPC unary :50052 | `notification.proto SendAlert(Alert)` returns reply | detection over threshold, or direct POST `/alerts` |
| backend | auth-service | gRPC unary | `auth.proto VerifyToken` per request, `IntrospectSession` and `RevokeSession` on admin paths | every authenticated request |
| backend | audit-service | gRPC unary | `audit.proto AppendEvent / QueryEvents / VerifyChain` | auditable event, compliance read |
| backend | analytics-service | HTTP | BI views for analytics endpoints | dashboard analytics request |
| backend | camera-service | gRPC bidi stream | `camera_control.proto Control`, edge-initiated | operator control command |
| backend | MongoDB | Motor TCP | `cameras`, `detections`, `alerts` and related collections | every repository call |
| backend | Redis | redis-py async | cache and idempotency keys | read paths, idempotency middleware |
| backend | Redis pub/sub | PUBLISH | `alerts:{created,acknowledged,deleted}`, `cameras:{created,deleted}` | use-case write methods |
| Redis pub/sub | backend BroadcastService | PSUBSCRIBE on `alerts:*`, `cameras:*` | same channels and payloads | every published message, fans out to WebSocket |

### Detection and defense

| Source | Target | Transport | Contract | Trigger |
|---|---|---|---|---|
| ai-service | adversarial-defense-service | gRPC unary | `defense.proto ValidateKeypoints` | before heavy classification |
| ai-service | model-serving-service | gRPC and HTTP (Triton) | pose forward pass | heavy inference path |

### Audit fan-in

| Source | Target | Transport | Contract | Trigger |
|---|---|---|---|---|
| internal services and the compliance UI | audit-service | gRPC unary | `audit.proto AppendEvent` | any auditable event |

### Notification delivery

| Source | Target | Transport | Contract | Trigger |
|---|---|---|---|---|
| Alertmanager | notification-service | HTTPS POST `/webhooks/alertmanager`, bearer token, constant-time compare | `AlertmanagerWebhook` schema | infrastructure alert fires |
| notification-service | Redis Celery broker | `send_task` over Redis | task enqueue | inside the SendAlert handler |
| notification-worker | Redis Celery broker | brpop on the Celery queue | job pop | continuous |
| notification-worker | Telegram Bot API | HTTPS | `sendMessage` or `sendPhoto` with caption | per task, retries with exponential backoff and jitter |
| notification-worker | local filesystem | bind-mount read | snapshot image | when a snapshot is present |

### Data and ML platform

| Source | Target | Transport | Contract | Trigger |
|---|---|---|---|---|
| ingest-service | Delta Lake bronze | Mongo change streams, Redis pub/sub, batch | bronze write | continuous and scheduled |
| analytics-service | Delta Lake | PySpark | bronze to silver to gold transform | scheduled |
| analytics-service | notification-service | report handoff | weekly PDF | scheduled |
| training-orchestrator-service | MLflow | HTTP | log runs, register models | training run |
| model-serving-service | MLflow registry | registry pull | model swap source | registry update |
| feature-store-service | Redis and Delta Lake | online and offline | feature read and write | inference and training |
| drift-detection-service | Alertmanager | alert | drift alert | distribution shift past threshold |
| label-studio-service | Delta Lake silver | export | labeled dataset | on export |
| federated-aggregator-service | federated-edge-client | Flower protocol | federated round | per round |
| MLflow | PostgreSQL, Azure Blob | metadata and artifacts | tracking and registry storage | continuous |
| label-studio-service | PostgreSQL | metadata | project and annotation storage | continuous |

### Event egress

| Source | Target | Transport | Contract | Trigger |
|---|---|---|---|---|
| edge services | Azure Event Hub | event and telemetry egress, never frames | edge-to-cloud events | on event |

### Overlays

OTLP traces export from every internal service to Alloy at `http://theft-alloy:4318`. Every gRPC service exposes `grpc.health.v1.Health` Check and Watch. Every service exposes `/metrics`, with target wiring in `config/prometheus/prometheus.yml`.

### New protos

All five share package `theftdetection.v1`, the same namespace as `inference.proto`, `notification.proto`, and `common.proto`.

#### audit.proto

Defined in `audit.proto`.

A typed `oneof` replaces an untyped struct so every audit category passes the proto type system. The cost is one message per new category, which is rare.

#### presence.proto

Defined in `presence.proto`.

A bidi stream amortizes connection cost across the high-frequency flow, carries backpressure, and returns an explicit ack per event. A dropped person-entered event would leave the heavy path asleep, so the ack is load-bearing. The event kind is an enum because both kinds carry identical fields.

#### camera_control.proto

Defined in `camera_control.proto`.

The edge box opens the stream outbound, which solves NAT without inbound reachability. Pending commands sit in Redis under `camera_pending:{camera_id}` and survive a backend restart. The channel carries control only; frames take the local path.

#### defense.proto

Defined in `defense.proto`.

The call is unary because it sits on the synchronous path of the heavy classifier. The server stays stateless by taking velocity context in the request, which makes it scale horizontally without coordination. Three verdicts instead of two let a mildly suspicious result feed the classifier with a confidence penalty rather than being thrown away.

#### auth.proto

Defined in `auth.proto`.

gRPC carries service-to-service verification; login stays on HTTP because the frontend never speaks gRPC. The three RPCs split by authorization scope: every backend service calls VerifyToken, while Introspect and Revoke belong to admin paths. Eight statuses map to eight downstream behaviors, where expired hints a refresh, revoked forces re-login, and malformed flags the request as suspicious.

### Existing protos

`common.proto` holds `Bbox` as four floats and `Keypoint` as three, shared by `inference.proto`, `notification.proto`, and `defense.proto`. `inference.proto` defines `InferenceService.Analyze(Frame)` returning `Detection`; the backend calls the unary form. `notification.proto` defines `NotificationService.SendAlert(Alert)` returning a reply, with the worker handling channel delivery.

## Diagrams

### Use cases

<div style="overflow-x: auto;">
  <img src="diagrams/Use-case.png" alt="use case diagram">
</div>

### Components

<div style="overflow-x: auto;">
  <img src="diagrams/component.png" alt="component diagram">
</div>

### Deployment

<div style="overflow-x: auto;">
  <img src="diagrams/deployment.png" alt="deployment diagram">
</div>

### Sequence: runtime detection, login to alert

<div style="overflow-x: auto;">
  <img src="diagrams/sequence-1.png" alt="sequence diagram, runtime detection from login to alert">
</div>

### Sequence: training, ingest to promote

<div style="overflow-x: auto;">
  <img src="diagrams/sequence-2.png" alt="sequence diagram, training from ingest to promote">
</div>

### Activity: frame to alert

<div style="overflow-x: auto;">
  <img src="diagrams/activity-frame_to_alert.png" alt="activity diagram, frame to alert">
</div>

### Activity: camera configuration

<div style="overflow-x: auto;">
  <img src="diagrams/activity-admin_config.png" alt="activity diagram, camera configuration">
</div>

### Activity: model lifecycle

<div style="overflow-x: auto;">
  <img src="diagrams/activity-ml_lifecycle.png" alt="activity diagram, model lifecycle">
</div>

### Domain model

<div style="overflow-x: auto;">
  <img src="diagrams/class.png" alt="class diagram">
</div>
