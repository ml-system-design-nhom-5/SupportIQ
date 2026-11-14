# Worker A Single-Fit Execution & 12-Check CAL Audit: `fit2-orig-teacher-kl-v1`

- **Date:** 2026-11-14
- **Role / Dispatch:** Worker A (`task_6a318d713dc7`, branch `minh`)
- **Pre-Fit Gate References:**
  - Frozen source/test commit: `6b7a0c4c020fa9565b9e11ce4864c05f8895f3d5`
  - Prep audit commit: `55bb42630f20cda9b92ac85e17c747d8100002ff`
  - Coordinator-released Worker B pre-fit review commit (`HEAD` at fit launch): `8401bf5ea829ee7e3f309d20afaf39485101dcc6`
  - Sealed prep bundle: `artifacts/models/candidates/run-records-fit2-orig-teacher-kl-v1-prep` (`prep_manifest.json` SHA-256 `3234e31bea47402b4d6ef2da1ceb0fe3434e470c707c848dbc538918b2049286`)
- **Fits Executed:** `1` (`fits_started: 1`, `fits_completed: 1`, `status: complete`)
- **CAL Guard Decision:** **`CAL_GUARD_REJECT_DO_NOT_PROMOTE`** (`cal_guard_passed: false`, `4` passed / `8` failed of `12` checks)
- **Active Promotion State:** Unchanged (Original Fit2 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` & Serving remain untouched; no retry/auto-fit executed; Worker C holdout evaluation NOT run by Worker A)

---

## 1. Archive & Provenance Summary

- **Candidate Archive:** [fit2-orig-teacher-kl-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-teacher-kl-v1)
- **Run Records:** [run-records-fit2-orig-teacher-kl-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-teacher-kl-v1)
- **Exact Checksums & Audits:**
  - Candidate `model.safetensors` SHA-256: `3994af2c461cd029f4d03dbec38a75b2bb103a78d8550f4f3a20078b354bca06`
  - Candidate `tokenizer.json` SHA-256: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`
  - Candidate `config.json` SHA-256: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
  - `calibration_manifest.json` SHA-256: `4e06df8f2ecd11fb72d9e8163525eafe06ca0feebba87310e808cdfbd7b88db8` (`valid: true`, `temperature: 1.0`, `min_temperature: 1.0`, `selective_rejector.enabled: false`, `calibration_sample_count: 776`)
  - `candidate_provenance_manifest.json` SHA-256: `ceacdb9f00f8f1d3e5a588080cdb747543db0d71446fa4b89b99d0c9ef592bcc` (`provenance_passed: true`, `num_labels: 46`, `reload_verified: true`)
  - `cal_guard_report.json` SHA-256: `34967831ff85a4d8a1da611f3c49cd5bda8d4d916a6428adc2448a4cd2eaeb8e`
  - `archive_sha_inventory.json`: `6` files verified, `0` mismatches (`[]`)
  - `sidecar_sha_inventory.json`: `41` files verified, `0` mismatches (`[]`)
- **Teacher Immutability Proof:**
  - Starting student & frozen teacher checkpoint: `reconstructed-fit2-supcon-20261113`
  - Pre-fit & post-fit `model.safetensors` SHA-256: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (`teacher_unchanged: true`, verified both by trainer post-loop SHA check and independent post-fit Python hash check).
- **Execution Telemetry (`cuda`, `train_seconds: 138.9`):**
  - Recipe: `profile=option_a_teacher_kl`, `fit_mode=fit2_supcon_energy`, `epochs=3`, `batch_size=32`, `lr=2e-5`, `seed=42`, `teacher_kl_weight=1.0`, `teacher_temperature=1.0`, `13,000` anchored (`772` canonical pos + `11,040` bitext + `1,188` neg) and `80` (`18` raw `orig_ret_ch_*`) excluded per epoch (`13,080` total).
  - Epoch 1: `mean_loss=0.37096`, `pos=0.26082`, `neg=0.00874`, `supcon=0.09677`, `avg_teacher_kl=0.004617`
  - Epoch 2: `mean_loss=0.35362`, `pos=0.25328`, `neg=0.00855`, `supcon=0.08818`, `avg_teacher_kl=0.003612`
  - Epoch 3: `mean_loss=0.35072`, `pos=0.25157`, `neg=0.00854`, `supcon=0.08714`, `avg_teacher_kl=0.003476`

---

## 2. All 12 Locked CAL Guard Checks (`orig_fit2_cal_guard_report.v1`)

Read-only post-T evaluation (`T = 1.0`, float tolerance `3e-6`) against locked Original Fit2 baseline (`f695b1fe`):

| # | Check Name | Actual | Rule / Limit (+ tol) | Baseline Ref | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | `boundary_pos_cal_correct_count` | `67 / 86` (`0.779070`) | `>= 68` | `68` (`-1`) | **FAIL** |
| 2 | `boundary_pos_cal_sup12_correct_count` | `37 / 48` (`0.770833`) | `>= 38` | `38` (`-1`) | **FAIL** |
| 3 | `bitext_cal_correct_count` | `689 / 690` (`0.998551`) | `>= 687` | `689` (`0`) | **PASS** |
| 4 | `pos_train_added_18_correct_count` | `18 / 18` (`1.000000`) | `>= 15` | `8` (`+10`) | **PASS** |
| 5 | `boundary_pos_cal_sup12_conf_ge_070_count` | `34` | `>= 26` | `28` | **PASS** |
| 6 | `boundary_pos_cal_sup12_conf_ge_080_count` | `32` | `>= 24` | `28` | **PASS** |
| 7 | `boundary_neg_cal_pred_sup12_count` | `10 / 48` | `<= 9` | `9` (`+1`) | **FAIL** |
| 8 | `boundary_pos_cal_delta_mean_max_prob` | `+0.055831` (`0.742175` vs `0.686344`) | `<= 0.015` | — | **FAIL** |
| 9 | `boundary_pos_cal_esc34_delta_mean_max_prob` | `+0.060602` (`0.731564` vs `0.670962`) | `<= 0.015` | — | **FAIL** |
| 10 | `boundary_pos_cal_esc34_max_sup12_mass` | `0.671330` | `<= 0.55` | `0.467362` | **FAIL** |
| 11 | `boundary_neg_cal_max_sup12_mass` | `0.764955` | `<= 0.715693` | `0.715693` | **FAIL** |
| 12 | `boundary_neg_cal_max_single_sup12_prob` | `0.611628` | `<= 0.557692` | `0.557692` | **FAIL** |

- **CAL Attribution Summary:**
  - `boundary_pos_cal_esc34`: `30/38` correct (`+0`), `incorrect_mean_max_prob` rose by `+0.164271` (`0.635133` vs `0.470862`).
  - `boundary_pos_cal_sup12`: `37/48` correct (`-1`), `all_mean_max_prob` rose by `+0.052054`.
  - `boundary_neg_cal`: `pred_sup12` rose `9 -> 10`; `mean_sup12_mass` rose `0.248401 -> 0.254404`.

---

## 3. Scope Limits & Next State

- Single-objective contrast vs unanchored `option_a` (`lr=2e-5`): `alpha_kl = 1.0` at `T_teacher = 1.0` was an exploratory single-run coefficient (`n=1`, no LR/weight sweep); KL magnitude (`0.0046 -> 0.0035`) was small relative to `pos_loss` (`~0.252`) and `supcon` (`~0.087`), and did not prevent probability-inflation or negative/pos-CAL drift under `lr=2e-5` continuation.
- `3` historical `bitext_train_noisy` vs eval exact-norm overlaps remain disclosed unmodified (`exclude_noisy_test_overlap: false`).
- Candidate archives and sidecar records remain intact for downstream inspection / Worker C assignment if desired; **no further training or promotion performed.**
