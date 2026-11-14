# Fit2 Final Attempt (2/2) Execution & CAL Guard Audit (`fit2-orig-pre-classifier-head-v1`)

- **Date (Local / UTC):** `2026-11-15T00:31:03+07:00` (`2026-11-14T17:31:03Z`)
- **Branch / Workspace:** `minh` (`F:\Năm 3\SD\project\SupportIQ`)
- **Pre-Fit Commits:** source/tests `f90deedb23b760a129f3aeaaedc92ea0c5c6d286`, prep audit `d67ac674b4afe5f4107f600c5dee8a7477682010`, Worker B PASS `c207026d3c4b1f089793e25ea7b7dae0b3e50858`
- **Role / Dispatch:** Worker A (`task_13c4a39c0016`, `dispatch_id=ctx_2af3b621851b`), actual start status `msg_1d674341edb3`
- **Verdict:** **`CAL_GUARD_REJECT_DO_NOT_PROMOTE` (`10 / 12` PASS, `2 / 12` FAIL)**
- **Terminal State:** **NO HOLDOUTS EXECUTED — NO PROMOTION — BUDGET `2 / 2` EXHAUSTED (`training_stopped = true`, `stop_reason = "budget_exhausted"`)**

---

## 1. Execution, Budget Accounting, & Archive Inventory

- **Exact CLI executed:**
  `.\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-pre-classifier-head-v1-prep" --run-id fit2-orig-pre-classifier-head-v1 --profile option_a_pre_classifier_head_v1 --epochs 3 --lr 5e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --weight-decay 0.01 --trainable-scope pre_classifier_and_classifier --feature-dropout-eval-mode --run-authorized-fit`
- **Preflight `--validate-only`:** Passed before budget consumption (`fits_executed: 0`).
- **Training cap ([training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json)):** Atomically incremented `1 -> 2` before optimizer execution (`final_attempt = true`, `no_more_training_authorized = true`), then marked `training_stopped = true`, `stop_reason = "budget_exhausted"`, `status = "completed_cal_guard_rejected"`. Total fits executed in this run: `1` (`train_seconds = 47.56s`, `temperature = 1.0`, `selective_rejector_enabled = false`).
- **Archived Candidate Dir:** [fit2-orig-pre-classifier-head-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-pre-classifier-head-v1)
  - `archive_sha_inventory.json` SHA-256: `87587acc935067d43f0002d1918eed91463360fb8676a1785f3954d474d8b27e` (`6 / 6` files verified, `0` mismatches, `6 / 6` bit-identical to local output dir)
  - `model.safetensors`: `374afde7977434ac0aae19efd2ac55bcfb6c04127531a355098dfe62a7490369`
  - `calibration_manifest.json`: `9d7fc0b79a52d5760c803c67e9ffab1355021bf570f3ae809d4aeb814cbac6c5` (`T = 1.0`, `min_temperature = 1.0`, `calibration_sample_count = 776`, `selective_rejector.enabled = false`)
  - `candidate_provenance_manifest.json`: `69cfb56ebe15422725baff634bf5a3167322337c0d9044747fe39a33073de1bc` (`provenance_passed = true`, `reload_verified = true`, `num_labels = 46`)
  - `tokenizer.json`: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87` | `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
- **Archived Records Dir:** [run-records-fit2-orig-pre-classifier-head-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-pre-classifier-head-v1)
  - `sidecar_sha_inventory.json` SHA-256: `db4e56df14992bbefb6a0bdb59656739dd242f22fe2b5927b090618869d5cf9b` (`41 / 41` files verified, `0` mismatches)
  - `cal_guard_report.json` SHA-256: `9b3ec85c1f3f9aa5dd48607da814c1a8b82ef43cc340761cea66343fecfd4b9b`
- **Anchors Untouched:** Init `reconstructed-fit2-supcon-20261113/model.safetensors` = `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`; Active serving = `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`.

---

## 2. Freeze Integrity & Trainable Layer Update Verification

- **Frozen encoder & buffers (`66,362,880` params across `100` tensors + `1` buffer):**
  - PRE-fit SHA-256 == POST-fit SHA-256 == `d16052a208919dfd2fa09f8bb4330ddbc37fab58fa7c8573dd31a686083a0151`.
  - Direct on-disk tensor equality check across all `100` frozen tensors in `model.safetensors` vs `reconstructed-fit2-supcon-20261113`: **`0` bit differences**.
- **Trainable subhead (`625,966` params across `4` tensors):**
  - `pre_classifier.weight`: `max_abs_delta = 0.01978631690144539`, `last_grad_abs_max = 0.0005988467601127923`
  - `pre_classifier.bias`: `max_abs_delta = 0.0063390061259269714`, `last_grad_abs_max = 0.0002302828652318567`
  - `classifier.weight`: `max_abs_delta = 0.028003374114632607`, `last_grad_abs_max = 0.004181467462331057`
  - `classifier.bias`: `max_abs_delta = 0.004640263505280018`, `last_grad_abs_max = 0.0024368646554648876`
- **Epoch loss progression (`supcon_loss_sum = 0.0` in all 3 epochs):** Epoch 1 `0.27057` (`pos=0.26236, neg=0.00821`) -> Epoch 2 `0.26078` (`pos=0.25243, neg=0.00835`) -> Epoch 3 `0.25871` (`pos=0.25032, neg=0.00839`).

---

## 3. All 12 Sealed CAL Guard Checks (`T = 1.0`, raw logits == post-`T`, tolerance `3e-6`)

Source: [cal_guard_report.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-pre-classifier-head-v1/cal_guard_report.json) (baseline `f695b1fe` also `T = 1.0`).

| # | Check Name | Kind | Candidate Actual | Rule / Limit (tol `3e-6`) | Baseline (`f695`) | Result |
|---|---|---|---|---|---|---|
| 1 | `boundary_pos_cal_correct_count` | int | **`64`** (`/ 86`) | `>= 68` | `68` (`/ 86`) | **FAIL** (`-4`) |
| 2 | `boundary_pos_cal_sup12_correct_count` | int | **`34`** (`/ 48`) | `>= 38` | `38` (`/ 48`) | **FAIL** (`-4`) |
| 3 | `bitext_cal_correct_count` | int | `689` (`/ 690`) | `>= 687` | `689` (`/ 690`) | PASS |
| 4 | `pos_train_added_18_correct_count` | int | `18` (`/ 18`) | `>= 15` | `8` (`/ 18`) | PASS (`+10`) |
| 5 | `boundary_pos_cal_sup12_conf_ge_070_count` | int | `32` | `>= 26` | `28` | PASS (`+4`) |
| 6 | `boundary_pos_cal_sup12_conf_ge_080_count` | int | `27` | `>= 24` | `28` | PASS (`-1`) |
| 7 | `boundary_neg_cal_pred_sup12_count` | int | `6` (`/ 48`) | `<= 9` | `9` (`/ 48`) | PASS (`-3`) |
| 8 | `boundary_pos_cal_delta_mean_max_prob` | float | `-0.005164828818056355` | `<= 0.015` (actual `0.681179` vs `0.686344`) | `0.6863441951590312` | PASS |
| 9 | `boundary_pos_cal_esc34_delta_mean_max_prob` | float | `-0.019262708062074085` | `<= 0.015` (actual `0.651700` vs `0.670962`) | `0.6709624479394273` | PASS |
| 10 | `boundary_pos_cal_esc34_max_sup12_mass` | float | `0.44703639902948133` | `<= 0.55` | `0.4673615502178657` | PASS |
| 11 | `boundary_neg_cal_max_sup12_mass` | float | `0.6582846861015232` | `<= 0.7156928153564155` | `0.7156928153564155` | PASS |
| 12 | `boundary_neg_cal_max_single_sup12_prob` | float | `0.4735395969061724` | `<= 0.5576920642670788` | `0.5576920642670788` | PASS |

---

## 4. Methodological Limits & Permanent Stop

1. **Empirical failure mode (`10 / 12` CAL):** Fitting `pre_classifier + classifier` memorized `+18` (`8 -> 18 / 18`) and reduced false positives on `boundary_neg_cal` (`9 -> 6 / 48`), but regressed on held-out in-domain `boundary_pos_cal_sup12` (`38 -> 34 / 48`, dropping `boundary_pos_cal` `68 -> 64 / 86`), triggering automatic `CAL_GUARD_REJECT_DO_NOT_PROMOTE` and zero holdout execution.
2. **`n = 1` & multi-factor confound:** Single execution at `seed = 42` changed architecture (`classifier` -> `pre_classifier + classifier`), `lr` (`1e-4` -> `5e-5`), and `epochs` (`2` -> `3`) simultaneously.
3. **`3` historical noisy overlaps preserved:** `bitext_train_noisy` (`5233abff...`, `exclude_noisy_test_overlap = false`) remained unchanged per Fit2 parity.
4. **Hard terminal stop:** Budget is permanently `2 / 2` exhausted (`training_stopped = true`, `stop_reason = "budget_exhausted"`). No retry, no Attempt 3, and no further fit proposal are authorized or made.
