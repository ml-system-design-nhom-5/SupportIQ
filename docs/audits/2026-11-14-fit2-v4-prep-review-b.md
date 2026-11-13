# Independent Pre-Fit Review (Worker B): Fit2 Boundary-Contrast v4 Prep & Calibration Plumbing

- **Verdict:** `CHANGES_REQUIRED` (not yet ready for the 1 bounded GPU fit until Finding 1 is fixed; readiness is strictly for the future fit, never acceptance or promotion)
- **Reviewed Commit:** `f5913adebe08c4d4350a813cf6254fd24b8825c0` vs base `e4adafd13c09c85b650cbe8b90430e9af42edd47` (`13` files, `+11054 / -2`)
- **Predeclared Scope & Zero-Fit Check:** `0` GPU fits, `0` CPU calibrator fits, `0` provider calls, `0` implementation/dataset edits during review.

## 1. Archive, Baseline, Lineage & Dry-Run Integrity

All immutable baselines, canonical Bitext prep inputs, and dry-run sidecar inventories verified with `0` mismatches:

- **Serving (`distilbert-supportiq`):** `model.safetensors` SHA-256 `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`.
- **Starting Checkpoint (`reconstructed-fit2-supcon-20261113`):** `model.safetensors` SHA-256 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `T=1.0`, `selective_rejector.enabled=false`, `calibration_sample_count=776`, 46-label bijection valid.
- **Canonical Bitext Prep (`data/datasets/restored/bitext-12dd624/prep`):** `cleaned.csv` `8bc10cfa056371bdecb3394bfd4c75eee7e10022ace5071833ecd140b2d75846`, `split_assignments.csv` `1d366e898f6ba68be46c5ca0f9059e9862fad1d7bafe350d9cdd310dd3e0a04c`.
- **Dry-Run Archive (`artifacts/models/candidates/run-records-fit2-boundary-contrast-v4-dryrun`):**
  - `sidecar_sha_inventory.json`: `19/19` files verified, `0` mismatches.
  - Archived script copies (`boundary_contrast_data.py` `dc134473daff...`, `train_boundary_candidate.py` `3974685672ab...`, `run_boundary_contrast_fit.py` `4ee43189c352...`) match `f5913ade` byte-for-byte.
  - `artifacts/evaluation/boundary_contrast_20261114/dryrun/datasets/` matches `run-records-fit2-boundary-contrast-v4-dryrun/datasets/` byte-for-byte (`0` diffs).
  - `dryrun_manifest.json`: `git_commit=f5913adebe08c4d4350a813cf6254fd24b8825c0`, `dry_run=true`, `fits_executed=0`, `planned_rejector_c_grid=[0.15, 0.35, 0.75, 1.5]`.
  - Zero-fit dry-run inspection (`scripts/run_boundary_contrast_fit.py:86-201, 239-295`): `verify_fit2_starting_checkpoint` loads model `local_files_only=True` solely for label/bijection check; no optimizer, DataLoader, training loop, or calibrator fit runs under `--dry-run`.
  - Uniqueness fail-closed guards (`scripts/run_boundary_contrast_fit.py:229-237`): `--run-contrast-fit` fails closed if `archive_dir`, `records_dir`, or `local_root` already exist; `--archive-dryrun` fails closed if `dryrun_records_dir` exists; inputs are copied and hash-verified before training (`298-307`).

## 2. Data, Semantic Boundaries, Exposure & Isolation Checks

- **Active-KB Semantic Boundaries (`pipeline/training/boundary_contrast_data.py:32-298`):**
  - Removed `5` contradictory base `track_order` rows (`cls_trk_live_gps_0`, `cls_trk_live_gps_2`, `cls_trk_partner_portal_2`, `cls_trk_sms_alerts_1`, `cls_trk_sms_alerts_2`).
  - Remaining `track_order` rows cover ordinary order status / `My Orders` / carrier link / hub scan / customs clearance; `track_delivery` (`ESCALATED_34`) owns live vehicle/driver GPS, stops away, and doorstep telemetry.
  - `return_policy` / `return_product` (`SUPPORTED_12`) are cleanly separated from `return_product_in_store` (`ESCALATED_34`) physical retail branch / storefront / walk-in / cashier returns. (`cls_rpr_pickup_dropoff_1` refers to a convenience-store parcel locker for mail returns; `bnd_return_policy_trn_0` and `contrast_auth_pos_eval_100` use "store" to mean merchant policy.)
- **Class & Exposure Balance:**
  - Raw counts: `domain_pos_train=300`, `domain_neg_train=127` (`out_of_scope=99`, `multi_intent=16`, `other_domain=12`), `bitext_train_clean=7360`, `bitext_train_noisy=3680`, `domain_pos_cal=135` (`sup11=53`, `human_agent=4`, `esc34=78`), `domain_neg_cal=60`, `bitext_cal=690`, `domain_pos_eval=175`, `domain_neg_eval=51`, `bitext_test_eval=6690`.
  - Effective encoder train rows: `total_positive_ce_effective=12380` (`1340` domain + `11040` bitext), `total_neg_effective=1524`, `total_effective_train_rows=13904` (`435` batches/epoch at `bs=32`). All `46` classes covered (`240..400` effective positives/class). Authored train contrasts balanced (`order_history=10`, `track_order=10`, `track_delivery=10`, `return_product_in_store=12`, `return_policy=10`, `return_product=10`).
  - Positive vs negative routing: `neg_intents_in_standard_46_count=0`, `pos_non_46_count=0`; only genuine non-46 rows (`out_of_scope`, `multi_intent`, `other_domain`) enter Uniform-KL + `sup12` ceiling + energy (`pipeline/training/train_boundary_candidate.py:714-744`).
- **Draft Eligibility & Split Isolation:**
  - `is_draft_eligible_intent` (`pipeline/training/train_boundary_candidate.py:132-137`) strictly uses `SUPPORTED_11_DRAFT_SET` (`SUPPORTED_12_INTENTS` excluding `human_agent`), independent of 46-class `selective_label=1`.
  - Rejector train set (`train_boundary_candidate.py:814-825`): `8766` TRAIN-only rows (`y=1`: `2356` `SUPPORTED_11`, `y=0`: `6410` `ESCALATED_34`/`human_agent`/negatives). `StandardScaler` + `LogisticRegression` fitted strictly on `TRAIN` (`220-221, 264-265`); `T >= 1.0` fitted strictly on `CAL` positives (`770-795`); `(C, tau)` tuned strictly on `CAL` (`276-341`). Zero eval-dependent selection.
  - Domain `TRAIN`/`CAL`/`EVAL` + frozen benchmark isolation (`check_split_isolation_and_gold_contamination`): `passed=True`, `0` group overlaps, `0` text overlaps, `0` gold matches.
- **Runtime 776d Parity & Dependencies:**
  - `cls_l2_plus_logit_geometry_v1` (L2-normalized 768d last-layer `[CLS]` + 8d logit geometry with nats Shannon entropy, `StandardScaler`, sigmoid, `reject_when="below"`) matches across `pipeline/training/train_selective_candidate.py:191-249`, `apps/ml_inference/app.py:520-586, 658-702`, and `pipeline/evaluation/classifier_acceptance_gate.py:528-585`.
  - Disabled/default compatibility preserved (`apps/ml_inference/app.py:325-326` sets `_selective_rejector=None` when `enabled=False`).
  - Imports across all `13` changed files use only existing project dependencies (`numpy`, `pandas`, `pytest`, `sklearn`, `torch`, `transformers`).

## 3. Findings (Ordered by Severity)

1. **[Medium] Calibration selector can silently accept a degenerate all-abstain (or unsafe) rejector (`pipeline/training/train_boundary_candidate.py:259-343`)**
   - `fit_selective_rejector_from_arrays` ranks `(C, tau)` by `(zero_unsafe, tau_obj)` where `zero_unsafe = int(neg_false_draft == 0 and esc34_unsafe_draft == 0)` and `tau_obj` subtracts `0.25 * (neg_false_accept_any / neg_cal_n) + 0.02 * abs(tau_f - 0.50)`.
   - If high `tau` (e.g., `0.90`) rejects 100% of positives and negatives (`pos_corr_draft=0`, `pos_raw_draft=0`, `neg_false_draft=0`, `esc34_unsafe_draft=0`, `neg_false_accept_any=0`), it yields `(1, -0.008)`. That ranks strictly above every `(0, ...)` point and even beats `(1, tau_obj)` with `pos_corr_draft=1` whenever `neg_false_accept_any` penalty exceeds `pos_corr_draft / sup11_cal_n`.
   - The function only asserts `best_params is not None` (`342`) and returns `best_stats` silently—even with `cal_dom_correct_draft == 0` or `zero_cal_unsafe == False`—and no unit test covers this degenerate regime. Downstream `classifier_acceptance_gate.py` would reject the candidate after training, but the pre-gate trainer/runner would emit and archive an all-abstain candidate unnoticed.

2. **[Low] CAL objective omits `bitext_cal` `SUPPORTED_11` coverage and `human_agent` misclassification check (`pipeline/training/train_boundary_candidate.py:253-297`)**
   - `pos_corr_draft / sup11_cal_n` scores only `cal_dom_intents` (`53` `SUPPORTED_11` rows), ignoring the `165` `SUPPORTED_11` rows in `bitext_cal`.
   - `esc34_unsafe_draft` checks `gold_y in ESCALATED_34_INTENTS` (`290, 293`), so a `human_agent` calibration row (`4` in `pos_cal`, `15` in `bitext_cal`) misclassified into `SUPPORTED_11` with `raw_act == "retrieve_draft"` is not counted in `zero_unsafe`.

3. **[Low] Pre-existing noise-aug text overlap with `bitext_test_6690` (`pipeline/training/train_boundary_candidate.py:494-498`)**
   - `bitext_train_noisy` (`lowercase_strip_punct`) checks `cal_norms_all` and `_has_gold_conflict`, but not `bitext_test_6690` normalized texts. Three noisy train rows (`bitext_trn_aug_sample_001393_41`, `bitext_trn_aug_sample_020326_51`, `bitext_trn_aug_sample_031082_1`) match normalized text of 3 `bitext_test_6690` rows (`sample_001360`, `sample_020916`, `sample_031234`), though `parent_sample_id` remains 100% disjoint (`0` overlap).

4. **[Low] Runner does not enforce clean working tree or post-fit `audit_candidate_provenance` (`scripts/run_boundary_contrast_fit.py:241, 309, 382-386`)**
   - `run_boundary_contrast_fit.py` records `git rev-parse HEAD` without checking `git status --porcelain` is clean before `--run-contrast-fit`, and post-fit checks `validate_calibration_manifest` + `verify_reload_from_archive` without explicitly calling `audit_candidate_provenance`.

5. **[Low] Disabled-rejector metadata asymmetry in `GateSequenceClassifier` (`pipeline/evaluation/classifier_acceptance_gate.py:670, 722`)**
   - When `rejector={"enabled": False, ...}`, `GateSequenceClassifier` emits `selective_accepted=True` / `rejector_decision="accept"`, whereas `apps/ml_inference/app.py:325-326` sets `_selective_rejector=None` (`selective_accepted=None`). Routing (`decide_route`, `Engine._analyse`, `experimental_rejector_active=False`) is unaffected.

## 4. Tests & Verification Commands Run (Zero Fits)

- `.venv/Scripts/python.exe -m pytest tests/unit/test_boundary_contrast_fit.py tests/unit/test_gate_contract_b.py tests/unit/test_model_runtime_parity_b.py tests/unit/test_task_c_evaluation_gates.py tests/unit/test_intent_client_rejector_routing.py tests/unit/test_model_provenance.py tests/unit/test_routing.py tests/unit/test_intent_policy_and_escalation.py tests/unit/test_sealed_holdout_20261113.py -q`
  - **Result:** `127 passed, 1 deselected in 83.21s` (`real_model` marker deselected per `pytest.ini`).
- `.venv/Scripts/python.exe -m pytest tests/unit/test_training.py tests/unit/test_preparation.py tests/unit/test_runtime_preflight.py tests/unit/test_pipeline_runner_safety_b.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_candidate_comparison_accounting.py -q`
  - **Result:** `164 passed in 33.78s`.
- Direct read-only Python checks: `sidecar_sha_inventory.json` (`19/19` ok), baseline/prep SHA-256s, AST import audit across all `12` code/test files, class exposure & rejector target balance, and `check_split_isolation_and_gold_contamination` on domain splits and `bitext_test_6690`.

## 5. Limitations & Target vs Measured Distinction

- All performance targets in `docs/superpowers/plans/2026-11-14-fit2-v4-taxonomy-calibration-plan.md` (`>=10/12` `final_acceptance_24`, `>=25/34` `system_acceptance_156`, `>=0.8573` macro-F1 / `>=267` `ml_noise_420`, `0` unsafe leaks) are **proposed evaluation targets only**—feasibility and measured checkpoint performance are unproved (`0` fits run).
- Tests ran with `pytest.ini` default `-m "not real_model and not cuda and not live"` (`1` `real_model` test deselected).

## 6. Minimal Corrective Tasks for Worker A

1. **Required (`pipeline/training/train_boundary_candidate.py:259-343`, `tests/unit/test_boundary_contrast_fit.py`):**
   - In `fit_selective_rejector_from_arrays`, rank `(non_degenerate, zero_unsafe, tau_obj)` with `non_degenerate = int(pos_corr_draft > 0)` (or enforce a minimum CAL `SUPPORTED_11` coverage floor) and **fail closed** (`ValueError`/`RuntimeError`) if `best_stats["cal_dom_correct_draft"] == 0` (or `not best_stats["zero_cal_unsafe"]`) so a degenerate all-abstain rejector cannot be silently emitted.
   - Add 1 focused unit test in `tests/unit/test_boundary_contrast_fit.py` verifying that an all-abstain-only CAL score grid fails closed instead of silently returning `threshold=0.90, cal_dom_correct_draft=0`.
2. **Optional small hygiene (same freeze before fit):**
   - Exclude `test_norms` in `prepare_and_lock_splits:496` when generating `bitext_train_noisy` (`0` overlap with `bitext_test_6690`), and call `audit_candidate_provenance` post-fit in `scripts/run_boundary_contrast_fit.py`.
