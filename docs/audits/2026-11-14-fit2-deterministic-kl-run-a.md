# Fit2 Deterministic Teacher-KL Execution & CAL Guard Audit (`fit2-orig-deterministic-kl-v1`)

- **Date:** 2026-11-14
- **Author:** Worker A (`task_id=task_b5a8db59f96e`, `dispatch_id=ctx_65200ec25ef2`)
- **Pre-Fit Release Basis:** Worker B pre-fit PASS ([2026-11-14-fit2-deterministic-kl-prefit-review-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-deterministic-kl-prefit-review-b.md), `HEAD=ac684c2fb091e30d78e3233151c18bad1be7a183`)
- **Frozen Code Commit:** `e82ec7d6bd3bcf18fe6227837fe2c42845cab943` (branch `minh`)
- **Fit Execution Count:** `1` (`fits_started=1`, `fits_completed=1`, `fits_executed=1`)
- **CAL Guard Verdict:** **`CAL_GUARD_REJECT_DO_NOT_PROMOTE`** (`passed=false`, `6/12` checks passed, `6/12` checks failed)
- **Direction Status:** **STOPPED** on current KL variant (`fit2-orig-deterministic-kl-v1`); zero holdouts/full-C gates run locally, zero promotion, zero extra fits.

## 1. Pre-Fit Verification & Execution Record

- **Prep Bundle Consumed:** [run-records-fit2-orig-deterministic-kl-v1-prep](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-deterministic-kl-v1-prep)
  - `prep_manifest.json` SHA-256: `a2b1983dcaa328423b182ec9ebcaeb969ee5e74330fd13394f01af68426d6fb6`
  - `sidecar_sha_inventory.json` SHA-256: `773c354f760e234cc3c6569a4e8203465bc9da31b34638b165394e66b1943515` (`39/39` verified, `0` mismatches)
  - Git provenance verified (`e82ec7d6` ancestor of `ac684c2f`, `0` source hash mismatches, `0` output path collisions) and `--validate-only` passed on `ac684c2fb091e30d78e3233151c18bad1be7a183`.
- **Executed CLI Command (Exact):**
  ```powershell
  .\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit `
    --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-deterministic-kl-v1-prep" `
    --run-id fit2-orig-deterministic-kl-v1 `
    --profile option_a_teacher_kl_deterministic `
    --epochs 3 `
    --lr 2e-5 `
    --batch-size 32 `
    --seed 42 `
    --fit-mode fit2_supcon_energy `
    --teacher-kl-weight 1.0 `
    --teacher-temperature 1.0 `
    --teacher-weights-sha256 f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa `
    --teacher-student-anchor-mode eval_no_dropout_autograd_enabled `
    --run-authorized-fit
  ```
- **Timing:** `train_seconds = 229.79` (`total command wall time = 267.763s`).
- **Component Losses (`fit_result.json` / `candidate_provenance_manifest.json`; epoch-level archive only, no extra optimizer steps run):**
  - **Epoch 1:** `mean_loss=0.36732`, `pos_loss_sum=0.26035`, `neg_loss_sum=0.00872`, `supcon_loss_sum=0.09654`, `avg_teacher_kl_loss=0.001713`, `weighted_teacher_kl_loss=0.001713`, `anchor_rows_seen=13000`, `excluded_rows_seen=80`
  - **Epoch 2:** `mean_loss=0.35142`, `pos_loss_sum=0.25324`, `neg_loss_sum=0.00854`, `supcon_loss_sum=0.08804`, `avg_teacher_kl_loss=0.001602`, `weighted_teacher_kl_loss=0.001602`, `anchor_rows_seen=13000`, `excluded_rows_seen=80`
  - **Epoch 3:** `mean_loss=0.34768`, `pos_loss_sum=0.25117`, `neg_loss_sum=0.00853`, `supcon_loss_sum=0.08692`, `avg_teacher_kl_loss=0.001065`, `weighted_teacher_kl_loss=0.001065`, `anchor_rows_seen=13000`, `excluded_rows_seen=80`
- **Reload & Provenance Checks:**
  - `calibration_manifest.json` valid: `temperature = 1.0` (`min_temperature = 1.0`), `selective_rejector.enabled = false`
  - `candidate_provenance_manifest.json` valid: `num_labels = 46`, `teacher_student_anchor_mode = "eval_no_dropout_autograd_enabled"`, `anchor_effective_total = 13000`, `excluded_effective_total = 80` (`extension_raw_count = 18`)
  - `verify_reload_from_archive`: `reload_verified = true`, `num_labels = 46`

## 2. Archived Artifacts & Checksums

- **Candidate Archive:** [fit2-orig-deterministic-kl-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-deterministic-kl-v1)
  - `archive_sha_inventory.json` SHA-256: `9c1c76acec5227df624fe3b1bd1baa5429867c0753f4a51847162efc8aff38b8` (`6/6` files verified, `0` mismatches)
  - `model.safetensors`: `e63d1ea963e165aaabdd8b619f2e1bf26914fff746bc9f1b7f888c3acf0191f1`
  - `calibration_manifest.json`: `9c529f862a50ed31ebb6f0091b286c84a92eef73cb8736229c410c119f9468ac`
  - `candidate_provenance_manifest.json`: `dd2e7b1c97dabae4a7bef6cc4c4f73fae16946bbeb3f178ff0a5a03a42692c38`
  - `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
  - `tokenizer.json`: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`
  - `tokenizer_config.json`: `15c067a68c4f12b2019e3a892c1158d4735544703fa496f2a6b73242b5812d84`
- **Run Records:** [run-records-fit2-orig-deterministic-kl-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-deterministic-kl-v1)
  - `sidecar_sha_inventory.json` SHA-256: `d0cbbc9964178ded6bda2af8656b1d23e84919220ec8ec50518cd8c337201c3a` (`41/41` files verified, `0` mismatches)
  - `cal_guard_report.json` SHA-256: `bbe60c54dbca5361ac117ecc7ae53652cb4dec6b91d1d6ff0b47694ea6160ef1`
- **Sealed Reference Checkpoints Unchanged:**
  - Teacher & Init `reconstructed-fit2-supcon-20261113/model.safetensors`: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (verified unchanged)
  - Active serving `artifacts/models/trained/distilbert-supportiq/model.safetensors`: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (verified unchanged)

## 3. Read-Only 12 CAL Guard Checks (`float_tolerance = 3e-6`)

Source: [cal_guard_report.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-deterministic-kl-v1/cal_guard_report.json)

| # | Check Name | Kind | Baseline Ref (`f695b1fe`) | Actual Candidate | Rule / Limit | Status |
|---|---|---|---|---|---|---|
| 1 | `boundary_pos_cal_correct_count` | integer | `68` / `86` | `67` / `86` | `>= 68` | **FAIL** |
| 2 | `boundary_pos_cal_sup12_correct_count` | integer | `38` / `48` | `37` / `48` | `>= 38` | **FAIL** |
| 3 | `bitext_cal_correct_count` | integer | `689` / `690` | `689` / `690` | `>= 687` | **PASS** |
| 4 | `pos_train_added_18_correct_count` | integer | `8` / `18` | `18` / `18` | `>= 15` | **PASS** |
| 5 | `boundary_pos_cal_sup12_conf_ge_070_count` | integer | `28` / `48` | `33` / `48` | `>= 26` | **PASS** |
| 6 | `boundary_pos_cal_sup12_conf_ge_080_count` | integer | `28` / `48` | `29` / `48` | `>= 24` | **PASS** |
| 7 | `boundary_neg_cal_pred_sup12_count` | integer | `9` / `48` | `10` / `48` | `<= 9` | **FAIL** |
| 8 | `boundary_pos_cal_delta_mean_max_prob` | float (`3e-6`) | `0.6863441951590312` (`mean_max_prob`) | `0.029798106456151774` (`0.716142301615183`) | `<= 0.015` | **FAIL** |
| 9 | `boundary_pos_cal_esc34_delta_mean_max_prob` | float (`3e-6`) | `0.6709624479394273` (`mean_max_prob`) | `0.03154005416950523` (`0.7025025021089325`) | `<= 0.015` | **FAIL** |
| 10 | `boundary_pos_cal_esc34_max_sup12_mass` | float (`3e-6`) | `0.4673615502178657` | `0.6732808699082385` | `<= 0.55` | **FAIL** |
| 11 | `boundary_neg_cal_max_sup12_mass` | float (`3e-6`) | `0.7156928153564155` | `0.6672699186278545` | `<= 0.7156928153564155` | **PASS** |
| 12 | `boundary_neg_cal_max_single_sup12_prob` | float (`3e-6`) | `0.5576920642670788` | `0.5274776085614582` | `<= 0.5576920642670788` | **PASS** |

- **Attribution Decomposition Highlights:**
  - `boundary_pos_cal`: `delta_correct_count = -1` (`67` vs `68`), `delta_incorrect_mean_max_prob = +0.08181512969951854` (`0.592513` vs `0.510698`).
  - `boundary_pos_cal_esc34`: `delta_correct_count = 0` (`30` vs `30`), `delta_incorrect_mean_max_prob = +0.1404325530451772` (`0.611294` vs `0.470862`), `delta_mean_true_class_prob = -0.001173476671062268` (`0.592218` vs `0.593392`), `max_sup12_mass = 0.673281` vs limit `0.55`.
  - `boundary_neg_cal`: `pred_sup12_count = 10` vs limit `<= 9`.

## 4. Verdict, Limitations & Stop Boundaries

- **Verdict:** `CAL_GUARD_REJECT_DO_NOT_PROMOTE` — stopping current deterministic Teacher-KL variant (`option_a_teacher_kl_deterministic`, `alpha_kl=1.0`, `T_teacher=1.0`) without automatic retuning, sweeps, or retries.
- **Limitations:**
  - Exploratory single-seed (`seed=42`, `n=1`) run at fixed `alpha_kl=1.0`, `T_teacher=1.0`.
  - Preserves the `3` inherited `bitext_train_noisy` vs eval exact-norm overlaps (`exclude_noisy_test_overlap=false`) for direct comparability with prior baselines.
  - Observed `avg_teacher_kl_loss` remained small (`0.001713 -> 0.001602 -> 0.001065`) relative to `pos_loss_sum + supcon_loss_sum` (~`0.34-0.36`), while `boundary_pos_cal_esc34` wrong-item confidence and `max_sup12_mass` (`0.673281`) and `boundary_neg_cal_pred_sup12_count` (`10`) breached CAL thresholds. This rejects this single run/configuration and does not assert universal impossibility across other loss scales or training designs.
