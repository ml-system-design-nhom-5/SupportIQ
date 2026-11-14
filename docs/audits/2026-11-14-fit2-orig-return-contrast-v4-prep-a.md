# Audit Report: Original Fit2 Return-Channel `lr5e6` + Read-Only CAL Guard (`v4-prep`, Worker A)

- **Role:** Worker A (`minh`)
- **Authorization Status:** Zero fits executed (`fits_executed: 0`, `optimizer_invoked: False`, `calibrator_invoked: False`); `v4-prep` archived strictly read-only/zero-fit pending Worker B re-review and Coordinator release before any future training.
- **Frozen Source+Test Commit (`git_commit` recorded in `v4-prep`):** `98d5de8fddca100520c86b38fd344db80675ae0c`
- **Prep Bundle (`v4-prep`):** `artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep`
  - `schema_version`: `orig_fit2_return_contrast_prep.v4`
  - `prep_manifest.json` SHA-256: `55e53cf0e1067216a25462b5d03ffc63eef406854b063b9c601ab1de9eaa9a45`
  - `sidecar_sha_inventory.json` SHA-256: `f8262ffd73816bafc164a608521b7205ffefd1d46a4ecae6f7d267de5026090c`
  - Prior archives preserved untouched: `v1-prep`, `v2-prep`, `v3-prep`, `fit2-orig-ret-channel-fit-v1`, `run-records-fit2-orig-ret-channel-fit-v1`, Original Fit2 (`f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`), Fit1 (`95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6`), Serving (`dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`).
  - Target `fit2-orig-ret-channel-lr5e6-v1` archive/records/local output paths remain absent.

---

## 1. Profile & Runner Guard Changes

- Added versioned profile `lr5e6` (`lr=5e-6`, `epochs=3`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`, init Original Fit2 `f695b1fe...`) in [`AUTHORIZED_FIT_PROFILES`](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_prep.py), while preserving `option_a` (`lr=2e-5`) intact.
- Fixed the hardcoded `lr=2e-5` inside [`run_authorized_fit`](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py) (`run_fit_and_lock_candidate(...)` call) so the validated profile `lr` (`5e-6` or `2e-5`) is passed explicitly.
- CLI in [`scripts/run_orig_fit2_return_contrast_fit.py`](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py) now requires `--profile` (`option_a` or `lr5e6`) and `--lr`, enforces exact profile/flag/manifest parity (`--run-option-a-fit` strictly requires `--profile option_a`; `--run-authorized-fit` supports arbitrary authorized profiles such as `lr5e6`), and fails closed on mismatch, dirty 19-file source closure, non-ancestor `git_commit`, or output collision.

---

## 2. Dataset Parity (`v4-prep` vs `v3-prep`)

- Zero edits made to `pipeline/training/orig_fit2_return_contrast_data.py`.
- Verified all `15` files under `v4-prep/datasets/`:
  - `14` files bit-identical (`sha256` exact match) to `v3-prep/datasets/`.
  - `1` file differing (`dataset_lock_manifest.json`, timestamp diff only).

---

## 3. Read-Only Post-Fit CAL Guard (`cal_guard_report.json`)

Implemented all four Worker B corrections as a strictly read-only post-fit guard in [`scripts/run_orig_fit2_return_contrast_prep.py`](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_prep.py) and [`scripts/run_orig_fit2_return_contrast_fit.py`](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py) (no calibration optimization, no auto-retrain, no heldout evaluation/tuning):

1. **Surface & Probability Scale:** Unpseudonymized raw `text`, `max_length=64`, post-`T` float64 softmax using `calibration.temperature` from `calibration_manifest.json`, across locked denominators:
   - `boundary_pos_cal` (`86`), `boundary_pos_cal_sup12` (`48`), `boundary_pos_cal_esc34` (`38`), `bitext_cal` (`690`), `boundary_neg_cal` (`48`), `pos_train_added_18` (`18`, `orig_ret_ch_*`).
2. **Exact Integer Count Gates (0 slack):**
   - `boundary_pos_cal` `correct_count >= 68`
   - `boundary_pos_cal_sup12` `correct_count >= 38`, `conf_ge_070_count >= 26`, `conf_ge_080_count >= 24`
   - `bitext_cal` `correct_count >= 687`
   - `pos_train_added_18` `correct_count >= 15`
   - `boundary_neg_cal` `pred_sup12_count <= 9`
3. **Bounded Drift & Ceiling Rules (`float_tolerance = 3e-6` for CPU-vs-CUDA float rounding):**
   - `boundary_pos_cal` `delta_mean_max_prob <= (0.015 if correct <= 68 else min(0.025, 0.015 + 0.5 * (acc_cand - 68/86))) + 3e-6`
   - `boundary_pos_cal_esc34` `delta_mean_max_prob <= 0.015 + 3e-6` and `max_sup12_mass <= 0.55 + 3e-6`
   - `boundary_neg_cal` `max_sup12_mass <= base_neg_max_sup12_mass + 3e-6` and `max_single_sup12_prob <= base_neg_max_single_sup12_prob + 3e-6`
4. **Locked `baseline_cal_reference` in `v4-prep/prep_manifest.json` (`f695b1fe`, `T=1.0`):**
   - `boundary_pos_cal`: `68/86`, `mean_max_prob = 0.6863441951590312`
   - `boundary_pos_cal_sup12`: `38/48`, `conf_ge_070_count = 28`, `conf_ge_080_count = 28`
   - `boundary_pos_cal_esc34`: `30/38`, `mean_max_prob = 0.6709624479394273`, `max_sup12_mass = 0.4673615502178657`
   - `bitext_cal`: `689/690`
   - `pos_train_added_18`: `8/18`
   - `boundary_neg_cal`: `pred_sup12_count = 9/48`, `max_sup12_mass = 0.7156928153564155`, `max_single_sup12_prob = 0.5576920642670788`
5. **Post-fit Archival Outcome:** Writes `records_dir/cal_guard_report.json` (SHA-sealed into `sidecar_sha_inventory.json`) and sets `status.json["cal_guard_passed"]` / `cal_guard_status` (`CAL_GUARD_PASS_READY_FOR_C_EVAL` or `CAL_GUARD_REJECT_DO_NOT_PROMOTE`). On CAL reject, the archive is still preserved cleanly with zero auto-retrain.

---

## 4. Planned Future Execution CLI (NOT EXECUTED; Pending B Re-Review & Coordinator Release)

```powershell
.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit `
  --prep-dir artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep `
  --run-id fit2-orig-ret-channel-lr5e6-v1 `
  --profile lr5e6 `
  --epochs 3 `
  --lr 5e-6 `
  --batch-size 32 `
  --seed 42 `
  --fit-mode fit2_supcon_energy `
  --run-authorized-fit
```

---

## 5. Verification Executed

- `--archive-prep` on `98d5de8fddca100520c86b38fd344db80675ae0c` (`fits_executed: 0`, `profile: lr5e6`).
- `--validate-only` against `v4-prep` (`validated_only: true`, `fits_executed: 0`, `authorized_fit_profile: lr5e6`).
- Live read-only `@pytest.mark.real_model` CAL check (`1 passed, 8 deselected in 10.88s`): Original Fit2 (`f695b1fe`) passes all 11 non-extension-learning CAL checks (only `pos_train_added_18_correct_count` is `8 < 15`); rejected `fit2-orig-ret-channel-fit-v1` (`dc3e88e7`) fails (`CAL_GUARD_REJECT_DO_NOT_PROMOTE`) on `boundary_pos_cal_delta_mean_max_prob`, `boundary_pos_cal_esc34_delta_mean_max_prob`, `boundary_pos_cal_esc34_max_sup12_mass`, `boundary_neg_cal_pred_sup12_count`, `boundary_neg_cal_max_sup12_mass`, and `boundary_neg_cal_max_single_sup12_prob`.
- Focused 6-file unit suite (`test_orig_fit2_return_contrast_prep.py`, `test_boundary_contrast_fit.py`, `test_faithful_fit2_entrypoint.py`, `test_gate_contract_b.py`, `test_task_c_evaluation_gates.py`, `test_model_provenance.py`): `56 passed, 2 deselected in 208.22s`.
