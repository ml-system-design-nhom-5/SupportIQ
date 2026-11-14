# Fit2 Final Attempt (2/2) Zero-Fit Prep & Implementation Audit (Worker A)

- **Date / UTC Timestamp:** `2026-11-14T17:15:10.390471+00:00` (local `2026-11-15`)
- **Role & Dispatch:** Worker A (`task_00923cbd1735`, `dispatch_id=ctx_c1ecc9692b1e`) on branch `minh`
- **Design Authorization Input:** Worker B conditional design `PASS` ([2026-11-14-fit2-final-attempt-proposal-review-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-final-attempt-proposal-review-b.md), `eea29ea16ae879e834dc1a05eae654dffdbcb777`)
- **Source & Test Commit (`prep_git_commit`):** `f90deedb23b760a129f3aeaaedc92ea0c5c6d286`
- **Prep Bundle Path:** `artifacts/models/candidates/run-records-fit2-orig-pre-classifier-head-v1-prep`
- **Planned Future Fit Run ID:** `fit2-orig-pre-classifier-head-v1`
- **Authorized Profile:** `option_a_pre_classifier_head_v1` (`trainable_scope = pre_classifier_and_classifier`, `feature_dropout_eval_mode = true`)
- **Fits Executed / Budget Status:** **`fits_executed = 0`** (`optimizer_invoked = false`, `calibrator_invoked = false`). Global budget in [training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json) remains **`1 / 2`** (`additional_attempts_started = 1`, `additional_attempt_limit = 2`); **Attempt 2/2 is NOT spent by this prep**.

---

## 1. Minimal Implementation Summary

Implemented strictly opt-in support for `option_a_pre_classifier_head_v1` (`trainable_scope = "pre_classifier_and_classifier"`) while leaving all legacy profiles (`option_a`, `lr5e6`, `option_a_teacher_kl`, `option_a_teacher_kl_deterministic`, `option_a_classifier_head_only_v1`) and default `DEFAULT_PREP_PROFILE = "lr5e6"` unchanged and historically reproducible:

1. [train_boundary_candidate.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py):
   - Added `HEAD_ONLY_SCOPES = ("classifier_head_only", "pre_classifier_and_classifier")` and `VALID_TRAINABLE_SCOPES = ("all",) + HEAD_ONLY_SCOPES` with `_SCOPE_TRAINABLE_PARAM_NAMES`.
   - Extended `_configure_trainable_scope` to unfreeze exact `["pre_classifier.weight", "pre_classifier.bias", "classifier.weight", "classifier.bias"]` (`625,966` params) and freeze all `100` `distilbert.*` tensors + `1` buffer (`66,362,880` params) with fail-closed count assertions.
   - Extended `_set_epoch_module_modes` to call `model.eval()`, set only `model.pre_classifier.train(True)` and `model.classifier.train(True)`, and fail closed if `model.dropout` or any `distilbert.*` module is `.training == True`.
   - Extended `run_fit_and_lock_candidate` for `HEAD_ONLY_SCOPES`: enforces `feature_dropout_eval_mode=True`, forbids teacher KL/custom anchor modes, uses `use_supcon = (fit_mode == "fit2_supcon_energy") and (trainable_scope == "all")` (inactive on frozen encoder), verifies single-group optimizer param count, captures pre/post `_snapshot_frozen_component_hashes`, and enforces non-`None` + strictly positive final-batch gradients and nonzero weight updates on all unfrozen tensors (`trainable_layer_update_verified`, `trainable_max_abs_delta`, `trainable_last_grad_abs_max`).
2. [run_orig_fit2_return_contrast_prep.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_prep.py):
   - Added locked `option_a_pre_classifier_head_v1` entry (`lr=5e-5, epochs=3, batch_size=32, seed=42, weight_decay=0.01, fit_mode="fit2_supcon_energy", min_temperature=1.0, enable_selective_rejector=False, init_weights_sha256=f695b1fe..., trainable_scope="pre_classifier_and_classifier", feature_dropout_eval_mode=True, expected_trainable_param_count=625966, expected_frozen_param_count=66362880`).
   - Added shared `SUBHEAD_PROFILE_MANIFEST_KEYS`, `SUBHEAD_FIT_PROFILES`, and `validate_subhead_config_block`; formatted `5e-5` in `_format_lr_cli`; preserved `classifier_head_only_config` for Attempt 1 and stored `subhead_scope_config` + `budget_attempt_label = "Attempt_2_of_2_final_pending_coordinator_release"` for `option_a_pre_classifier_head_v1`.
3. [run_orig_fit2_return_contrast_fit.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py):
   - Shared `VALID_TRAINABLE_SCOPES`, `SUBHEAD_FIT_PROFILES`, `SUBHEAD_PROFILE_MANIFEST_KEYS`, and `validate_subhead_config_block` across `validate_profile_settings`, `verify_locked_prep_bundle`, `run_authorized_fit`, and CLI `--trainable-scope` `choices=VALID_TRAINABLE_SCOPES`.
4. [test_orig_fit2_return_contrast_prep.py](file:///F:/Năm%203/SD/project/SupportIQ/tests/unit/test_orig_fit2_return_contrast_prep.py):
   - Added focused unit tests covering `625,966` / `66,362,880` counts, `100` frozen tensors + `1` buffer hash invariance, optimizer `4`-tensor list (`lr=5e-5, wd=0.01`), synthetic autograd gradients on BOTH `pre_classifier.*` and `classifier.*` (`p.grad is None` on frozen encoder, zero optimizer updates), `SupCon` exact `0.0` gradient equivalence, deterministic dropout-eval RNG preservation, intact `ReLU` gating (not flattened), wrong-profile/wrong-kwargs negative guards, legacy profile isolation, and mocked `--validate-only` + archival kwargs forwarding.

---

## 2. Prep Bundle Provenance, SHAs, & Freeze Snapshots (`0` Fits Executed)

### Source Hashes (`prep_manifest.json`, `git_commit = f90deedb23b760a129f3aeaaedc92ea0c5c6d286`)
- `pipeline/training/train_boundary_candidate.py`: `b352907be736bbb530143cda8ebbe16854c7360d430b6381c95dddfc280faf5f`
- `scripts/run_orig_fit2_return_contrast_prep.py`: `628b902f5fc154e1197125cb70760ed5c22ee99287e481d0520c3cb198d51e4e`
- `scripts/run_orig_fit2_return_contrast_fit.py`: `50c78be64f498d99dbe4cade073c1592195bf43e6968a3e61f017e4c8f8392e8`
- All `19` tracked relevant source files snapshotted in `source_snapshot/` with `0` mismatches.

### Prep Sidecar Inventory & Dataset Identity (`run-records-fit2-orig-pre-classifier-head-v1-prep`)
- `prep_manifest.json` SHA-256: `23b82dfe9a17d384fd85ad7f24d9a8c9cb61f2f05f7a95c4290e1cab6971d3dc`
- `sidecar_sha_inventory.json` SHA-256: `bd30fd69011d4bc59637a5e7555f1ab32c8b309385ab718b1dd8209882ae81eb` (**39 / 39 files verified, 0 mismatches**)
- `status.json`: `status="complete"`, `fits_executed=0`, `prep_archive=true`, `budget_attempt_label="Attempt_2_of_2_final_pending_coordinator_release"`, `budget_consumed_by_prep=0`
- Dataset identity vs Attempt 1 (`run-records-fit2-orig-classifier-head-only-v1-prep/datasets`): **All 15 dataset files match bit-for-bit except timestamp metadata in `dataset_lock_manifest.json`**:
  - `split_manifest.json`: `44eebb254c3b6d472dfda68d07c0d36efe5390113b04802890d5155033318387`
  - `full_train_split.jsonl`: `63254304c1ccd722a5fc40b23ee37ee239006f7e66b10a2d81371417190571d0` (`11,338` raw / `13,080` effective rows)
  - `full_cal_split.jsonl`: `dc8c7773db46a1bbebcdf67b83c640b9635a4724f0c262dd9fa61ede3c139672` (`824` rows)
  - `orig_fit2_return_contrast_extension.jsonl`: `f87c6185362a358f03a1a7515778abaad5a6dd911462aca88287781acffbec3e` (`18` added TRAIN rows)
  - `bitext_train_clean.jsonl`: `36f6e74f7dd009459e0a79710197dc44437ca5539d3b5a46b1e014f5b3bafea0`
  - `bitext_train_noisy.jsonl`: `5233abffaf4c6dbf78c548f3af06cb14aa96f2063611d1b61eb4a6be59573261`
  - `bitext_cal.jsonl`: `54e9e86ae6ae076a9245fb5d3af60d1ce28c345fe492200824fe26078a83a3a9`
  - `bitext_test_6690.jsonl`: `c2279c30a6e7a9fde7488ea78d80a05fa560eb4ea9c02c746ffd87f6767c50b8`
  - `dataset_lock_manifest.json`: `8755a8e74c11372898d0b29a20330645cf23a420c1925cf26d9f0cf13d775080`

### Initial Freeze & Untouched Checkpoint Snapshots
- **Student Init (`reconstructed-fit2-supcon-20261113/model.safetensors`):** `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (NOT Attempt 1 weights `c0908ffb...`)
- **Active Serving (`trained/distilbert-supportiq/model.safetensors`):** `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`
- **`initial_frozen_tensors_sha256` (`100` frozen params + `1` buffer, `66,362,880` params):** `d16052a208919dfd2fa09f8bb4330ddbc37fab58fa7c8573dd31a686083a0151`
  - `distilbert.embeddings`: `9662676024c6a6cb5fca578d3466f5e9c43ca91d39c98e396ffb900532c07262`
  - `distilbert.transformer.layer.0`: `4cdcd10c2469d3de420d0bb25ead6008096a4206b0f1d748613cd8d782b1bcee`
  - `distilbert.transformer.layer.1`: `a0d27f1fc52822d252b8c4146254806665eea459a8d02a428a6090d74849301a`
  - `distilbert.transformer.layer.2`: `febe747d5591c061c230d432e43077d3c63ac91c2742ef5aadb14c16715a9c61`
  - `distilbert.transformer.layer.3`: `e3d9604616019ddce3b6acd5146c3b1820ef5b21bae592601224006ef8afcc68`
  - `distilbert.transformer.layer.4`: `a72929efd64a023781ae687d245529d1ff264526a63066705c3735df681537d4`
  - `distilbert.transformer.layer.5`: `0df9904d111f7f430858ccba2dfa5339c49a6747b24dc77bd578994219b1fc1a`
  - `buffers` (`distilbert.embeddings.position_ids`): `26ef7d8b98537c99d82b8d135adab799031872d26387aa5545315a0d87e4c57f`
- **Trainable tensors (`4` tensors, `625,966` params):** `["pre_classifier.weight", "pre_classifier.bias", "classifier.weight", "classifier.bias"]`.

---

## 3. Focused Tests & Planned Future Execution Command

- **Unit Tests:** `.venv/Scripts/python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py tests/unit/test_boundary_contrast_fit.py -q` -> **`47 passed, 1 deselected`** in `257.73s` (`0` real fits, `0` real optimizer steps).
- **Exact Future CLI (DO NOT EXECUTE until Worker B review `PASS` + explicit coordinator release):**
  ```powershell
  .\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-pre-classifier-head-v1-prep" --run-id fit2-orig-pre-classifier-head-v1 --profile option_a_pre_classifier_head_v1 --epochs 3 --lr 5e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --weight-decay 0.01 --trainable-scope pre_classifier_and_classifier --feature-dropout-eval-mode --run-authorized-fit
  ```
- **Target Pre-Fit Output Paths (verified currently ABSENT):**
  - `artifacts/models/candidates/fit2-orig-pre-classifier-head-v1`
  - `artifacts/models/candidates/run-records-fit2-orig-pre-classifier-head-v1`
  - `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-pre-classifier-head-v1`

---

## 4. Disclosure of Limits & Final Attempt Protocol

1. **Multi-factor confound (`n = 1`):** Simultaneously changes trainable capacity (`classifier` -> `pre_classifier + classifier`), `lr` (`1e-4` -> `5e-5`), and `epochs` (`2` -> `3`) at `seed = 42`.
2. **Feature-geometry risk:** Read-only probes on `f695b1fe` `h_cls` features found `0 / 8` added `return_product_in_store` rows nearest-neighbor-match canonical `return_product_in_store`; CAL pass is uncertain and not promised.
3. **3 historical noisy overlaps preserved:** `bitext_train_noisy` retains the `3` historical normalized-text overlaps against `bitext_test_6690` (`exclude_noisy_test_overlap = false`).
4. **Hard Final Attempt Rule (`Attempt 2/2`):** Any future optimizer start increments `.local/training-cap-20261114.json` to `2 / 2` before `optimizer.step()`. Any crash/partial attempt consumes the final attempt; if `cal_guard_passed == false` (`< 12 / 12`), trigger **permanent Fit2 STOP** (`CAL_GUARD_REJECT_DO_NOT_PROMOTE`, zero Attempt 3, zero retries). Only if CAL passes `12 / 12` will C-gate / holdouts run.
