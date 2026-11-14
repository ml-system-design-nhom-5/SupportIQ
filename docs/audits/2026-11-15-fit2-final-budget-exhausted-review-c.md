# Worker C Final Attempt (2/2) Verification & Budget-Exhausted Stop Review — Fit2

- **Terminal Program Status:** **`STOPPED`** (`additional_attempts_started = 2/2` exhausted, `training_stopped = true`, `stop_reason = "budget_exhausted"`, `final_attempt = true`, `no_more_training_authorized = true` in [.local/training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json)); **no eligible candidate**, **no promotion**, **no Fit 3 / next-fit proposal**
- **Final Attempt 2/2 Target:** [fit2-orig-pre-classifier-head-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-pre-classifier-head-v1) (A's audit at `9fbdebc149fb04a013ca40badbbe6cabf8d579dc`: [2026-11-15-fit2-final-attempt-fit-a.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-15-fit2-final-attempt-fit-a.md); source `f90deedb23b760a129f3aeaaedc92ea0c5c6d286`; Worker B review `c207026d3c4b1f089793e25ea7b7dae0b3e50858`; prep `23b82dfe9a17d384fd85ad7f24d9a8c9cb61f2f05f7a95c4290e1cab6971d3dc`)
- **Dual Verdict (Attempt 2/2):** Archive, Freeze & Lineage Verification **`PASS`**; Bounded CAL Guard **`CAL_GUARD_REJECT_DO_NOT_PROMOTE`** (**`10/12 PASS, 2/12 FAIL`**, `max_guard_float_diff = 0.0 <= 3e-6`, zero full EVAL executed)
- **Evidence Bundle ([artifacts/evaluation/fit2_final_attempt_review_c_20261115/](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_final_attempt_review_c_20261115/)):**
  - Script: [verify_final_attempt_c.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_final_attempt_review_c_20261115/verify_final_attempt_c.py) (`2f9b8a81b8a6bb8dac87e28074ed7504b013543ee4955b5dc00a568a0c2ceb59`)
  - Metrics JSON: [final_attempt_cal_verification.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_final_attempt_review_c_20261115/final_attempt_cal_verification.json) (`55bb8e4ae3a11662d26d8ee28ecb5212e2dd7dd5e1ed6dd2046eae1c70d03b7f`)
  - Manifest: [run_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_final_attempt_review_c_20261115/run_manifest.json) (`cuda`, `19.4s`)

---

## 1. Attempt 2/2 Archive, Freeze & Runtime Verification (`PASS`)

- **Sealed Archive & Records (`0` mismatches):**
  - Archive (`6/6`, [archive_sha_inventory.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-pre-classifier-head-v1/archive_sha_inventory.json) `87587acc935067d43f0002d1918eed91463360fb8676a1785f3954d474d8b27e`): `model.safetensors` `374afde7977434ac0aae19efd2ac55bcfb6c04127531a355098dfe62a7490369`, `calibration_manifest.json` `9d7fc0b79a52d5760c803c67e9ffab1355021bf570f3ae809d4aeb814cbac6c5` (`T=1.0`, `min_temperature=1.0`, `selective_rejector.enabled=false`), `candidate_provenance_manifest.json` `69cfb56ebe15422725baff634bf5a3167322337c0d9044747fe39a33073de1bc`.
  - Sidecar (`41/41`, `db4e56df14992bbefb6a0bdb59656739dd242f22fe2b5927b090618869d5cf9b`): `cal_guard_report.json` `9b3ec85c1f3f9aa5dd48607da814c1a8b82ef43cc340761cea66343fecfd4b9b`; Prep (`39/39`): `prep_manifest.json` `23b82dfe9a17d384fd85ad7f24d9a8c9cb61f2f05f7a95c4290e1cab6971d3dc`.
  - Parity (`0` diffs): `rec/inputs` vs `prep/datasets`, shared `.jsonl` + `split_manifest.json` vs `v4-prep`, and `source_snapshot/` vs `run_config.json`, `prep_manifest.json`, and disk all matched cleanly.
- **Profile, Scope & Exact Freeze Proof (`orig_fit2` `f695b1fe` -> `374afde7`):**
  - Profile `option_a_pre_classifier_head_v1` verified: `lr=5e-5`, `epochs=3`, `wd=0.01`, `bs=32`, `seed=42`, `fit_mode=fit2_supcon_energy`, `trainable_scope=pre_classifier_and_classifier`, `feature_dropout_eval_mode=true`, `teacher_used=false`, `unfrozen_transformer_layers=0`, `fits_started=1`, `fits_completed=1`, `train_seconds=47.56`, `train_total_examples=13080`, `supcon_loss_sum=0.0`.
  - `_snapshot_frozen_component_hashes` independently verified **`100` frozen encoder tensors** (`66,362,880` params) + **`1` buffer** (`distilbert.embeddings.position_ids`) match **`d16052a208919dfd2fa09f8bb4330ddbc37fab58fa7c8573dd31a686083a0151`** PRE and POST (`8/8` components), with **`0.0` max abs diff**.
  - **Strictly `4` trainable subhead tensors (`625,966` params) updated:** `pre_classifier.weight` (`1.756067` L2 / `10.70%` rel / `max_abs=0.019786`), `pre_classifier.bias` (`0.045151` L2 / `max_abs=0.006339`), `classifier.weight` (`0.911081` L2 / `19.72%` rel / `max_abs=0.028003`), `classifier.bias` (`0.011187` L2 / `max_abs=0.004640`).
- **`ModelContainer` Runtime Parity:** `134/134` boundary CAL rows checked, **`0` intent mismatches**, `max_confidence_abs_diff = 1.935956e-6 <= 3e-6`.

---

## 2. Recomputed 12-Check CAL Guard (`10/12 PASS, 2/12 FAIL -> REJECT`)

Raw post-`T=1.0` `float64` softmax reproduced [cal_guard_report.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-pre-classifier-head-v1/cal_guard_report.json) with `0` integer/status mismatches and **`max_guard_float_diff = 0.0 <= 3e-6`**:

| # | Check | Rule / Limit (`tol 3e-6`) | `orig_fit2` (`f695b1fe`) | `pre_cls_head` (`374afde7`) | Status |
|---:|---|---|---:|---:|---|
| 1 | `boundary_pos_cal_correct_count` (`86`) | `>= 68` | `68` (`0.686344`) | **`64`** (`0.681179`) | **FAIL** (`-4`) |
| 2 | `boundary_pos_cal_sup12_correct_count` (`48`) | `>= 38` | `38` | **`34`** | **FAIL** (`-4`) |
| 3 | `bitext_cal_correct_count` (`690`) | `>= 687` | `689` (`0.977800`) | `689` (`0.968163`) | PASS |
| 4 | `pos_train_added_18_correct_count` (`18`) | `>= 15` | `8` (`0.504559`) | **`18`** (`0.691377`) | PASS |
| 5 | `boundary_pos_cal_sup12_conf_ge_070_count` | `>= 26` | `28` | `32` | PASS |
| 6 | `boundary_pos_cal_sup12_conf_ge_080_count` | `>= 24` | `28` | `27` | PASS |
| 7 | `boundary_neg_cal_pred_sup12_count` (`48`) | `<= 9` | `9` | **`6`** | PASS (`-3`) |
| 8 | `boundary_pos_cal_delta_mean_max_prob` | `<= 0.015` | `0.0` (`0.686344`) | **`-0.005165`** (`0.681179`) | PASS |
| 9 | `boundary_pos_cal_esc34_delta_mean_max_prob` | `<= 0.015` | `0.0` (`0.670962`) | **`-0.019263`** (`0.651700`) | PASS |
| 10 | `boundary_pos_cal_esc34_max_sup12_mass` | `<= 0.55` | `0.467362` | **`0.447036`** | PASS |
| 11 | `boundary_neg_cal_max_sup12_mass` | `<= 0.715693` | `0.715693` | **`0.658285`** | PASS |
| 12 | `boundary_neg_cal_max_single_sup12_prob` | `<= 0.557692` | `0.557692` | **`0.473540`** | PASS |

- **Diagnostic Reading (Not Accepted):** Attempt `2/2` shows safety-confidence gains (`neg_cal pred_sup12 9 -> 6`, `neg_mass 0.658285`, `neg_single 0.473540`, `esc_mass 0.447036`, `added_18 18/18`) **paired with a significant utility loss** (`pos_cal 68 -> 64`, `sup12 38 -> 34`: gained `1` `cls_e34_chg_cal_0_c36a18761dec`, lost `5` — `cls_rpr_qc_inspection_2_80de0abcbaeb`, `cls_pay_ewallet_timeout_2_3e025e118d68`, `cls_hum_escalate_now_1_58df76a91338`, `bnd_return_product_cal_0_f6c7b606561c`, and `cls_e34_avonl_cal_1_af025937dd54` flipping to `return_product_in_store @ 0.6532`). Notably, all `3` `neg_cal` exits (`cls_neg_cmi_cal_rpo_shp_hum_0_ec38e6e4895f`, `cls_neg_cmi_cal_rpo_shp_hum_1_50501565a035`, `cls_neg_cmi_cal_pay_inv_pinfo_2_ed26ede4b742`) shifted argmax into `return_product_in_store` (in `esc34`, while their `sup12_mass` slightly increased). Do **not** relax `pos_cal`/`sup12` thresholds to accept, and do **not** claim held-out safety (not measured).

---

## 3. FINAL Consolidated 2-Attempt Comparison Table (Pre-Cap Runs Referenced Only)

| Run / Role | Weights SHA-256 | Scope / LR / Ep | `pos_cal` (`86`) | `sup12` (`48`) | `esc34` (`38`, `max_sup12`) | `neg_cal` (`48`, `pred`/`max_m`/`single`) | `new18` (`18`) | CAL Verdict / Eval |
|---|---|---|---:|---:|---:|---|---:|---|
| **Baseline (`orig_fit2`)** | `f695b1fe...` | Stage-2 `11,320` ref | `68` (`0.6863`) | `38` | `30` (`0.467362`) | `9` / `0.715693` / `0.557692` | `8/18` (`0.5046`) | Reference (**open safety issues**) |
| **Attempt 1/2 (`head_only`)** | `c0908ffb...` | `classifier` (`35,374`), `1e-4`, `2`ep | **`67`** (`0.6527`) | `38` | `29` (`0.424806`) | **`10`** / `0.652838` / `0.487159` | **`9/18`** (`0.4843`) | **REJECT (`9/12`, `3` FAIL)**; no eval |
| **Attempt 2/2 (`pre_cls_head`)** | `374afde7...` | `pre_cls+cls` (`625,966`), `5e-5`, `3`ep | **`64`** (`0.6812`) | **`34`** | `30` (`0.447036`) | `6` / `0.658285` / `0.473540` | `18/18` (`0.6914`) | **REJECT (`10/12`, `2` FAIL)**; no eval |

- **Historical Pre-Cap Runs (Reference Only, No Re-Runs):** Prior full-backbone attempts (`zero_delta_control` `904188aa` `6/11` CAL fail; `prior_2e5` `dc3e88e7` `7/12` CAL fail & `9/16` full-eval `REJECT`; `cand_lr5e6` `b7a28547` `5/12` CAL fail; `teacher_kl` `3994af2c` `4/12` CAL fail; `deterministic_kl` `e63d1ea9` `6/12` CAL fail) are consolidated verbatim in [2026-11-14-fit2-training-stop-final-review-c.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-training-stop-final-review-c.md) and remain intact on disk.

---

## 4. Runtime, Preserved Repository State, Cleanup & Limits

- **Runtime Distinction & Read-Only Health:** [.local/ai.env](file:///F:/Năm%203/SD/project/SupportIQ/.local/ai.env) (`26d083c7...`) remains pointed at original Fit2 `reconstructed-fit2-supcon-20261113` (`f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`), distinct from the untouched archived default serving checkpoint [distilbert-supportiq](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/trained/distilbert-supportiq) (`dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`). Read-only GET on `127.0.0.1:8002/health/ready` and `127.0.0.1:8000/health/ready` timed out (no local server running; `0` restarts/config changes). Original `f695b1fe` remains active only as configured in `.local/ai.env` and is **not** accepted on all project safety/eval requirements.
- **Preserved State & Unexecuted Cleanup Plan:** All models/checkpoints on disk (including rejects: `fit1` `95a940b6...`, `orig_fit2` `f695b1fe...`, `serving` `dc7af8cf...`, `ctrl` `904188aa...`, `prior_2e5` `dc3e88e7...`, `lr5e6` `b7a28547...`, `teacher_kl` `3994af2c...`, `det_kl` `e63d1ea9...`, `head_only` `c0908ffb...`, `pre_cls_head` `374afde7...`), all datasets/archives, [.local/training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json) (`bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`), `docs/report.template.pptx` (`1,585,591` B, `08763b39d1c80db4f84f6a369ab62692f83f5611b5513097ac1eed11eb104ad7`), `.codegraph/`, and pre-existing `D artifacts/models/.gitkeep` remain untouched. Worker D's cleanup plan ([2026-11-14-code-cleanup-preparation-d.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-code-cleanup-preparation-d.md)) remains prepared-only and **unexecuted**.
- **Open Limits:**
  1. **Inherited Overlap:** `3` normalized-text overlaps persist between `bitext_train_noisy` and `bitext_test_6690` (`sample_001360`, `sample_020916`, `sample_031234`); `0` overlaps in `full_cal_split` or non-bitext eval suites.
  2. **`n=1` & Multi-Factor Confounds:** Each run tested a single seed (`42`); Attempt `2/2` changed trainable scope (`classifier` -> `pre_classifier+classifier`), `lr` (`1e-4` -> `5e-5`), and `epochs` (`2` -> `3`) together.
  3. **Unmeasured Holdouts:** Both additional attempts failed the frozen CAL guard and executed **0** full holdout evaluations; held-out behavior is unmeasured and not inferred.
  4. **Final Stop:** Budget is permanently **`2/2` exhausted** (`training_stopped=true`); no candidate met acceptance and no further training or proposal is made.
