# Fit2 Boundary-Contrast v4 Prep & Calibration Plan (Ponytail ULTRA)

**Date:** 2026-11-14  
**Scope:** Implementation, data/semantic cleanup, unit tests, and zero-GPU dry-run only (**0 fits executed in this task**).

## 1. Immutable Lineages & Canonical Inputs
- **Starting Checkpoint:** `artifacts/models/candidates/reconstructed-fit2-supcon-20261113` (`model.safetensors` SHA-256 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `T=1.0`, `selective_rejector.enabled=false`).
- **Preserved Baselines:** Serving `distilbert-supportiq` (`dc7af8cf...`), Closure (`95a940b6...`), and rejected `v1`/`v2`/`v3` records remain untouched.
- **Canonical Bitext Prep:** `data/datasets/restored/bitext-12dd624/prep` (`cleaned.csv` SHA-256 `8bc10cfa056371bdecb3394bfd4c75eee7e10022ace5071833ecd140b2d75846`, `split_assignments.csv` SHA-256 `1d366e898f6ba68be46c5ca0f9059e9862fad1d7bafe350d9cdd310dd3e0a04c`). Noisy train augmentations (`bitext_train_noisy`) exclude normalized overlaps against held-out `bitext_test_6690`, `CAL`, `eval`, and frozen gold suites, verified end-to-end by `check_split_isolation_and_gold_contamination` across `full_eval_all + bitext_test`.

## 2. Semantic, Exposure, and OOD Fixes (`boundary_contrast_data.py`)
1. **Active-KB Semantic Disambiguation:**
   - `track_order` (`SUPPORTED_12`, `POL-ORD-001`): restricted strictly to ordinary order status / `My Orders` fulfillment stage / tracking code lookup. Contradictory base rows (`cls_trk_live_gps`, driver/rider doorstep rows) and live-truck/courier-GPS authored phrases are removed/re-aligned.
   - `track_delivery` (`ESCALATED_34`): owns live delivery truck/van GPS, driver location, stops away, and doorstep delivery telemetry.
   - `return_policy` (`SUPPORTED_12`, `POL-RET-001`) vs `return_product` (`SUPPORTED_12`, `POL-RET-002`) vs `return_product_in_store` (`ESCALATED_34`): policy eligibility rules strictly separated from physical retail branch / brick-and-mortar / storefront / walk-in return channel requests.
2. **Balanced Supported Contrast Exposures:**
   - Train authored contrast counts balanced to `10` each (`order_history=10`, `track_order=10`, `track_delivery=10`, `return_policy=10`, `return_product=10`, `return_product_in_store=12`) instead of `28` `track_order` rows (`x4`).
   - Retains full 46-class Bitext replay + positive CE/SupCon for all `STANDARD_INTENTS_46` (including `ESCALATED_34`).
   - Only genuine non-46 rows (`out_of_scope`, `multi_intent`, `other_domain`) enter negative Uniform-KL + `sup12` ceiling + energy splits.
3. **Small Group-Isolated Non-Retail OOD (`other_domain`):**
   - Independently authored telecom, municipal utility, SaaS billing, and non-retail homonym families (`12` train / `6` cal / `6` eval across disjoint `group_id`s), audited against all frozen benchmarks.

## 3. Existing `selective_calibration.v1` Protocol (`train_boundary_candidate.py`)
- **No New Architecture:** Reuses `selective_calibration.v1` (`cls_l2_plus_logit_geometry_v1`, 776d) enforced end-to-end by `Engine` and `classifier_acceptance_gate.py`.
- **Draft Eligibility Separation:** `selective_label=1` in split JSONLs denotes 46-class membership, NOT draft eligibility. The rejector uses `is_draft_eligible_intent`: `y=1` (`in_scope`) iff single-intent `SUPPORTED_11` (`SUPPORTED_12` minus `human_agent`), and `y=0` for `ESCALATED_34`, `human_agent`, and negative rows, with `reject_when="below"`.
- **Strict Split Isolation:**
  - Scalar `T >= 1.0` fitted strictly on isolated positive calibration (`pos_cal + bitext_cal`).
  - `StandardScaler` + `LogisticRegression` fitted strictly on `TRAIN` (`pos_train + bitext_clean + neg_train`).
  - `(C, threshold)` selected strictly on isolated `CAL` (`pos_cal + bitext_cal + neg_cal`): candidate points must first satisfy hard feasibility (`zero_cal_unsafe=True` across `neg_cal`, `ESCALATED_34`, AND `human_agent` on both domain CAL and Bitext CAL, plus nonzero `SUPPORTED_11` correct draft coverage on all present `cal_dom` and `bitext_cal` cohorts); fails closed (`ValueError`) if 0 feasible points exist. Among feasible points, ranks by `0.5 * (cal_dom_corr / sup11_dom) + 0.5 * (bitext_cal_corr / sup11_bitext) - 3.0 * neg_false_draft / neg_cal_n - 3.0 * non_draft_unsafe / non_draft_cal_total - 0.25 * neg_false_accept_any / neg_cal_n - 0.02 * abs(tau - 0.50)`.

## 4. Proposed Future Budget (Pending Coordinator Authorization — Not Yet Authorized)
- **Proposed Compute Budget (Pending B Re-Review & Coordinator Approval):** **1 GPU encoder fit** (`fit2_supcon_energy`, `epochs=2`, `batch_size=32`, `lr=1e-5`, `seed=42`, `--enable-selective-rejector`, `--run-id fit2-boundary-contrast-v4p1`) + **1 fixed small CPU rejector `C` grid** `(0.15, 0.35, 0.75, 1.5)`. Zero hidden extra encoder fits. Runner verifies clean relevant tracked source provenance vs `HEAD` before starting and audits archived `candidate_provenance_manifest.json` + `calibration_manifest.json` after fit.
- **Predeclared Command (If Authorized):**  
  `python -m scripts.run_boundary_contrast_fit --run-contrast-fit --run-id fit2-boundary-contrast-v4p1 --enable-selective-rejector`
- **Comparison & Acceptance Targets (Feasibility Unproved Until Run):** Compare against frozen Serving (`dc7af8cf`) and original Fit2 (`f695b1fe`): retain `>= 10/12` `final_acceptance_24`, `>= 25/34` `system_acceptance_156`, `ml_noise_420` macro-F1 `>= 0.8573` & `>= 267` correct drafts, and `0` unsafe leaks across all known suites + group-isolated holdout, followed by fresh independent checkpoint review.
