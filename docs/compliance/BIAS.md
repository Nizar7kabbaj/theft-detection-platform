# Bias & Fairness — TheftGuard

**Document type:** Bias and fairness disclosure
**Audience:** Reviewers, prospective deployers, technical readers
**Last updated:** 2026-05-07
**Owner:** Provider (see scope below)

---

## Document scope

This document is written from the perspective of a hypothetical solution
provider delivering TheftGuard to a European retail client. The author is
a student; no commercial deployment exists.

This is the document about **who the system fails on, and why**. Every
claim is either measurable in the project's artifacts (the PoseLift
dataset, the deployed model, the evaluation results) or named as an
explicit, unmeasured limitation of the methodology. No bias is
speculated; no fairness is claimed without evidence.

A processor unwilling to name the populations its product is unfair to
is a processor a controller should not deploy.

---

## 1. Dataset bias — PoseLift

The model is trained on the PoseLift dataset (TeCSAR-UNCC, WACV 2025).
PoseLift's strengths — pre-extracted keypoints, persistent track IDs,
academic licensing — were the basis for selecting it (see
`ai-model/DATASET.md`, ticket TDP-85). Its biases follow from how it
was constructed, and we name them here.

### 1.1 Single-store, single-geography bias

PoseLift was captured in **one store**. All 151 labeled instances
(43 shoplifting + 112 normal) come from the same retail environment,
with the same lighting, layout, camera positions, and customer base.

**Consequence:** any property of *that store's customer population* is
baked into the training distribution. If the store served a particular
neighborhood, the model has learned what shoplifting looks like *in
that neighborhood, at that store, with those cameras*. We have no
evidence the model generalizes; we have direct evidence (the live
demo's LSTM flicker, see `LIMITATIONS.md` §5) that it does not
generalize across camera viewpoints.

**Mitigation:** none in the current model. The roadmap (§8) requires
per-deployment fine-tuning before promoting the LSTM to the alert path.

### 1.2 Item-value bias

PoseLift's annotations reflect the items its labelers could *see being
taken*. Large items are visually obvious; **small items concealed by
palming are systematically under-represented** in the labeled positives.

**Consequence:** the model is more confident about theft signatures
involving large items (reaching for high shelves, large bags, jacket
concealment of bulky goods) than about theft signatures involving small
items (palming jewelry, slipping cosmetics into a sleeve, swallowing
items). This is not a model defect — it is a label distribution effect
inherited from the dataset.

**Real consequence at deployment:** a retailer in a category dominated
by small high-value items (pharmacy, cosmetics, jewelry) will see lower
true effective recall than a retailer in a category dominated by large
items (apparel, electronics).

**Mitigation:** none at the model level. The recall-tuning at the
threshold level (§3) partially compensates by lowering the bar for
*any* suspicious motion, but it cannot recover signatures that are
absent from the training data.

### 1.3 Sample size

151 labeled instances, of which only 47 are in the labeled test split
(used as supervised training data via 5-fold CV — see
`ai-model/DATASET.md`). This is **small** for a behavioral classifier.

**Consequence:** high cross-fold variance. The 5-fold CV F1 is
0.569 ± 0.077 — meaning a different random seed could have produced a
deployed model with F1 anywhere in the [0.49, 0.65] range. The
deployed model is the best fold (F1 = 0.693), which is a defensible
choice for a demonstration but should not be confused with a stable
estimate of the model's true performance. The honest expected F1 in
production is closer to the cross-fold mean.

**Mitigation:** disclose the cross-fold variance alongside the deployed
model's metrics (done — see `ai-model/EVALUATION.md` and
`LIMITATIONS.md` §2).

### 1.4 Class proportion in the labeled subset

PoseLift's labeled test files contain *anomaly* windows in approximately
60% of frames — a quirk of curation, since the dataset was assembled
for unsupervised anomaly detection where labeled clips are clips that
*contain* an anomaly somewhere.

**Consequence:** the supervised training regime sees an inverted class
balance compared to a real deployment, where the prior probability of a
suspicious window in any given 2-second slice is *far* below 50%. The
model's score distribution is calibrated to the training prior, not the
deployment prior.

**Real consequence at deployment:** the deployed precision (0.55) is
likely to be *worse* on a real store feed than on the test set, because
the deployment-time prior of `suspicious` is much lower than the
training-time prior. False alarms will dominate even more than the
metrics suggest.

**Mitigation:** this is the strongest argument for the **human-in-the-loop
design** (§5). A guard reviewing alerts can absorb a high false-positive
rate; an autonomous system could not.

---

## 2. Demographic blindness — what we cannot measure

PoseLift **does not publish participant demographics.** We do not know:

- Age distribution of customers in the source store.
- Sex / gender distribution.
- Skin tone distribution.
- Cultural dress distribution (e.g., presence of veils, robes,
  oversized garments that change skeletal silhouette).
- Body type distribution.
- Mobility-aid users (wheelchair, crutches, walker).

**Consequence:** we cannot compute fairness metrics across protected
attributes. We cannot say whether the model has equal recall for men
and women, whether it produces more false positives on dark-skinned
customers, whether it confuses religious dress for theft posture. We
have no evidence either way.

**This is itself a bias of the methodology, and we disclose it as
such.** The honest sentence: *the model has been trained and
evaluated on a dataset that does not enable disaggregated fairness
analysis. Any retailer deploying this system is doing so without
demographic fairness evidence, and any production deployment must
treat fairness evaluation as a precondition, not an afterthought.*

What a real deployment would require:

1. A fairness evaluation protocol on the controller's own customer
   population (using video from the controller's existing cameras,
   with appropriate labeling and consent).
2. Disaggregated metrics — recall, precision, false-positive rate
   computed within each protected-attribute slice.
3. A documented threshold for fairness — what disparity is acceptable
   before deployment is paused or thresholds are re-tuned.

None of this is in scope for the demonstration. All of it is in scope
for production.

---

## 3. Model bias — the operating point is a fairness choice

The deployed model is recall-tuned: recall = 0.93, precision = 0.55
(see `LIMITATIONS.md` §3). This trade is a privacy/fairness choice, not
a neutral engineering choice.

**The choice favors the retailer's interest** (catching theft) **at the
cost of an inflated false-positive rate against customers**. Forty-five
out of every 100 flagged customers are flagged in error.

**Whose error is it?** The system has no facial recognition, no identity,
no record of who was flagged. The error is absorbed by the *guard*, who
spends ~2 seconds dismissing the dashboard alert; the customer, in the
intended workflow, never knows they were flagged.

**The risk this design accepts.** If the controller deviates from the
intended workflow — if a guard treats a TheftGuard alert as probable
cause and approaches the customer — the false-positive rate becomes a
direct customer-facing harm. **The system's privacy guarantees collapse
when human-in-the-loop is replaced by human-as-rubber-stamp.**

**The mitigation.** This is named in `LIMITATIONS.md` §7 ("the system
is not autonomous") and reinforced in the controller obligations under
`PRIVACY.md` §4: the controller is responsible for guard training that
treats alerts as *prompts to look*, not as *evidence to act*. The
provider's deliverable cannot enforce guard behavior; it can only
document the assumption.

A controller deploying this system without guard training accepting the
human-in-the-loop premise is operating an autonomous behavioral
profiling system, with the corresponding GDPR Art. 22 obligations.

---

## 4. Specific failure modes worth naming

The following customer populations are at elevated risk of being
mis-classified by the system. Each is named, the cause is located in
the pipeline, and the response is stated.

### 4.1 Customers picking up dropped items

The bend rule fires on torso inclination > 60° for ≥ 2 seconds. A
customer picking up dropped keys, retrieving an item from a low shelf,
or tying their shoe will trigger this. The rule cannot distinguish
*reason* from *posture*.

**Frequency:** common. **Severity:** low (false positive, dismissed by
guard). **Response:** documented; expected; guard training compensates.

### 4.2 Customers with mobility aids

Wheelchairs, walkers, and crutches partially occlude the lower-body
keypoints YOLOv8-pose expects. The pose estimator produces low-confidence
or missing hip/knee/ankle keypoints, which propagate into the LSTM as
zero-vectors (see `PROJECT_CONTEXT.md` lesson #57).

**Effect:** unpredictable LSTM behavior; the bend rule may misfire on
the seated posture of a wheelchair user.

**Severity:** moderate. A wheelchair user repeatedly false-flagged is a
specific dignity harm. **Response:** the system should not be deployed
in stores where mobility-aid users are a significant customer fraction
without per-deployment validation. The roadmap (§8) calls for a
mobility-aid carve-out — keypoint-based detection of seated posture,
suppressing alerts on detected wheelchair users.

### 4.3 Children

Pose estimation models are trained predominantly on adult skeletons.
Child proportions (larger head relative to body, shorter limbs) produce
lower-confidence keypoints and unusual joint angles relative to adult
training data. The LSTM, in turn, has not seen child skeletons in
PoseLift to a known degree (PoseLift does not disclose age).

**Effect:** unknown. Could go either way — under-detection (false
negatives on child shoplifters) or over-detection (false positives on
playing children).

**Severity:** moderate. Falsely flagging a child causes specific
parental-trust and dignity harms. **Response:** acknowledged; the system
should not be deployed in stores with significant child traffic
(toy stores, children's clothing) without validation.

### 4.4 Customers in religious or cultural dress

Loose-fitting garments (abayas, kaftans, oversized traditional dress,
some monastic dress) change the silhouette pose estimation produces.
Veils that cover the head can lower nose-keypoint confidence, which
matters for the bend rule (which uses the nose for desk-camera variants).

**Effect:** unknown direction. Possibly elevated false positives if the
silhouette change is read as concealment posture; possibly elevated
false negatives if the keypoints are too low-confidence to enter the
LSTM at all.

**Severity:** high if biased systematically. **Response:** named here as
a specific category requiring per-deployment evaluation. The methodology
to evaluate it (disaggregated fairness analysis) is in §2.

### 4.5 Tall and short customers

Bend angle is computed from absolute joint positions normalized to
bounding-box scale, but the threshold (60°) is fixed. Customers at the
extremes of height may bend further or less far for the same physical
action (reaching for a low shelf), producing different rule-firing
rates.

**Severity:** low. **Response:** a per-deployment threshold tune is
trivially possible (the angle is one configuration line). This is a
roadmap item.

---

## 5. The mitigation argument — recall + human-in-the-loop

The provider's response to the biases above is **not** a claim that the
model is unbiased. The response is structural:

1. **Recall is high (0.93), precision is moderate (0.55)** by design.
   This means the model errs toward over-flagging, not under-flagging.
   In a fairness frame, this is the *less* harmful direction: the cost
   of over-flagging is absorbed by the guard, while under-flagging
   would mean the system disproportionately misses theft by populations
   under-represented in training (a fairness harm to the retailer) *and*
   gives a false sense of security.
2. **Human-in-the-loop validation is mandatory.** Every alert is
   reviewed by a guard; no alert produces an automated action. The
   guard is the system's fairness backstop. This works only if the
   guard is trained appropriately (see §3).
3. **The system is not facial recognition and has no memory.** A
   customer flagged once is not flagged-on-sight on subsequent visits.
   There is no demographic-level record. The error population on day N
   is independent of day N-1.

These three properties together do not eliminate bias — they bound the
*persistent harm* a biased decision can produce. A biased flag becomes
a 2-second guard interaction and is then forgotten. This is materially
different from a biased flag entering a permanent database.

The argument's failure mode is the human-in-the-loop assumption. If
the controller deploys without it, the bias arguments above no longer
hold and the system becomes a behavioral profiling tool with all the
fairness obligations that follow.

---

## 6. What we cannot mitigate, and why disclosure is the substitute

Some biases are not addressable in the current scope:

- **Demographic blindness of PoseLift.** Cannot be fixed without a new
  dataset. Disclosed in §2.
- **Item-value bias.** Cannot be fixed without re-labeling PoseLift or
  collecting new data. Disclosed in §1.2.
- **Single-store generalization gap.** Cannot be fixed without
  per-deployment fine-tuning. Disclosed in §1.1 and roadmap §8.

For each, the response is **structured disclosure**. A controller who
reads this document knows what they are accepting. A controller who
reads marketing copy claiming this product is "fair" or "unbiased" is
being misled.

This is the central argument: in the absence of fairness *evidence*,
the substitute is fairness *transparency*. Naming the biases is the
ethical floor, not the ceiling.

---

## 7. Comparison against the alternative

A useful question: *is TheftGuard fairer or less fair than what it
replaces?*

The realistic alternative in a small or mid-size retailer is **direct
human observation** — a guard watching cameras, or a clerk watching
the floor. Direct human observation has its own well-documented
biases: studies of retail loss prevention consistently find
disproportionate surveillance of minority customers, young customers,
and customers perceived as low-income.

TheftGuard's biases are described above. They are real. They are not
the same biases as a human observer's biases, and in some respects
(no demographic memory, no cross-session re-identification, no
facial features) they are more bounded than a human's.

**This is not an argument that TheftGuard is fair in the abstract.**
It is an argument that *replacing* a human observer with TheftGuard
is not a strict fairness regression, and may be a fairness improvement
on certain axes. A controller deciding to deploy is choosing between
two flawed systems, not between TheftGuard and a fair baseline.

The honest framing for a controller: *"What biases am I trading away,
and what biases am I accepting in their place?"*

---

## 8. Roadmap

Each unmitigated bias maps to a roadmap item. None are ready today.

| Bias | What would address it | Phase |
|------|----------------------|-------|
| Single-store training | Per-deployment fine-tuning on controller cameras | Post-meeting |
| Item-value bias | Re-labeling or new dataset focused on small-item theft | Not in current scope |
| Demographic blindness | Disaggregated fairness evaluation on controller's customer population | Pre-production (controller) |
| Mobility-aid false positives | Wheelchair/walker detection with alert suppression | Phase 6 |
| Child mis-classification | Validation on child-traffic deployments before rollout | Pre-production (controller) |
| Religious/cultural dress | Disaggregated fairness slice in the §2 evaluation | Pre-production (controller) |
| Height-induced bend-angle variance | Per-deployment threshold tuning | Configuration, available now |
| Inverted training-prior calibration | Re-train with deployment-prior-matched class weights | Post-meeting |

---

## 9. Summary line

TheftGuard is trained on a small, single-store, demographically
opaque dataset. Its biases are named in this document. Its mitigations
are structural (recall-tuned + human-in-the-loop + no persistent
identity), not architectural. A controller deploying this system
without per-deployment fairness evaluation and validated guard training
is not deploying it as the provider intended.

The provider's commitment is to disclosure, not to claims of fairness
the evidence does not support.

---

*This document does not constitute a fairness audit. The provider's
deliverable is the system as described in the source repository;
fairness in any specific deployment depends on the controller's
customer population, guard training, and operational practices.*
