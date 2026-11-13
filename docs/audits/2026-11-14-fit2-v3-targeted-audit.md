# Targeted Audit: `fit2-boundary-contrast-v3` (`c2e4eb37`)

- **Date:** 2026-11-14
- **Auditor:** Task C (`fit2-gate-c`)
- **Candidate:** `F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\fit2-boundary-contrast-v3` (`model.safetensors` SHA-256 `c2e4eb37424b15b3cbf8a7fb0509c70b8c02f0ddc0cd1d28f456de7364d2e0be`, `run-records-fit2-boundary-contrast-v3`, `fit2-improve-a` commit `428d91831fb66c9162a498a9eabf299fd2b76169`)
- **Decision:** **`PROMOTION_REJECT`** (Candidate lineage/archive integrity verified; promotion blocked by unsafe draft leaks and supported coverage regression.)

---

## 1. Lineage, Archive Integrity & Immutability Verification

- **Baseline & Serving Immutability:**
  - `reconstructed-fit2-supcon-20261113/model.safetensors`: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (unchanged).
  - `distilbert-supportiq/model.safetensors`: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (unchanged).
- **Candidate Archive & Sidecar Checksums:**
  - `archive_sha_inventory.json`: 7/7 files match, 0 mismatches; model reloads cleanly (`46` labels, `30522` vocab). Note: `candidate_provenance_manifest.json` carries `candidate_name: "fit2-supcon-energy-boundary-v1"` and `calibration_manifest.json` records `T=1.0`, `calibrated=True`, `calibration_sample_count=832`, `selective_rejector.enabled=False`.
  - `run-records-fit2-boundary-contrast-v3`: `status.json` is `"complete"`; `sidecar_sha_inventory.json` (`23` entries) and `inputs/inputs_sha256_inventory.json` (`14` entries) have 0 mismatches.
- **Parity & Split Isolation (`fit2_gate_report.json` / `acceptance_gate_report.json`):**
  - `runtime_parity_audit.passed = true` (`probe_count=4`, `probe_temperature=1.0`, 0 tokenization/label/score mismatches, `engine_enforces_experimental_rejection=true`).
  - `split_isolation_and_contamination.passed = true` (0 train/cal/eval group or text overlaps, 0 gold matches; train/cal/eval counts `11484 / 886 / 178`).
  - Gate verdict: **`REJECT`** (`holdout_34_label_unsafe_draft_leak`, `mandatory_escalation_unsafe_draft_leak`, `oos_draft_leak`).

---

## 2. Suite Comparison (`post_fit_eval_summary.json`)

| Metric | Serving (`dc7af8cf`) | Original (`f695b1fe`) | v3 (`c2e4eb37`) |
|---|---:|---:|---:|
| `ml_oos_80` unsafe leaks | `0/80` | `0/80` | **`1/80`** (`oos-other_domain-16`) |
| `ml_noise_420` `acc_12` / `safe` | `0.6548` / `0.9214` | `0.8571` / `0.9381` | `0.8643` / `0.9571` |
| `ml_noise_420` `corr / raw_draft` | `177 / 210` | `267 / 293` | `271 / 289` |
| `system_acceptance_156` `mand63` strict | `55/63` (`0` leaks) | `57/63` (`2` leaks) | **`60/63` (`1` leak: `uns-track_delivery-01`)** |
| `system_acceptance_156` `draft34` corr/raw | `17 / 21` | `25 / 28` | `27 / 29` |
| `final_acceptance_24` `ans12` corr/raw | `4 / 5` | `10 / 10` (`0` wrong) | **`8 / 8` (`0` wrong; dropped case 10, 12)** |
| `final_acceptance_24` unanswerable leaks | `0/8` | `0/8` | `0/8` |
| `independent_holdout_178_pos` `esc34` leaks | — | `3` Runner / `4` Engine | **`1`** (`contrast_auth_pos_eval_136`) |
| `bitext_test_6690` macro-F1 | — | `0.996313` | `0.99617` |

---

## 3. Paired Probe Root Causes (`orig f695b1fe` vs `v3 c2e4eb37`)

Paired telemetry in [probes.json](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-gate-c/artifacts/evaluation/fit2_v3_targeted_audit_20261114/probes.json) evaluated all three surfaces separately:
- **Bare `decide_route`** ([routing.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-gate-c/apps/core_backend/intent/routing.py)): enforces `SUPPORTED_12_INTENTS`, class thresholds ([intent_policy.v2.json](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-gate-c/apps/core_backend/config/policies/intent_policy.v2.json)), and `PERSONAL_ORDER_REQUIRED`.
- **`Engine._analyse`** ([engine.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-gate-c/apps/ai_service/engine.py)): enforces confidence/margin thresholds and `selective_rejected`, but has **no** `missing_order_id` slot guard.
- **`PipelineRunner.run` (offline `_OfflineValidSpyLLM`)**: adds slot/order lookup guards; validates draft **eligibility**, not real LLM generation quality.

### A. `uns-track_delivery-01` Leak + `final-case-10`/`12` Drop (Proven `track_order` Contradiction & Over-Exposure)
1. **`uns-track_delivery-01`** (*"Can you check the delivery vehicle live GPS tracking?"*, gold `track_delivery`, `is_personal_lookup=False`):
   - `orig`: `track_order` `0.15268` (`margin=0.0513`, `H=3.3073`) -> `clarify` / `manual_fallback` (safe).
   - `v3`: `track_order` `0.67684 >= 0.65` (`margin=0.4773`, `max_logit=4.3688`, `energy=-4.7591`, `H=1.2756`) -> **leaks `retrieve_draft` on `Engine._analyse`**, while bare `decide_route` and `PipelineRunner` return `clarify ['missing_order_id']` strictly due to missing `order_id`, **not** intent boundary correctness.
2. **`final-case-10`** (*"The app shows my order was delivered but I never received the package from the courier."*, gold `delivery_issue`):
   - `orig`: `delivery_issue` `0.89111` (`retrieve_draft`) -> `v3`: `delivery_issue` `0.50965 < 0.70`, because `track_order` jumped `0.027 -> 0.33946` -> dropped to `clarify` / `manual_fallback`.
3. **`final-case-12`** (*"My bank account was debited but my order status on Tiki still shows Awaiting Payment."*, gold `payment_issue`):
   - `orig`: `payment_issue` `0.91608` (`retrieve_draft`) -> `v3`: `payment_issue` `0.70146 < 0.75`, because `track_order` jumped `0.020 -> 0.1621` -> dropped to `clarify` / `manual_fallback`.
4. **Root Cause Observed in Training Data (`RR_V3/inputs/` & `boundary_contrast_data.py`):**
   - Authoring `28` `track_order` + `12` `track_delivery` contrast items created a **direct cross-split semantic contradiction** on live courier/parcel tracking: `contrast_auth_pos_cal_091` (*"Can you check the live delivery progress of my current parcel?"*) and `oh_to_trn_05` (*"Tell me where my delivery truck is right now..."*) are labeled `track_order`, contradicting `td_to_trn_01` (*"Share the driver's live GPS delivery status for my street drop-off."*) labeled `track_delivery`.
   - Meanwhile `track_order` had `28` contrast rows (`x4` repeat = `112` effective rows vs `8-16` base for other `supported_12` classes), biasing `track_order` logits upward on delivery/status-adjacent queries.

### B. `oos-other_domain-16` Leak (Telecom Negative Gap + Uncalibrated OOD Score)
- Query (*"My phone carrier charged me for roaming."*, `category=other_domain`): `orig` predicted `delivery_issue` `0.49723` (`H=2.450`, blocked on all 3 surfaces); `v3` drifted to `delivery_issue` `0.75927` (`margin=0.7331`, `max_logit=4.1344`, `energy=-4.4098`, `H=1.3798`), leaking `retrieve_draft` on all 3 surfaces.
- `boundary_neg_train` (`115` raw rows: `15` `off_domain_unrelated` + `10` `off_domain_homonym` + `16` authored compound) has **0** telecom/carrier-roaming negatives (max token Jaccard `0.15`). Simultaneously `max_neg_cal_supported12_prob` rose `0.5577 -> 0.6349`, yet `fit_temperature_on_calibration_logits` ([train_domain_candidate.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-improve-a/pipeline/training/train_domain_candidate.py#L434-L454)) fits `T >= 1.0` strictly on positive calibration NLL (`T=1.0`), ignoring negative calibration logits, and `selective_rejector.enabled=False`.

### C. `contrast_auth_pos_eval_136` Leak (Store-Return Channel Taxonomy Overlap)
- Query (*"Is returning an item at a brick-and-mortar branch allowed?"*, gold `return_product_in_store`): `orig` predicted `return_policy` `0.97860` and `v3` predicted `return_policy` `0.96989` (`return_product_in_store=0.00696`, `max_logit=6.21`, `energy=-6.24`, `H=0.237`), leaking `retrieve_draft` on all 3 surfaces.
- `return_policy` (active policy eligibility rules) overlaps semantically with `return_product_in_store` (in-person channel); `branch` paraphrase coverage is sparse in train (`2` rows), while compound `neg_train` items (`compound_auth_train_002`) push `"return policy ... in store"` phrasing toward uniform entropy.

---

## 4. Existing Repo Calibration / Rejector Mechanisms

The runtime and gate already support `selective_calibration.v1` without architectural changes:
- [classifier_acceptance_gate.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-gate-c/pipeline/evaluation/classifier_acceptance_gate.py#L495-L570), [engine.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-gate-c/apps/ai_service/engine.py), and `GateSequenceClassifier` natively support scalar `temperature` and logistic `selective_rejector` (`logit_geometry_v1` 8d, `cls_l2_plus_logit_geometry_v1` 776d), enforced end-to-end (`engine_enforces_experimental_rejection=true`).
- **Capability boundary:** `selective_rejector` only emits `abstain` / `manual_fallback` without altering the top-1 class. It can address OOD confidence spikes (`oos-other_domain-16`), but **cannot** resolve in-distribution semantic misclassifications (`uns-track_delivery-01` -> `track_order` at `0.677`, `contrast_auth_pos_eval_136` -> `return_policy` at `0.970` whose logit geometry mirrors clean supported `return_policy`).

---

## 5. ONE Recommended Next Step & Feasibility Assessment

**Single smallest generalizable next step:** Starting from `reconstructed-fit2-supcon-20261113` (`f695b1fe`), run one taxonomy-clean, exposure-balanced contrast+OOD training pass combined with existing `selective_calibration.v1` post-hoc calibration (no new model architecture):
1. Remove the `track_order` vs `track_delivery` cross-split definition conflict ("live delivery/truck progress" cleanly separated from active `track_order` policy) and balance `supported_12` contrast exposure (`~8-12` rows/class instead of `28` `track_order` rows), while adding clean in-store paraphrase diversity for `return_product_in_store`.
2. Broaden `boundary_neg_train` non-retail domain diversity (e.g., telecom, consumer utilities, general non-retail services — without touching any eval or C36 prompts).
3. Fit existing `selective_calibration.v1` (`T` + `cls_l2_plus_logit_geometry_v1` from [train_closure_candidate.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-improve-a/pipeline/training/train_closure_candidate.py#L830-L910)) strictly on disjoint calibration (`pos_cal + neg_cal`), selecting parameters for `0` unsafe leaks subject to preserving `supported_12` coverage.

---

## 6. Candid Unknowns & Scope Disclosures

- **Coverage + zero-unsafe feasibility is NOT yet proved:** Retaining `>=10/12` `final_acceptance_24` coverage while achieving `0` unsafe leaks across `mand63` / `ml_oos_80` / `esc34` with existing clean data + `selective_calibration.v1` remains unverified; `v3` dropped `10/12 -> 8/12` precisely because pushing boundary/contrast examples shifted `track_order` logits across `delivery_issue` and `payment_issue`.
- **C36 unseen holdout (`task_73155afcc601`, `efb6868`):** Evaluated **only** on rejected sibling `d7ac47d0`, and intentionally **not** run on `f695b1fe` or `v3` (`c2e4eb37`) to preserve its unseen promotion-gate integrity.
- **Real LLM generation:** `PipelineRunner` checks used offline `_OfflineValidSpyLLM` (slot/DB/draft eligibility only); real LLM response quality is unmeasured in this audit.
