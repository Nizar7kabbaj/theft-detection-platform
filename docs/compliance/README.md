# Compliance & Disclosure — TheftGuard

This folder contains the project's compliance and disclosure documentation
for a hypothetical European retail deployment of TheftGuard. Three
documents, written from the perspective of a hypothetical solution
provider delivering the system to a controller (the deploying retailer).

The author is a student; no commercial deployment exists. The framing
produces concrete, contractually-meaningful disclosures rather than
abstract academic statements. Every technical claim is verifiable
against the source repository.

---

## The headline

TheftGuard is a recall-tuned, human-in-the-loop, hybrid rule+ML
behavioral alert system. It uses pose estimation (no faces, no identity)
to flag potentially suspicious motion to a human guard, who decides
whether to act. It suits a supervised pilot deployment matching its
training viewpoint and customer base. It does **not** suit autonomous,
cross-deployment, or evidence-grade use.

A retailer evaluating TheftGuard for production deployment in France or
the EU should plan to: conduct a Data Protection Impact Assessment
before installation; refresh prefectoral CCTV authorization; update
in-store signage; replace the Telegram alert path with an EU-resident
equivalent; configure retention; perform per-deployment fairness
evaluation on their own customer population; and train guards to treat
alerts as prompts to look, not as evidence to act.

The provider's commitment is to disclosure, not to claims the evidence
does not support.

---

## The three documents

### [PRIVACY.md](./PRIVACY.md) — *regulatory honesty*

GDPR Articles 6, 9, 22, 28, 30, 35 applied to the system's actual data
flows. French CNIL specifics for video surveillance. Sub-processor
inventory and data residency. Telegram is named as a current compliance
gap with a stated roadmap. Retention is named as undefined with a
proposed default policy. Controller-vs-provider responsibilities split
explicitly.

**Read first if you are:** a DPO, a privacy reviewer, the controller's
legal team.

### [LIMITATIONS.md](./LIMITATIONS.md) — *technical honesty*

Model performance: F1 = 0.69, recall = 0.93, precision = 0.55, AUC = 0.45.
Why the operating point is recall-tuned, what AUC < 0.5 actually means,
why the LSTM does not drive alerts, why the bend rule does. The hybrid
rule+ML architecture and its design rationale. Operational limits
(lighting, occlusion, distance, single-camera). What the system is not.

**Read first if you are:** a technical reviewer, an interviewer, the
controller's engineering team.

### [BIAS.md](./BIAS.md) — *fairness honesty*

Single-store training, item-value bias, sample-size variance, inverted
class proportions in supervised mode. Demographic blindness of PoseLift
and what that prevents us from measuring. Specific failure-mode populations
(mobility-aid users, children, religious dress, customers picking up
dropped items). The recall-tuning + human-in-the-loop + no-persistent-identity
mitigation argument and its failure mode. Comparison against the realistic
alternative (direct human observation).

**Read first if you are:** an ethics reviewer, an academic reviewer, a
controller weighing fairness obligations.

---

## Reading paths by audience

| Audience | Suggested order | Time |
|----------|----------------|------|
| Client meeting attendee | This README only, then PRIVACY §10 + LIMITATIONS §10 + BIAS §9 | 5 min |
| DPO / legal reviewer | PRIVACY in full, then BIAS §3 and §5, then LIMITATIONS §7 | 30 min |
| Technical interviewer | LIMITATIONS in full, then BIAS §3, then PRIVACY §3 | 25 min |
| Academic reviewer | All three documents end-to-end | 45 min |
| Controller's engineering team evaluating deployment | All three, plus `ai-model/EVALUATION.md` and `ai-model/DATASET.md` | 60 min |

---

## Cross-references to other project artifacts

These three documents do not stand alone. They reference and depend on:

- **`ai-model/DATASET.md`** — PoseLift selection rationale and data structure.
- **`ai-model/EVALUATION.md`** — full evaluation report with confusion matrix, ROC curve, inference benchmark.
- **`ai-model/outputs/evaluation/metrics.json`** — raw metrics file.
- **Repo root `README.md`** — project overview, stack, run-it-locally instructions.

---

## Document maturity

| Document | Status | Word count | Last updated |
|----------|--------|------------|--------------|
| PRIVACY.md | First draft, shippable | ~1700 | 2026-05-07 |
| LIMITATIONS.md | First draft, shippable | ~1900 | 2026-05-07 |
| BIAS.md | First draft, shippable | ~2500 | 2026-05-07 |
| README.md (this file) | First draft, shippable | ~500 | 2026-05-07 |

These are first-draft disclosures suitable for the client meeting and
for inclusion in a portfolio. They do **not** substitute for a real
DPIA, a real fairness audit, or qualified legal counsel, and they say
so explicitly in their respective closing notes.

---

## A note on what this folder is missing

A genuinely production-ready compliance pack would also contain: a
Data Processing Agreement template (Art. 28), a Standard Contractual
Clauses module for non-EU sub-processors (Art. 46), a Records of
Processing template (Art. 30), a Data Subject Access Request workflow,
and a per-deployment DPIA input pack. None of these sit in this folder.
They are roadmap items for Phase 7 (documentation finalization).

Their absence is itself disclosed — see PRIVACY.md §9 and LIMITATIONS.md §9.