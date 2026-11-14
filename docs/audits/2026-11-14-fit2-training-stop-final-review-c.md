# Worker C Independent Verification & Final Consolidated Stop Review — Fit2 Program

- **Status:** **`STOPPED`** (`additional_attempts_started = 1/2`, `1` attempt permanently unspent under `training_stopped = true` in [.local/training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json); **NOT** pending another training run; **no model met all acceptance criteria**)
- **Attempt 1/2 Target:** [fit2-orig-classifier-head-only-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-classifier-head-only-v1) (A's audit at `0644285bb35780a064df15a4abed044faeedd4d7`: [2026-11-14-fit2-classifier-head-only-run-a.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-classifier-head-only-run-a.md); frozen code `4e87cdeee5e8cb060289d75cbe53a8e51eb26f23`; B pre-fit [2026-11-14-fit2-classifier-head-only-prefit-review-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-classifier-head-only-prefit-review-b.md))
- **Dual Verdict on Attempt 1/2:** Implementation & Tensor-Freeze Verification **`PASS`**; Bounded CAL Guard **`CAL_GUARD_REJECT_DO_NOT_PROMOTE`** (**`9/12 PASS`, `3/12 FAIL`**, `max_guard_float_diff = 0.0 <= 3e-6`)
- **Scope:** Strictly read-only verification (**0** new fits, **0** optimizer/backward steps, **0** calibrator fits, **0** paid LLM calls, **0** holdout/OOD inferences, **0** next-fit proposals)
- **Verification Bundle ([artifacts/evaluation/fit2_head_only_final_review_c_20261114/](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_head_only_final_review_c_20261114/)):**
  - Script: [verify_head_only_final.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_head_only_final_review_c_20261114/verify_head_only_final.py) (`a346799040a930eca3b6ffcb2f1614bab8239d20d22c1b5749d971d13e8bb1d3`)
  - Consolidated Data: [head_only_cal_verification.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_head_only_final_review_c_20261114/head_only_cal_verification.json) (`49fef530fd5afb067abcfb76040c3c97cb25710fed08b345273529e68a5a6c49`)
  - Manifest: [run_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_head_only_final_review_c_20261114/run_manifest.json) (`cuda`, `15.84s`)

---

## 1. Independent Verification of `fit2-orig-classifier-head-only-v1` (Attempt 1/2)

### 1.1 Archive, Sidecar, Prep, Source Parity & Exact Freeze Proof (`PASS`)
- **Inventories & Hashes (`0` mismatches):**
  - Archive (`6/6`): `model.safetensors` `c0908ffb9794a4c9450959534c694e64dd1c296a2dc65831334a17e7c5409afb`, `calibration_manifest.json` `09720c1367fcd236d239e91499b1b62be70d447c81137629640d82611a1b1fe8` (`T=1.0`, `min_temperature=1.0`, `selective_rejector.enabled=false`), `candidate_provenance_manifest.json` `962b8c80258e42425fdfdb6f6f47f3b7e31d7e68d2c9e02b85fd5d1b70622eb9`, `archive_sha_inventory.json` `f7c00a763cd36dbd31307234b97ce2506ebc750deb07eff0e49c032218c9e4fd`.
  - Sidecar (`41/41`): `cal_guard_report.json` `6420a920eb3fcf4012ab4f56001a6a38a9c48014781e3ae57de2c5e68aaee39b`, `sidecar_sha_inventory.json` `9a7fa92f892282a5a4c52f32a55afd60a4b00d1d10c1e7481fbb501ddd66f5e8`.
  - Prep (`39/39`): `prep_manifest.json` `44432c82091c823f9df0a23a3c9038ac3fdd7068ff2f2f8229d77b15c4695fc6`, `sidecar_sha_inventory.json` `787d0b7c4b3b672775f159f3a0a321494731067bc1f18382cb511bbaadaf6672`.
  - Input parity (`rec/inputs` vs `prep/datasets` and shared `.jsonl` + `split_manifest.json` vs `v4-prep`): **`0` diffs**; `source_snapshot/` vs `run_config.json`, `prep_manifest.json`, and disk: **`0` diffs**.
- **Profile & Frozen Tensor Proof (`orig_fit2` `f695b1fe` -> `c0908ffb`):**
  - Profile `option_a_classifier_head_only_v1` verified (`lr=1e-4`, `epochs=2`, `bs=32`, `wd=0.01`, `seed=42`, `fit_mode=fit2_supcon_energy`, `trainable_scope=classifier_head_only`, `feature_dropout_eval_mode=true`, `teacher_used=false`, `unfrozen_transformer_layers=0`, `train_total_examples=13080`, `train_seconds=41.67`, `supcon_loss_sum=0.0`, `mean_loss` `0.27419 -> 0.26979`).
  - `_snapshot_frozen_component_hashes` independently verified **`102` frozen parameter tensors** (`66,953,472` params = `99.9472%`) + **`1` buffer** (`distilbert.embeddings.position_ids`) match `3b8b48f556d4f2f0c99dad938e470d6caa2184650f09f3af7c0bfb164364d31d` bit-for-bit across all `9` components, with **`0.0` max abs tensor/buffer diff**.
  - **Only** `classifier.weight` (`1.269679` L2 / `27.48%` rel delta vs `4.620543` orig norm; top-shifted row `return_product_in_store` `0.294212` L2, row norm `0.674978 -> 0.729914`) + `classifier.bias` (`0.019506` L2) updated (`35,374` params = `0.0528%`).
- **`ModelContainer` Runtime Parity:** `134/134` boundary CAL rows checked, **`0` intent mismatches**, `max_confidence_abs_diff = 1.648424e-6 <= 3e-6`.

### 1.2 Independent 12-Check CAL Guard Reproduction (`9/12 PASS, 3/12 FAIL -> REJECT`)
Post-`T=1.0` softmax reproduced [cal_guard_report.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-classifier-head-only-v1/cal_guard_report.json) with `0` integer/status mismatches and **`max_guard_float_diff = 0.0 <= 3e-6`**:

| # | Check | Rule / Limit | `orig_fit2` (`f695b1fe`) | `head_only` (`c0908ffb`) | Status |
|---:|---|---|---:|---:|---|
| 1 | `boundary_pos_cal_correct_count` (`n=86`) | `>= 68` | `68` (`0.686344`) | **`67`** (`0.652702`) | **FAIL** |
| 2 | `boundary_pos_cal_sup12_correct_count` (`n=48`) | `>= 38` | `38` | `38` | PASS |
| 3 | `bitext_cal_correct_count` (`n=690`) | `>= 687` | `689` (`0.977800`) | `689` (`0.968311`) | PASS |
| 4 | `pos_train_added_18_correct_count` (`n=18`) | `>= 15` | `8` (`0.504559`) | **`9`** (`0.484304`) | **FAIL** |
| 5 | `boundary_pos_cal_sup12_conf_ge_070_count` | `>= 26` | `28` | `29` | PASS |
| 6 | `boundary_pos_cal_sup12_conf_ge_080_count` | `>= 24` | `28` | `26` | PASS |
| 7 | `boundary_neg_cal_pred_sup12_count` (`n=48`) | `<= 9` | `9` | **`10`** | **FAIL** |
| 8 | `boundary_pos_cal_delta_mean_max_prob` | `<= 0.015` | `0.0` (`0.686344`) | **`-0.033642`** (`0.652702`) | PASS |
| 9 | `boundary_pos_cal_esc34_delta_mean_max_prob` | `<= 0.015` | `0.0` (`0.670962`) | **`-0.044578`** (`0.626384`) | PASS |
| 10 | `boundary_pos_cal_esc34_max_sup12_mass` | `<= 0.55` | `0.467362` | **`0.424806`** | PASS |
| 11 | `boundary_neg_cal_max_sup12_mass` | `<= 0.715693` | `0.715693` | **`0.652838`** | PASS |
| 12 | `boundary_neg_cal_max_single_sup12_prob` | `<= 0.557692` | `0.557692` | **`0.487159`** | PASS |

- **What Happened Mechanism-Wise:** Freezing the `6`-layer encoder + `pre_classifier` completely cured confidence inflation and `sup12` mass spikes (all `5` float drift/mass gates passed with wide headroom). **However**, linear `classifier`-only adaptation could not separate `added_18` (`8/18 -> 9/18`: `return_policy 8/10`, **`return_product_in_store 0/8 -> 1/8`** at `mean_true_class_prob=0.067323`, still losing `7/8` to `return_policy` x4 / `return_product` / `exchange_product_in_store` / `human_agent`), and still triggered the shared CAL boundary regressions (`pos_cal` lost `cls_e34_avonl_cal_1_af025937dd54`, `neg_cal` entered `bnd_neg_homonym_cal_0_b32c79aceec4`, matching Attempt 1 early-stop rule triggers). Canonical TRAIN stayed `181/181` pos and `0/99` `neg pred_sup12`.

---

## 2. Consolidated Program Evidence Across All 7 Fit2 Artifacts (No Unrun Holdouts Inferred)

Only `orig_fit2` and `prior_2e5` were run on full frozen holdout/OOD suites (`9/16 PASS, 7/16 FAIL -> REJECT` for `prior_2e5` in [2026-11-14-fit2-orig-return-contrast-fit-v1-evaluation-c.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-orig-return-contrast-fit-v1-evaluation-c.md)); all subsequent candidates were **blocked at the frozen CAL guard** and unrun holdout suites are **not** inferred:

| Model (`model.safetensors` SHA prefix) | Recipe / Scope | CAL Guard Result | `pos_cal` (`86`, R/W prob) | `sup12` (`48`) | `esc34` (`38`, `max_sup12`) | `neg_cal` (`48`, `pred`/`max_m`/`single`) | `added_18` | Holdout Status |
|---|---|---|---|---|---|---|---|---|
| `orig_fit2` (`f695b1fe`) | Stage-2 `11,320` baseline | Reference | `68` (`0.733`/`0.511`) | `38` | `30` (`0.467362`) | `9` / `0.715693` / `0.557692` | `8/18` (`0.5046`) | Ran; **NOT accepted** (see §3) |
| `zero_delta_control` (`904188aa`) | `+0` rows, `2e-5`, full | **`6/11` (`5` float FAIL)** | `68` (`0.768`/`0.501`) | `38` | `30` (`0.607555`) | `9` / `0.734620` / `0.609309` | `7/18` (`0.4894`) | Blocked at CAL (control) |
| `prior_2e5` (`dc3e88e7`) | `+18`, `2e-5`, full | **`7/12` (`5` FAIL)** | `68` (`0.754`/`0.604`) | `38` | `30` (`0.682218`) | `10` / `0.733993` / `0.582643` | `18/18` (`0.9796`) | Ran full eval: **`9/16` `REJECT`** |
| `cand_lr5e6` (`b7a28547`) | `+18`, `5e-6`, full | **`5/12` (`7` FAIL)** | **`66`** (`0.772`/`0.569`) | **`36`** | `30` (`0.491472`) | `11` / `0.745128` / `0.589594` | `18/18` (`0.9780`) | Blocked at CAL |
| `teacher_kl` (`3994af2c`) | `+18`, `2e-5`, stoch KL | **`4/12` (`8` FAIL)** | **`67`** (`0.785`/`0.590`) | **`37`** | `30` (`0.671330`) | `10` / `0.764955` / `0.611628` | `18/18` (`0.9815`) | Blocked at CAL |
| `deterministic_kl` (`e63d1ea9`) | `+18`, `2e-5`, eval KL | **`6/12` (`6` FAIL)** | **`67`** (`0.751`/`0.593`) | **`37`** | `30` (`0.673281`) | `10` / `0.667270` / `0.527478` | `18/18` (`0.9804`) | Blocked at CAL |
| **`classifier_head_only` (`c0908ffb`)** | **`+18`, `1e-4`, head-only** | **`9/12` (`3` FAIL)** | **`67`** (`0.704`/`0.472`) | `38` | **`29`** (**`0.424806`**) | **`10`** / **`0.652838`** / **`0.487159`** | **`9/18`** (`0.4843`) | **Blocked at CAL -> STOP** |

- **`prior_2e5` Full-Eval Summary vs `orig_fit2` (Existing Observed Metrics):** Improved `unseen36 ret_esc` (`0.778` vs `0.111`, raw/runner leaks `4/3 -> 1/1`), `sa156 sup34` (`28/34` vs `25/34`), `noise420` (`283/420` gate / `276/420` runner vs `267/420` / `260/420`), and `fresh34` (`0` vs `1`), yet **`REJECT`** (`7/16 FAIL`) due to `pos175`, `neg51`, `oos80` (`oos-other_domain-16`), `ind36` (`g2-esc-06`, `g2-esc-09`), `sa156 mand63` (`6` raw / `1` eng), `bitext6690`, and `unseen36` (`ugc-retonl-01`).
- **Core Structural Trade-off:** Every full-backbone continuation fit memorized `added_18` (`18/18`) while drifting encoder weights (`~2.22-2.31` L2 in `encoder_all_6`) and degrading CAL accuracy/separation or confidence calibration; freezing the `6`-layer encoder + `pre_classifier` prevented confidence inflation/mass spikes yet left `return_product_in_store` (`1/8`) linearly inseparable in `f695b1fe`'s frozen representation (`9/18` < `15/18`) while still failing `pos_cal` (`67<68`) and `neg_cal` (`10>9`).

---

## 3. Runtime & Environment Distinction and Preserved Repository State (Read-Only Verified)

| Component | Exact Path / Identifier | SHA-256 / Observed State | Role / Acceptance Status |
|---|---|---|---|
| **Original Fit2** (local active via [.local/ai.env](file:///F:/Năm%203/SD/project/SupportIQ/.local/ai.env)) | `artifacts/models/candidates/reconstructed-fit2-supcon-20261113` | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (`T=1.0`, `selective_rejector=false`; `.local/ai.env` `26d083c7...`; ports `8000`/`8002` offline/timed out) | **Untouched.** Local runtime target only per [2026-11-14-original-fit2-local-activation-d.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-original-fit2-local-activation-d.md); **NOT** production/project acceptance — open safety issues remain (`sa156 mand63` `9` raw / `2` eng / `1` run leaks; `pos175` `4` raw / `3` run; `oos80` `3` raw; `unseen36` `4` raw / `3` run & `ret_esc` `0.111`; `neg_cal max_sup12_mass=0.715693`, `max_single=0.557692`). |
| **Default Serving Artifact** | `artifacts/models/trained/distilbert-supportiq` | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (`v1.0.0`) | **Untouched.** Default repo serving model, distinct from `.local/ai.env` local override (`f695b1fe`). |
| **Other Preserved Models** | `fit1` + `ctrl` + `prior_2e5` + `lr5e6` + `teacher_kl` + `det_kl` + `head_only` | `95a940b6...`, `904188aa...`, `dc3e88e7...`, `b7a28547...`, `3994af2c...`, `e63d1ea9...`, `c0908ffb...` | **100% intact** (`0` SHA mismatches). |
| **Governance & Repo Assets** | [.local/training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json), `docs/report.template.pptx`, `.codegraph/` | Cap `52ff870f...` (`1/2`, `training_stopped=true`); PPTX `08763b39...` (`1,585,591` B); `.codegraph/` (`codegraph.db`, etc.) intact; `artifacts/models/.gitkeep` absent pre-run | **100% preserved.** |

---

## 4. Open Limits & Uncertainty

1. **Inherited Dataset Overlap:** `3` normalized-text overlaps persist identically across all splits between `bitext_train_noisy` and `bitext_test_6690` (`test_idx=203` `sample_001360`, `3137` `sample_020916`, `4685` `sample_031234`), with `0` overlaps on `full_cal_split` or any non-bitext eval suite.
2. **Sample & Design Bounds:** Each attempted configuration ran `n=1` (`seed=42`); `classifier_head_only` changed trainable scope, `lr=1e-4`, and `epochs=2` simultaneously vs `prior_2e5`, so single-factor attribution within the head-only run is bounded.
3. **Unrun Holdouts Not Inferred:** `cand_lr5e6`, `teacher_kl`, `deterministic_kl`, and `classifier_head_only` stopped at the CAL guard without running held-out suites; their held-out behavior is unknown and not extrapolated.
4. **No Promotion & Training Halted:** No candidate satisfied acceptance criteria; `f695b1fe` retains known escalation/OOD safety gaps; training is **`STOPPED`** (`1/2` used, `1` unspent).
