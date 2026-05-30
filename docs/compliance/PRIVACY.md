# Privacy & GDPR Compliance — TheftGuard

**Document type:** Privacy disclosure and compliance scope
**Jurisdiction:** European Union (GDPR) with French CNIL specifics
**Last updated:** 2026-05-07
**Owner:** Provider (see scope below)

---

## Document scope

This document is written from the perspective of a hypothetical solution
provider delivering TheftGuard to a European retail client. The author is
a student; no commercial deployment exists. The framing produces
concrete, contractually-meaningful disclosures rather than abstract
academic statements. All technical claims about the system's behavior are
factual and verifiable in the codebase.

Throughout this document:

- **The system** / **TheftGuard** — the technical artifact described in
  the source repository.
- **The provider** — the entity that builds and supplies the system.
  Acts as a **processor** under GDPR Article 4(8).
- **The controller** — the deploying retailer who installs cameras,
  determines purposes, and is legally accountable. Acts as a **controller**
  under GDPR Article 4(7).
- **The data subject** — a person filmed by a camera on which the system
  is running.

---

## 1. Data inventory — what flows through the system

| Data | Source | Purpose | Storage | Retention (current) |
|------|--------|---------|---------|---------------------|
| Raw video frames | Camera (RTSP / webcam) | Inference input | **In-memory only**, never persisted | None — discarded each frame |
| Pose keypoints (17 × x,y,confidence) | YOLOv8-pose on raw frame | Behavioral inference | In-memory; published to Event Hub | 1 day (Event Hub retention) |
| Person track IDs (ByteTrack) | YOLOv8 tracker | Per-person classification | In-memory only | None |
| Alert snapshots (JPEG) | OpenCV imwrite on alert | Forensic context for guard | `ai-model/outputs/snapshots/` | **Undefined** — see §7 |
| Alert metadata (timestamp, camera, severity) | FastAPI POST | Audit + dashboard | MongoDB Atlas (eu-west-3, Paris) | **Undefined** — see §7 |
| Telegram message + photo | Background task | Guard notification | Telegram servers (non-EU) | Per Telegram policy — see §6 |

**The system does not collect, store, or transmit:** facial images, voice,
biometric templates, names, identifiers from loyalty cards, payment data,
or any data linkable to a known individual outside the cameras' field of view.

---

## 2. Legal basis (GDPR Art. 6)

The lawful basis for processing is **legitimate interest** under
Art. 6(1)(f) — the controller's interest in preventing theft on premises
they operate. This requires the controller to perform a documented
**Legitimate Interest Assessment (LIA)** weighing:

- **Purpose:** loss prevention, deterrence, evidence for incident review.
- **Necessity:** the processing must be necessary, not merely useful — i.e.
  no less-intrusive alternative meets the purpose.
- **Balancing:** the controller's interest vs the data subject's reasonable
  expectation of privacy in a retail space.

The provider's position: the system **supports** the LIA, it does not
replace it. Two design choices reduce the privacy cost relative to
traditional CCTV with human review:

1. Raw video is never persisted. Only pose keypoints (a 51-dimensional
   abstraction) and on-alert snapshots leave the camera node.
2. The classifier is recall-tuned (recall = 0.93, precision = 0.55) and
   a human guard validates alerts before any action is taken. The system
   does not produce automated decisions with legal or similarly
   significant effects (Art. 22).

The LIA itself is the controller's responsibility, not the provider's
deliverable.

---

## 3. Special category data (GDPR Art. 9)

Pose keypoints occupy a contested position under Art. 9.

**Provider's analysis:**

- Raw skeleton coordinates `(x, y, confidence)` for 17 body joints, taken
  in isolation, are **not biometric identifiers** in the Art. 4(14) sense.
  They do not uniquely identify a natural person; two people with the same
  height and posture produce nearly identical skeletons.
- However, **persistent track IDs** assigned by ByteTrack within a session
  re-identify a person across frames for the duration they remain in the
  camera's view (typically seconds to minutes). This is *session-scoped
  re-identification*, not biometric identification.
- The system **does not** generate cross-session, cross-camera, or
  long-term biometric templates. Track IDs are not persisted beyond the
  session.

**Conclusion:** the provider does not treat pose data as Art. 9 special
category data. The controller should confirm this position with their
DPO and, where appropriate, the CNIL, before deployment. If the
controller's regulator takes the contrary view, the lawful basis would
need to shift to explicit consent (Art. 9(2)(a)) — which is generally
not workable in a retail CCTV context — or to an Art. 9(2) derogation.

---

## 4. Controller obligations the provider does not discharge

The items below are the **controller's** legal obligations and are not
produced or covered by the provider's deliverable:

1. **DPIA (Art. 35).** Systematic monitoring of a publicly accessible
   area combined with automated behavioral inference triggers the DPIA
   threshold. The controller must conduct one before deployment. The
   provider supplies this document and `LIMITATIONS.md` as inputs.
2. **DPO appointment (Art. 37).** Required if the controller's core
   activities involve large-scale systematic monitoring. Most retailers
   meeting this threshold already have a DPO; the provider does not.
3. **Records of processing (Art. 30).** The controller maintains the
   register; the provider supplies a per-system data-flow diagram on
   request.
4. **Information to data subjects (Arts. 13–14).** The controller is
   responsible for in-store signage. CNIL's video surveillance
   *délibération* (most recent: n° 2022-051) requires visible signs
   identifying the controller, the purpose, the legal basis, the
   retention period, and contact details for rights exercise.
5. **Prefectoral authorization.** Under the French *Code de la sécurité
   intérieure* (L223-1 et seq.), CCTV systems filming areas accessible
   to the public require prefectoral authorization renewable every five
   years. The provider's system inherits whatever authorization the
   underlying camera infrastructure already holds.
6. **Data subject rights (Arts. 15–22).** The controller receives and
   processes access, rectification, erasure, restriction, and objection
   requests. The provider supplies tooling to honor erasure requests on
   demand (see §8).

---

## 5. Sub-processors and data residency

| Sub-processor | Role | Region | Notes |
|---------------|------|--------|-------|
| Microsoft Azure (Event Hub) | Pose event stream | Spain Central | EU residency confirmed. Standard contractual clauses via Azure DPA. |
| MongoDB Atlas | Alert metadata persistence | AWS eu-west-3 (Paris) | EU residency confirmed. MongoDB Inc. DPA covers transfers. |
| Telegram FZ-LLC | Alert delivery to guards | **Non-EU (UAE / distributed)** | **Flagged — see §6.** |

The controller must execute a Data Processing Agreement (DPA) with the
provider under Art. 28, and the provider's DPA back-to-backs each
sub-processor's terms.

---

## 6. Telegram — known compliance gap, roadmap item

The current alert delivery channel uses the Telegram Bot API. Telegram is
a **non-EU sub-processor** with limited transparency on its data handling,
and its Bot API messages — including the JPEG snapshot attached to each
alert — pass through Telegram's infrastructure outside the EU.

**This is disclosed as a compliance gap, not defended.** It works for a
development demonstration; it would not work in production without one
of the following:

- A Standard Contractual Clauses arrangement with Telegram covering Art. 46
  international transfers (Telegram does not currently publish one).
- Replacement of Telegram with an EU-resident channel: an in-app
  notification on the controller's existing security dashboard, an SMS
  gateway with EU residency, or an email gateway with EU residency.

The post-meeting roadmap replaces Telegram with an EU-resident
notification path (Azure Service Bus + internal dashboard). That is the
recommended production configuration.

---

## 7. Retention — current state and proposed policy

**Current state:** alert snapshots in `ai-model/outputs/snapshots/` and
alert documents in MongoDB have **no automatic retention policy**. This
is an open issue.

**Proposed policy** (controller-configurable, defaults shown):

| Asset | Default retention | Rationale |
|-------|-------------------|-----------|
| Alert snapshot JPEG | 30 days | Sufficient for incident review and any law-enforcement handover. |
| Alert metadata document | 90 days | Longer than image to support trend analysis with image already deleted. |
| Aggregated statistics (no personal data) | Indefinite | Counts and rates are non-personal. |
| Event Hub pose events | 1 day (current) | Set at the Event Hub namespace level; sufficient for downstream consumers. |

The provider commits to delivering a retention enforcement job (cron-style
deletion of expired snapshots and Mongo documents) before any production
deployment. This is currently **not implemented** and is disclosed as such.

---

## 8. Data subject rights — what the provider supplies

A data subject filmed by a deployed camera has rights under GDPR Arts.
15–22. The provider supplies:

- A **deletion endpoint** (planned, not implemented) accepting a time
  window + camera ID, purging matching snapshots and Mongo documents.
- A **redaction utility** (planned) blurring all but the requesting
  individual in any retained snapshot, for access requests.
- Documentation enabling the controller to answer access requests within
  the Art. 12(3) one-month deadline.

What the provider **cannot** supply:

- Identification of which snapshots contain a given individual. Without
  facial recognition (which the provider deliberately does not implement),
  matching a request to records is the controller's responsibility,
  typically via timestamp + camera location supplied by the requester.

---

## 9. Roadmap to production-grade compliance

| Item | Status | Phase |
|------|--------|-------|
| EU-resident notification channel (replace Telegram) | Designed, not built | Phase 5 deferred (Service Bus + dashboard) |
| Automatic retention enforcement | Not built | Phase 5 deferred |
| Deletion / redaction endpoints | Not built | Phase 6 |
| Audit log of all alert dispatches | Partial (Mongo writes exist; not tamper-evident) | Phase 6 |
| Per-deployment DPA template | Not drafted | Phase 7 |
| DPIA input pack for controllers | This document + `BIAS.md` + `LIMITATIONS.md` | Phase 5 ✅ |

---

## 10. Summary for the controller

A retailer evaluating TheftGuard for deployment in France should plan to:

1. Conduct a DPIA before installation, using this document and the
   `LIMITATIONS.md` and `BIAS.md` files as input.
2. Confirm or refresh prefectoral authorization for the affected cameras.
3. Update in-store signage to reflect automated behavioral analysis.
4. Execute a DPA with the provider under Art. 28.
5. Replace the Telegram alert channel with an EU-resident equivalent, or
   accept the Art. 46 transfer risk in writing.
6. Configure retention values in line with their internal policy.
7. Establish a process for receiving and answering data subject requests.

The provider's role is to make each step tractable. The provider does not
perform them on the controller's behalf.

---

*This document does not constitute legal advice. The controller is
responsible for obtaining qualified legal counsel before deployment.*