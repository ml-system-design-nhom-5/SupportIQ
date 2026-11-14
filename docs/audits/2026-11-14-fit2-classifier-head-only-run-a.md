# Fit2 Classifier-Head-Only Attempt 1 Run Audit (Worker A)

- **Date / UTC Completion:** `2026-11-14T16:32:44.758758+00:00`
- **Role & Dispatch:** Worker A (`task_b59858733876`, `dispatch_id=ctx_02b06afa033f`)
- **Pre-Fit Gate Input:** [2026-11-14-fit2-classifier-head-only-prefit-review-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-classifier-head-only-prefit-review-b.md) (`PASS`, `HEAD=4e87cdeee5e8cb060289d75cbe53a8e51eb26f23`)
- **Run ID / Profile:** `fit2-orig-classifier-head-only-v1` / `option_a_classifier_head_only_v1`
- **Verdict:** **`CAL_GUARD_REJECT_DO_NOT_PROMOTE` — HARD EARLY STOP TRIGGERED**
- **Training Budget Consumed:** **`1 / 2`** (`additional_attempts_started: 1`, `additional_attempt_limit: 2` in `.local/training-cap-20261114.json`; **Attempt 2/2 remains unspent**)

---

## 1. Execution Provenance & Training Telemetry

- **Git HEAD at Execution:** `4e87cdeee5e8cb060289d75cbe53a8e51eb26f23` (`prep_git_commit`: `a433e9fa7ecaab0d2edfdbd46e834b9492772762`, `prep_schema_version`: `orig_fit2_return_contrast_prep.v4`)
- **Prep Dir & Manifest SHA-256:**
  - `F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-classifier-head-only-v1-prep`
  - `prep_manifest_sha256`: `44432c82091c823f9df0a23a3c9038ac3fdd7068ff2f2f8229d77b15c4695fc6`
- **Exact Executed Command (`FIT_EXIT=0`, wall `78.768s`, `train_seconds=41.67`, `fits_executed=1`):**
  ```powershell
  .\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-classifier-head-only-v1-prep" --run-id fit2-orig-classifier-head-only-v1 --profile option_a_classifier_head_only_v1 --epochs 2 --lr 1e-4 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --weight-decay 0.01 --trainable-scope classifier_head_only --feature-dropout-eval-mode --run-authorized-fit
  ```
- **Environment (`environment.json`):** Python `3.12.14`, PyTorch `2.11.0+cu128`, Transformers `5.22.1`, CUDA `NVIDIA GeForce RTX 5060`
- **Training Hyperparameters & Epoch Telemetry (`fit_result.json`, `train_total_examples=13080`):**
  - `fit_mode`: `fit2_supcon_energy`, `trainable_scope`: `classifier_head_only`, `feature_dropout_eval_mode`: `true`, `teacher_used`: `false`, `epochs`: `2`, `batch_size`: `32`, `lr`: `1e-4`, `weight_decay`: `0.01`, `seed`: `42`, `max_length`: `64`, `supcon_inactive_under_frozen_encoder`: `true`
  - Epoch 1: `mean_loss=0.27419`, `pos_loss_sum=0.26602`, `neg_loss_sum=0.00817`, `supcon_loss_sum=0.0`
  - Epoch 2: `mean_loss=0.26979`, `pos_loss_sum=0.26157`, `neg_loss_sum=0.00822`, `supcon_loss_sum=0.0`

---

## 2. Artifact, Sidecar, Freeze, & Untouched-Checkpoint SHA-256 Verification

### Archived Candidate (`artifacts/models/candidates/fit2-orig-classifier-head-only-v1`)
- `archive_sha_inventory.json` SHA-256: `f7c00a763cd36dbd31307234b97ce2506ebc750deb07eff0e49c032218c9e4fd` (**6 / 6 files verified, 0 mismatches**)
  - `model.safetensors`: `c0908ffb9794a4c9450959534c694e64dd1c296a2dc65831334a17e7c5409afb`
  - `calibration_manifest.json`: `09720c1367fcd236d239e91499b1b62be70d447c81137629640d82611a1b1fe8`
  - `candidate_provenance_manifest.json`: `962b8c80258e42425fdfdb6f6f47f3b7e31d7e68d2c9e02b85fd5d1b70622eb9`
  - `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
  - `tokenizer.json`: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`
  - `tokenizer_config.json`: `15c067a68c4f12b2019e3a892c1158d4735544703fa496f2a6b73242b5812d84`

### Run-Records Sidecar (`artifacts/models/candidates/run-records-fit2-orig-classifier-head-only-v1`)
- `sidecar_sha_inventory.json` SHA-256: `9a7fa92f892282a5a4c52f32a55afd60a4b00d1d10c1e7481fbb501ddd66f5e8` (**41 / 41 files verified, 0 mismatches**)
- `cal_guard_report.json` SHA-256: `6420a920eb3fcf4012ab4f56001a6a38a9c48014781e3ae57de2c5e68aaee39b`

### Untouched Reference & Active Checkpoints
- **Teacher / Init (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`):** `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (unchanged)
- **Active Serving (`artifacts/models/trained/distilbert-supportiq/model.safetensors`):** `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (unchanged)

### Independent Post-Archive Freeze & Classifier-Head Delta Verification
Reloaded both saved checkpoints directly from disk (`AutoModelForSequenceClassification.from_pretrained`) after fit completion:
- **Trainable scope (`2` tensors, `35,374` params):** Updated vs `f695b1fe`:
  - `classifier.weight` max abs diff = `0.045400314033031464`
  - `classifier.bias` max abs diff = `0.00617041764780879`
- **Frozen scope (`102` parameter tensors = `66,953,472` params + `distilbert.embeddings.position_ids` buffer):**
  - `frozen_param_max_diffs = []` (zero difference on every non-`classifier.` tensor)
  - `_snapshot_frozen_component_hashes` (with `requires_grad = n.startswith('classifier.')`): **`all_frozen_tensors_sha256 = 3b8b48f556d4f2f0c99dad938e470d6caa2184650f09f3af7c0bfb164364d31d`** bit-identical between `reconstructed-fit2-supcon-20261113` and archived `fit2-orig-classifier-head-only-v1`, including all 9 components:
    - `distilbert.embeddings`: `9662676024c6a6cb5fca578d3466f5e9c43ca91d39c98e396ffb900532c07262`
    - `distilbert.transformer.layer.0`: `4cdcd10c2469d3de420d0bb25ead6008096a4206b0f1d748613cd8d782b1bcee`
    - `distilbert.transformer.layer.1`: `a0d27f1fc52822d252b8c4146254806665eea459a8d02a428a6090d74849301a`
    - `distilbert.transformer.layer.2`: `febe747d5591c061c230d432e43077d3c63ac91c2742ef5aadb14c16715a9c61`
    - `distilbert.transformer.layer.3`: `e3d9604616019ddce3b6acd5146c3b1820ef5b21bae592601224006ef8afcc68`
    - `distilbert.transformer.layer.4`: `a72929efd64a023781ae687d245529d1ff264526a63066705c3735df681537d4`
    - `distilbert.transformer.layer.5`: `0df9904d111f7f430858ccba2dfa5339c49a6747b24dc77bd578994219b1fc1a`
    - `pre_classifier`: `ab5fb6bded85a99fdfb14ed784c28ebaf061bcdb9ffe2e81f35706ca28103c58`
    - `buffers` (`distilbert.embeddings.position_ids` = `5738153ec97595b1c1e4dc027f7b7fb4534f19ed2ce9f9ee712e6d34a384cde7`): `26ef7d8b98537c99d82b8d135adab799031872d26387aa5545315a0d87e4c57f`
- **Calibration, Provenance, & Reload Audits:**
  - Temperature scaling (`temperature_scaling_nll`, `calibration_sample_count=776`): `T=1.0` (`min_temperature=1.0`), `valid=true`, `selective_rejector.enabled=false`
  - Provenance (`candidate_provenance_manifest.json`): `provenance_status="verified"`, `46` labels (`valid_46_label_bijection=true`), `truncated_count=0` across all 6 audited splits
  - Reload verified: `reload_verified=true`, `num_labels=46`

---

## 3. CAL-Only 12-Check Guard Results (`cal_guard_report.json`)

Schema `orig_fit2_cal_guard_report.v1`, `cal_guard_mode="candidate_12_checks"`, `read_only_post_fit_guard=true`, `float_tolerance=3e-6`. Baseline checkpoint is `reconstructed-fit2-supcon-20261113` (`f695b1fe`, `T=1.0`).

| # | Check | Kind | Candidate Actual | Baseline (`f695b1fe`) | Rule / Limit (`tol=3e-6`) | Status |
|---|---|---|---|---|---|---|
| 1 | `boundary_pos_cal_correct_count` | int | **`67`** (`67/86`, `0.779070`) | `68` (`68/86`, `0.790698`) | `>= 68` | **FAIL** |
| 2 | `boundary_pos_cal_sup12_correct_count` | int | `38` (`38/48`, `0.791667`) | `38` (`38/48`, `0.791667`) | `>= 38` | PASS |
| 3 | `bitext_cal_correct_count` | int | `689` (`689/690`, `0.998551`) | `689` (`689/690`, `0.998551`) | `>= 687` | PASS |
| 4 | `pos_train_added_18_correct_count` | int | **`9`** (`9/18`, `0.500000`) | `8` (`8/18`, `0.444444`) | `>= 15` | **FAIL** |
| 5 | `boundary_pos_cal_sup12_conf_ge_070_count` | int | `29` | `28` | `>= 26` | PASS |
| 6 | `boundary_pos_cal_sup12_conf_ge_080_count` | int | `26` | `28` | `>= 24` | PASS |
| 7 | `boundary_neg_cal_pred_sup12_count` | int | **`10`** (`10/48`) | `9` (`9/48`) | `<= 9` | **FAIL** |
| 8 | `boundary_pos_cal_delta_mean_max_prob` | float | `-0.03364186423584026` (`0.652702` vs `0.686344`) | `0.6863441951590312` | `<= 0.015` | PASS |
| 9 | `boundary_pos_cal_esc34_delta_mean_max_prob` | float | `-0.044578418675821796` (`0.626384` vs `0.670962`) | `0.6709624479394273` | `<= 0.015` | PASS |
| 10 | `boundary_pos_cal_esc34_max_sup12_mass` | float | `0.4248058372541098` | `0.4673615502178657` | `<= 0.55` | PASS |
| 11 | `boundary_neg_cal_max_sup12_mass` | float | `0.6528381962120668` | `0.7156928153564155` | `<= 0.7156928153564155` | PASS |
| 12 | `boundary_neg_cal_max_single_sup12_prob` | float | `0.4871586095427117` | `0.5576920642670788` | `<= 0.5576920642670788` | PASS |

- **Gate Result:** **`9 / 12` passed, `3 / 12` failed** (`boundary_pos_cal_correct_count`, `pos_train_added_18_correct_count`, `boundary_neg_cal_pred_sup12_count`) -> `cal_guard_passed = false`, `recommended_status = CAL_GUARD_REJECT_DO_NOT_PROMOTE`.
- **Attribution Breakdown Summary (`cal_guard_report.json`):**
  - `boundary_pos_cal`: `delta_correct_count = -1` (`67` vs `68`), `delta_mean_true_class_prob = -0.031076`, `delta_all_mean_max_prob = -0.033642` (`correct_mean_max_prob` dropped `-0.028846`, `incorrect_mean_max_prob` dropped `-0.038861`).
  - `boundary_pos_cal_esc34`: `delta_correct_count = -1` (`29/38` vs `30/38`), `delta_mean_true_class_prob = -0.036556`.
  - `boundary_pos_cal_sup12`: `delta_correct_count = 0` (`38/48`), `delta_mean_true_class_prob = -0.026737`.
  - `boundary_neg_cal` (`48` rows): `pred_sup12_count` regressed `9 -> 10` (FAIL), even though `max_sup12_mass` (`0.715693 -> 0.652838`), `mean_sup12_mass` (`0.248401 -> 0.244380`), and `max_single_sup12_prob` (`0.557692 -> 0.487159`) decreased.
  - `bitext_cal` (`690` rows): `689/690` (`0.998551`), unchanged correct count (`delta=0`).
  - `pos_train_added_18`: `9/18` (`0.50`) vs `8/18` (`0.444444`), `+1` gain, far short of `>= 15/18`.

---

## 4. Early-Stop Decision & Methodological Limits

- **Decision:** **`CAL_GUARD_REJECT_DO_NOT_PROMOTE` — HARD EARLY STOP.** Holdouts (`boundary_pos_evaluation`, `boundary_neg_evaluation`, `bitext_test_6690`, `ml_oos_80`, `system_acceptance_156`) and Full C-gate were **NOT** executed, active serving weights remain unchanged (`dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`), and **Attempt 2/2 remains unspent** (`additional_attempts_started = 1` of `2`).
- **Observed Result Interpretation & Limits:**
  - **Multi-factor attribution limit:** Option A changed both trainable architecture (`classifier_head_only`, `classifier.weight`/`classifier.bias` only) and optimization/regularization recipe (`epochs=2`, `lr=1e-4`, `weight_decay=0.01`, `feature_dropout_eval_mode=true`, inactive SupCon `supcon_loss_sum=0.0`) simultaneously at `n=1` (`seed=42`), so this single negative run cannot separate optimizer sensitivity from head-only capacity limits.
  - **1-NN frozen representation geometry limit:** Pre-fit audit already documented `0 / 8` 1-NN same-label separation on these `8` hard-case anchors inside the frozen `768`-d representation (`reconstructed-fit2-supcon-20261113`); a linear `768 -> 46` classifier head alone cannot untangle classes whose `pre_classifier` features are non-separable (`pos_train_added_18` moved only `8/18 -> 9/18`, while `boundary_pos_cal` and `boundary_neg_cal` integer classification counts regressed).
  - **Historical noisy overlap retention:** `bitext_train_noisy` (`5233abffaf4c6dbf78c548f3af06cb14aa96f2063611d1b61eb4a6be59573261`) preserved `3` historical noisy overlaps per `prep.v4` lock.
