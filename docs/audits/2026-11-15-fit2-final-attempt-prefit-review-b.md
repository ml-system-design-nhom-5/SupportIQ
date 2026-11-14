# Fit2 Final Attempt (2/2) Actual Pre-Fit Review (Worker B)

- **Date (UTC):** `2026-11-14T17:24:00Z` | **Branch:** `minh` | **Audited Commits:** source `f90deedb23b760a129f3aeaaedc92ea0c5c6d286`, prep audit `d67ac674b4afe5f4107f600c5dee8a7477682010`
- **Role / Task:** Worker B (`task_9b54d7daf29a`, `dispatch_id=ctx_cbe737a07d1b`)
- **Design Reference:** [2026-11-14-fit2-final-attempt-proposal-review-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-final-attempt-proposal-review-b.md) (`eea29ea16ae879e834dc1a05eae654dffdbcb777`)
- **Prep Audit Reviewed:** [2026-11-15-fit2-final-attempt-prep-a.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-15-fit2-final-attempt-prep-a.md) (`d67ac674b4afe5f4107f600c5dee8a7477682010`)
- **Verdict:** **`PASS` — AUTHORIZED FOR COORDINATOR RELEASE OF FINAL ATTEMPT (`2 / 2`) ONLY**
- **Budget & Fit Constraint:** Global cap in [training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json) remains **`1 / 2`** (`additional_attempts_started = 1`, `additional_attempt_limit = 2`, `training_stopped = false`). `0` real fits, `0` optimizer steps, `0` calibrator runs, and `0` holdouts executed. Coordinator release is required before executing any fit.

---

## 1. Independent Verification Evidence

| Check | Result | Observed Evidence |
|---|---|---|
| **Prep Manifest & Sidecar** | **PASS** | `run-records-fit2-orig-pre-classifier-head-v1-prep`: `prep_manifest.json` SHA `23b82dfe9a17d384fd85ad7f24d9a8c9cb61f2f05f7a95c4290e1cab6971d3dc`, `sidecar_sha_inventory.json` SHA `bd30fd69011d4bc59637a5e7555f1ab32c8b309385ab718b1dd8209882ae81eb` (**`39 / 39` files verified, `0` mismatches**); `status.json`: `status="complete"`, `fits_executed=0`, `budget_consumed_by_prep=0`. |
| **Source Closure (`19/19`)** | **PASS** | All `19` `RELEVANT_SOURCE_PATHS` in `source_snapshot/` match live repo SHA-256 (`train_boundary_candidate.py`: `b352907b...`, `run_orig_fit2_return_contrast_prep.py`: `628b902f...`, `run_orig_fit2_return_contrast_fit.py`: `50c78be6...`). No tracked code changes in `f90deed` lie outside `RELEVANT_SOURCE_PATHS` + `test_orig_fit2_return_contrast_prep.py`. |
| **Dataset Identity (`15/15`)** | **PASS** | `14 / 15` files in `datasets/` match Attempt 1 (`run-records-fit2-orig-classifier-head-only-v1-prep/datasets`) bit-for-bit; `dataset_lock_manifest.json` differs solely in `"locked_at"` (`16:14:14Z` vs `17:14:41Z`). Accepted `+18` (`f87c6185...`), `bitext_train_noisy` (`5233abff...`), `split_manifest.json` (`44eebb25...`), and `CAL` (`dc8c7773...`) preserved. |
| **Init & Serving Anchors** | **PASS** | Student init untouched `reconstructed-fit2-supcon-20261113/model.safetensors`: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (NOT rejected `c0908ffb...`). Active serving untouched: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`. |
| **Freeze Snapshot & Counts** | **PASS** | Independent `_configure_trainable_scope` + `_snapshot_frozen_component_hashes` on `f695b1fe`: `100` frozen tensors + `1` buffer (`66,362,880` params) match `d16052a208919dfd2fa09f8bb4330ddbc37fab58fa7c8573dd31a686083a0151` (`embeddings`, `layer.0..5`, `buffers`); `4` trainable tensors (`625,966` params: `pre_classifier.{weight,bias}`, `classifier.{weight,bias}`). |
| **Future Outputs Absent** | **PASS** | Verified absent: `artifacts/models/candidates/fit2-orig-pre-classifier-head-v1`, `artifacts/models/candidates/run-records-fit2-orig-pre-classifier-head-v1`, `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-pre-classifier-head-v1`. |
| **Focused Unit & Regression Tests** | **PASS** | Ran `.venv\Scripts\python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py -k "pre_classifier or head_only" -q` -> **`8 passed, 22 deselected in 11.66s`** (`0` real fits); Worker A additionally reported `47 passed, 1 deselected` across `test_orig_fit2_return_contrast_prep.py` + `test_boundary_contrast_fit.py`. |
| **`--validate-only` (Pre & Post Doc Commit)** | **PASS** | Pre-commit (`head_git_commit=d67ac674b4afe5f4107f600c5dee8a7477682010`) and post-doc-commit `validate-only` both pass with `fits_executed=0`, `prep_git_commit=f90deedb23b760a129f3aeaaedc92ea0c5c6d286` ancestor-verified. |

---

## 2. Code, Guard, & Compatibility Verification

1. **Optimizer, Autograd, & Module Mode Isolation ([train_boundary_candidate.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L775-L930)):**
   - `HEAD_ONLY_SCOPES = ("classifier_head_only", "pre_classifier_and_classifier")` unfreezes exact `4` tensors (`625,966` params) via `_configure_trainable_scope`; `optimizer = AdamW(opt_params, lr=5e-5, weight_decay=0.01)` asserts single param group of length `4` (`L1455-L1464`).
   - `_set_epoch_module_modes` calls `model.eval()` and sets `.train(True)` strictly on `model.pre_classifier` and `model.classifier`, raising `RuntimeError` if `model.dropout` or any `distilbert.*` module is `.training == True` (no recursive `model.train()` override anywhere in epoch loop). Synthetic unit tests confirm `p.grad` nonzero on both layers, `ReLU` gating active, `p.grad is None` on all `100` frozen tensors, deterministic `0.0` repeat forward diff with CPU/NumPy/Python RNG preserved, `SupCon` inactive (`use_supcon = (fit_mode == "fit2_supcon_energy") and (trainable_scope == "all")`, `0.0` grad equivalence), and post-fit fail-closed checks on both frozen tensor/buffer SHA-256 and `trainable_layer_update_verified` (`trainable_max_abs_delta > 0`, `trainable_last_grad_abs_max > 0`).
   - Minor non-blocking note: `train_boundary_candidate.py#L1843` omits `post_fit_frozen_tensors_sha256` from the top-level `fit_result` return dict outside `classifier_head_only`, while `candidate_provenance_manifest.json` (`L1775-L1794`) and `run_orig_fit2_return_contrast_fit.py#L753-L771` enforce and archive both freeze hashes and trainable-update verification for all `HEAD_ONLY_SCOPES`.
2. **Fail-Closed Profile, CLI, Provenance, & Runtime Parity ([run_orig_fit2_return_contrast_prep.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_prep.py#L137-L163), [run_orig_fit2_return_contrast_fit.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py#L140-L160)):**
   - `option_a_pre_classifier_head_v1` enforces exact `lr=5e-5`, `epochs=3`, `weight_decay=0.01`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `trainable_scope="pre_classifier_and_classifier"`, `feature_dropout_eval_mode=True`, `min_temperature=1.0`, `enable_selective_rejector=False`, and forbids KL/anchor/wrong-profile combinations via `validate_profile_settings`, `verify_locked_prep_bundle`, and `validate_subhead_config_block`. Legacy profiles (`option_a`, `lr5e6`, `option_a_teacher_kl*`, `option_a_classifier_head_only_v1`) remain untouched.
   - All `12` CAL guard checks remain unchanged in `evaluate_cal_guard_report`; [ModelContainer](file:///F:/Năm%203/SD/project/SupportIQ/apps/ml_inference/app.py#L98-L310), `validate_calibration_manifest`, and `audit_candidate_provenance` validate standard DistilBERT `46`-label checkpoints + `selective_calibration.v1` / `candidate_provenance.v1` hashes with zero scope-name coupling.

---

## 3. Exact Future Execution Command (ONLY After Coordinator Release)

```powershell
.\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-pre-classifier-head-v1-prep" --run-id fit2-orig-pre-classifier-head-v1 --profile option_a_pre_classifier_head_v1 --epochs 3 --lr 5e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --weight-decay 0.01 --trainable-scope pre_classifier_and_classifier --feature-dropout-eval-mode --run-authorized-fit
```

---

## 4. Explicit Methodological Limits & Permanent Stop Rule (`Attempt 2 / 2`)

1. **`0 / 8` `h_cls` geometry risk:** Read-only inspection on `f695b1fe` raw `h_cls` showed `0 / 8` added `return_product_in_store` rows nearest-neighbor-match canonical `return_product_in_store` (`cos = -0.0427`, `max_cos_to_neg_cal = 0.8639`).
2. **Multi-factor `n = 1` confound:** Simultaneously alters unfrozen architecture (`classifier` $\rightarrow$ `pre_classifier + classifier`), `lr` (`1e-4` $\rightarrow$ `5e-5`), and `epochs` (`2` $\rightarrow$ `3`) at `seed = 42`.
3. **3 historical noisy overlaps preserved:** `exclude_noisy_test_overlap = false` retained identically across Fit2 inputs (`bitext_train_noisy` `5233abff...`).
4. **Hard terminal stop:** Increment [training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json) to `2 / 2` before `optimizer.step()`. Any crash/abort or `CAL < 12 / 12` on `fit2-orig-pre-classifier-head-v1` triggers **permanent Fit2 STOP** (`no Attempt 3`, `no retries`); holdouts run only if CAL passes `12 / 12`.
