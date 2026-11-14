# Worker B Pre-Fit Audit: `fit2-orig-ret-channel-v4-prep` (`lr5e6` & Read-Only CAL Guard)

**Date:** 2026-11-14  
**Reviewer:** Worker B (Zero-Fit Audit)  
**Branch:** `minh`  
**Reviewed Commits:** `98d5de8fddca100520c86b38fd344db80675ae0c` (`feat(fit2): add lr5e6 profile and read-only post-fit CAL guard for v4-prep`), `243ac5ed7b46428b737bc2a024a13b1281c8088e` (`docs(audit): record v4-prep lr5e6 profile and read-only CAL guard`)  
**Required Baseline Proposal:** `6943e91ad670d9699b4a3a4e6b6916ced11e883b`  
**Verdict:** `PASS` *(technical one-fit-ready preflight pass ONLY — does NOT authorize starting the fit without explicit Coordinator release, and does NOT constitute EVAL/production acceptance)*  
**Fits Executed:** `0` (`--validate-only` only; optimizer and calibrator not invoked)

---

## 1. Executive Decision

Worker A's `v4` implementation (`98d5de8fddca100520c86b38fd344db80675ae0c`) and immutable `v4-prep` bundle (`artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep`) accurately implement the minimum `lr5e6` profile (`lr=5e-6`, forwarding `profile_cfg["lr"]` to `run_fit_and_lock_candidate`) and all four Worker B CAL guard corrections specified in `6943e91ad670d9699b4a3a4e6b6916ced11e883b`.

- Scope touched in `98d5de8f`: strictly 3 files (`scripts/run_orig_fit2_return_contrast_fit.py`, `scripts/run_orig_fit2_return_contrast_prep.py`, `tests/unit/test_orig_fit2_return_contrast_prep.py`), with zero edits to `orig_fit2_return_contrast_data.py`, `pipeline/`, runtime, UI, backend, or settings.
- `option_a` (`lr=2e-5`) profile contract and prior `v1/v2/v3` prep/candidate archives remain untouched.

---

## 2. Verification of the 4 Required CAL Guard Corrections

| Requirement (`6943e91`) | Verified Implementation & Locked `v4-prep` Values | Status |
|---|---|---|
| **1. Exact integer floor (`68/86` vs float `0.7907`)** | `boundary_pos_cal_correct_min = 68` (`86` rows); exact integer gate `cand_pos["correct_count"] >= 68`. | PASS |
| **2. Accuracy-coupled drift + `esc34` guards** | `boundary_pos_cal_delta_mean_max_prob <= (0.015 if correct <= 68 else min(0.025, 0.015 + 0.5 * (acc_cand - 68/86))) + 3e-6`; `boundary_pos_cal_esc34_delta_mean_max_prob <= 0.015 + 3e-6`; `boundary_pos_cal_esc34_max_sup12_mass <= 0.55 + 3e-6`. | PASS |
| **3. Raw unpseudonymized surface, `float64`, `3e-6` tol, anti-all-abstain + neg/extension floors** | Evaluates raw unmasked `r["text"]` with `float64` post-`T` softmax (`temperature >= min_temp`), `CAL_GUARD_FLOAT_TOLERANCE = 3e-6`. Exact integer gates: `boundary_pos_cal >= 68/86`, `boundary_pos_cal_sup12 >= 38/48`, `conf_ge_070 >= 26/48`, `conf_ge_080 >= 24/48`, `bitext_cal >= 687/690` *(distinct from `f695b1fe` actual `689/690` = `0.9985507246376811`)*, `pos_train_added_18 >= 15/18`, `boundary_neg_cal pred_sup12 <= 9/48`. Neg float ceilings: `max_sup12_mass <= baseline (0.7156928153564155) + 3e-6`, `max_single_sup12_prob <= baseline (0.5576920642670788) + 3e-6`. | PASS |
| **4. Read-only post-fit CAL-only guard & Worker C separation** | Runs strictly after fit, candidate archival, calibration/provenance checks, and reload verification; writes `cal_guard_report.json` and `status.json` (`CAL_GUARD_REJECT_DO_NOT_PROMOTE` on fail, preserves failed candidate without auto-refit). Worker C's full EVAL/OOD/adversarial/calibration/promotion protocol remains unchanged and mandatory. | PASS |

---

## 3. `lr5e6` Profile, `v4-prep` Parity & Immutability Verification

- **Profile & CLI:** `AUTHORIZED_FIT_PROFILES["lr5e6"]` sets `lr=5e-6`, `epochs=3`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`, `init_weights_sha256=f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`. `run_authorized_fit` passes `lr=float(profile_cfg["lr"])` to `run_fit_and_lock_candidate`. `--run-option-a-fit` explicitly requires `--profile option_a`.
- **`v4-prep` Hashes & Inventory (`artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep`):**
  - `prep_manifest.json` SHA-256: `55e53cf0e1067216a25462b5d03ffc63eef406854b063b9c601ab1de9eaa9a45`
  - `sidecar_sha_inventory.json` SHA-256: `f8262ffd73816bafc164a608521b7205ffefd1d46a4ecae6f7d267de5026090c` (`39/39` files verified, `0` missing, `0` extra, `0` mismatches)
  - `source_snapshot/`: `19/19` tracked files match workspace `HEAD` (`0` mismatches)
- **`v3-prep` vs `v4-prep` Dataset Parity:** `14/15` files under `datasets/` are bit-identical (`orig_fit2_return_contrast_extension.jsonl` SHA-256 `f87c6185362a358f03a1a7515778abaad5a6dd911462aca88287781acffbec3e`); only `dataset_lock_manifest.json` differs, solely in `locked_at` (`2026-11-14T11:21:31.085616+00:00` vs `2026-11-14T12:36:49.139487+00:00`).
- **Untouched Baseline, Serving, Prior Runs & Unused Destinations:**
  - Baseline Original Fit2 weights: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`
  - Rejected `fit2-orig-ret-channel-fit-v1` weights: `dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d`
  - `v3-prep` `prep_manifest.json`: `24094bc72fade9493eceb37c93a6acecd0d00e34545f95bd70d3811be9bd60b6`
  - Serving weights (`--validate-only`): `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`
  - Planned `fit2-orig-ret-channel-lr5e6-v1` archive, records, eval, and `%LOCALAPPDATA%\SupportIQ\fit_runs\...` directories do not exist yet.

---

## 4. Verification Runs (Zero Fits)

1. **Unit suite:** `.venv/Scripts/python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py -v` -> **`8 passed, 1 deselected in 68.23s`** (`real_model` deselected by default). Confirms provenance guards, extension balance, zero-fit preflight, `lr5e6` profile/CLI rejections, CAL integer & float+`3e-6` gates, mocked `lr=5e-6` forwarding, and fail-closed `CAL_GUARD_REJECT_DO_NOT_PROMOTE` archival.
2. **Real-model CAL guard check:** `.venv/Scripts/python.exe -m pytest -m real_model tests/unit/test_orig_fit2_return_contrast_prep.py -v` -> **`1 passed, 8 deselected in 10.56s`**. Confirms live baseline `f695b1fe` scores `68/86` pos, `38/48` `sup12`, `>=26` (`28`) `@>=0.70`, `>=24` (`28`) `@>=0.80`, `9/48` neg `pred_sup12`, and fails only `pos_train_added_18_correct_count` (`8 < 15`), while rejected `fit-v1` (`dc3e88e7`) triggers all 6 confidence-drift and negative-intrusion failures (`CAL_GUARD_REJECT_DO_NOT_PROMOTE`).
3. **Contract dry-run (pre-commit & post-commit descendant `HEAD` closure):**  
   `.venv/Scripts/python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep --run-id fit2-orig-ret-channel-lr5e6-v1 --profile lr5e6 --epochs 3 --lr 5e-6 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --validate-only`  
   Verified `validated_only: true`, `fits_executed: 0`, `authorized_fit_profile: "lr5e6"`, `lr: 5e-06`, `prep_git_commit: "98d5de8fddca100520c86b38fd344db80675ae0c"`, and clean descendant `head_git_commit` both pre-commit (`243ac5ed...`) and post-commit of this audit file.

---

## 5. Required Disclosures & Residual Constraints

1. **Historical 3 noisy overlaps unchanged:** Frozen `exclude_noisy_test_overlap=false` and bit-identical `14/15` dataset artifacts preserve the historical 3 normalized `bitext_train_noisy` vs `bitext_test_6690` overlaps.
2. **Comparative-only causal confound:** Warm-starting `lr5e6` (`lr=5e-6`, `epochs=3`) from already-converged Original Fit2 (`f695b1fe`) adds 3 full passes over 13,080 effective rows without a matched no-added-data continuation control; results compare a downstream candidate rather than isolating a pure causal extension delta.
3. **Boundary of `PASS`:** This `PASS` certifies only that `v4-prep` and the read-only CAL guard satisfy Worker B's technical prerequisites for **one** bounded fit. Coordinator authorization is required before executing `--run-authorized-fit`, and Worker C's full EVAL / OOD / adversarial / calibration / promotion protocol remains untouched and mandatory prior to any promotion.
