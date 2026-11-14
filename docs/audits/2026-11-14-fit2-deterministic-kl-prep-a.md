# Fit2 Deterministic-Student KL Anchor Implementation & Zero-Fit Prep Archive (`fit2-orig-deterministic-kl-v1`)

- **Date:** 2026-11-14
- **Author:** Worker A (`task_id=task_92cb10b56748`, `dispatch_id=ctx_2fa4294e7239`)
- **Design Basis:** Worker B design PASS ([2026-11-14-fit2-deterministic-kl-proposal-review-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-deterministic-kl-proposal-review-b.md), base commit `07748ac47ad2423a47fbbb9580ed4b425c057c20`)
- **Execution Mode:** **IMPLEMENTATION + ZERO-FIT PREP ARCHIVE ONLY (`fits_executed: 0`)**
- **Frozen Source/Test Commit:** `e82ec7d6bd3bcf18fe6227837fe2c42845cab943` (branch `minh`)

## 1. Implementation Summary (Single-Delta Change)

To eliminate step-0 dropout variance in the canonical TRAIN `KL(p_teacher || p_student)` preservation anchor while keeping the base contrastive/domain loss identical to the stochastic training regime, an explicit opt-in anchor mode `eval_no_dropout_autograd_enabled` and profile `option_a_teacher_kl_deterministic` were added:

1. **`pipeline/training/train_boundary_candidate.py`** (SHA-256 `7f160e637edc3c98b5762d938fe2dd2e38a0b2545f937d1bd6b999ffb32a2c9b`):
   - Added `VALID_TEACHER_STUDENT_ANCHOR_MODES = ("train_stochastic", "eval_no_dropout_autograd_enabled")`.
   - Added `_forward_student_logits_eval_mode(model, input_ids, attention_mask)`, which snapshots all nested `module.training` flags, sets `model.eval()` with autograd enabled (`output_hidden_states=False`, logits only), and restores every module's `training` flag in a `finally:` block even on exception.
   - Base `pos_ce + 0.25 * supcon + neg_loss` remains strictly on the original stochastic `model.train()` forward (`out`).
   - Only when `teacher_student_anchor_mode == "eval_no_dropout_autograd_enabled"` and batch `active_count > 0` does `run_fit_and_lock_candidate` evaluate `KL(p_teacher || p_student)` via `_forward_student_logits_eval_mode` (when `active_count == 0`, the extra student forward and teacher forward are skipped cleanly).
   - Recorded `"teacher_student_anchor_mode"` in candidate lineage.

2. **`scripts/run_orig_fit2_return_contrast_prep.py`** (SHA-256 `d0822e334e5a08789ed491d78d8002793f9807ebcb0bcb641b7b9906e44f96d1`):
   - Added `"option_a_teacher_kl_deterministic"` to `AUTHORIZED_FIT_PROFILES`.
   - Kept `DEFAULT_PREP_PROFILE = "lr5e6"` and all historical profiles (`"option_a_teacher_kl"`, `"option_a"`, `"lr5e6"`, `"zero_delta_control"`) unchanged.
   - Updated `_build_planned_execution_plan` and `_archive_orig_fit2_prep_bundle` to emit `--teacher-student-anchor-mode eval_no_dropout_autograd_enabled` and `teacher_anchor_config.teacher_student_anchor_mode`.

3. **`scripts/run_orig_fit2_return_contrast_fit.py`** (SHA-256 `cc8a89dd2b07416524dbb9f2e47f00b58b0f8c32617bb7c5119417b4330c4fb6`):
   - Added `--teacher-student-anchor-mode` CLI flag and fail-closed validation against requested `--profile`, archived `prep_manifest.json`, and model lineage.
   - Enforced mutual isolation: `"option_a_teacher_kl_deterministic"` requires `teacher_student_anchor_mode="eval_no_dropout_autograd_enabled"`, whereas `"option_a_teacher_kl"`, `"option_a"`, and `"lr5e6"` forbid non-stochastic anchor modes.

4. **`tests/unit/test_orig_fit2_return_contrast_prep.py`**:
   - Added `_make_synthetic_dropout_classifier` and the 5 Worker B specification tests:
     - `test_deterministic_kl_init_identity_zero_and_zero_anchor_grad_vs_stochastic_dropout`
     - `test_deterministic_kl_perturbed_student_positive_and_gradient_toward_teacher`
     - `test_deterministic_kl_mask_all_added_empty_zero_and_canonical_exclusion`
     - `test_deterministic_kl_base_forward_rng_modes_unchanged_and_exception_restore`
     - `test_deterministic_kl_no_grad_only_teacher_and_profile_archive_forward_flags`

## 2. Archived Zero-Fit Prep Bundle & Integrity Verification

- **Prep Bundle Path:** `artifacts/models/candidates/run-records-fit2-orig-deterministic-kl-v1-prep`
- **Target Future Run ID:** `fit2-orig-deterministic-kl-v1`
- **`status.json`:** `{"status": "complete", "fits_executed": 0, "prep_archive": true}`
- **`prep_manifest.json`:**
  - `schema_version`: `orig_fit2_return_contrast_prep.v4`
  - `git_commit`: `e82ec7d6bd3bcf18fe6227837fe2c42845cab943`
  - SHA-256: `a2b1983dcaa328423b182ec9ebcaeb969ee5e74330fd13394f01af68426d6fb6`
- **`sidecar_sha_inventory.json`:**
  - SHA-256: `773c354f760e234cc3c6569a4e8203465bc9da31b34638b165394e66b1943515`
  - Entries verified: `39` sidecar files, `0` mismatches
- **Dataset Parity vs `run-records-fit2-orig-ret-channel-v4-prep/datasets`:**
  - `15` dataset files total; `14/14` data/split/extension files are byte-identical.
  - Only `dataset_lock_manifest.json` differs (`8b2d68059a1cba9db04d6cd431ed8a5f2b97937d3dd9503fe3369217fc91fe01` vs `a07d1342a40298b76959d431a12ea967deb3add8d18408343a5e5c78682bd074`).
- **Locked Dataset & Anchor Configuration:**
  - `canonical_prep.cleaned_sha256`: `8BC10CFA056371BDECB3394BFD4C75EEE7E10022ACE5071833ECD140B2D75846`
  - `canonical_prep.splits_sha256`: `1D366E898F6BA68BE46C5CA0F9059E9862FAD1D7BAFE350D9CDD310DD3E0A04C`
  - Row counts: `domain_pos_train = 199`, `extension_pos_train_added = 18`, `full_train_split_rows = 11338`
  - Teacher & Student Init: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (frozen teacher in `.eval()` + `torch.no_grad()`)
  - Anchor params: `teacher_kl_weight = 1.0`, `teacher_temperature = 1.0`, `teacher_student_anchor_mode = "eval_no_dropout_autograd_enabled"`
  - Anchor mask counts: `anchor_effective_count = 13000` (`m=1` canonical replay), `excluded_effective_count = 80` (`18` raw `orig_ret_ch_*` added rows, `m=0`)
  - Training hyperparams: `epochs=3`, `lr=2e-5`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`
  - `12` CAL guard checks and all historical runs/artifacts (`fit2-orig-teacher-kl-v1`, `f695b1fe`, etc.) remain unchanged and untouched.
- **No Future Fit Artifacts Created:** Verified non-existence of candidate dir `fit2-orig-deterministic-kl-v1`, `run-records-fit2-orig-deterministic-kl-v1`, and `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-deterministic-kl-v1`.

## 3. Verification Executed (Zero Real Fits)

1. **Targeted Unit Test Suite (on frozen code at `e82ec7d6bd3bcf18fe6227837fe2c42845cab943`):**
   - Command:
     ```powershell
     .\.venv\Scripts\python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py tests/unit/test_boundary_contrast_fit.py tests/unit/test_faithful_fit2_entrypoint.py tests/unit/test_gate_contract_b.py tests/unit/test_task_c_evaluation_gates.py tests/unit/test_model_provenance.py -v
     ```
   - Result: `69 passed, 2 deselected in 276.72s` (exit code `0`).

2. **Fail-Closed Negative CLI & Prep Collision Guards:**
   - `missingMode` (deterministic profile without `--teacher-student-anchor-mode`): exit code `1` (`ValueError: option_a_teacher_kl_deterministic requires explicit teacher_student_anchor_mode='eval_no_dropout_autograd_enabled'; got None`)
   - `wrongMode` (`train_stochastic` on deterministic profile): exit code `1` (`ValueError: option_a_teacher_kl_deterministic requires explicit teacher_student_anchor_mode='eval_no_dropout_autograd_enabled'; got 'train_stochastic'`)
   - `stochWithDetFlag` (`eval_no_dropout_autograd_enabled` on `option_a_teacher_kl`): exit code `1` (`ValueError: option_a_teacher_kl forbids non-stochastic teacher_student_anchor_mode; got 'eval_no_dropout_autograd_enabled'`)
   - `wrongProfile` (`option_a_teacher_kl` against deterministic prep): exit code `1` (`ValueError: Requested profile 'option_a_teacher_kl' mismatches locked prep authorized_fit_profile 'option_a_teacher_kl_deterministic'`)
   - `collision` (re-archiving `fit2-orig-deterministic-kl-v1-prep`): exit code `1` (`FileExistsError: MAIN prep records already exist: F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-deterministic-kl-v1-prep`)

## 4. Exact Quoted Future Fit CLI (NOT EXECUTED)

Recorded verbatim in `prep_manifest.json` (`planned_cli`) for use only after design/prep review and explicit coordinator release:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-deterministic-kl-v1-prep" --run-id fit2-orig-deterministic-kl-v1 --profile option_a_teacher_kl_deterministic --epochs 3 --lr 2e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --teacher-kl-weight 1.0 --teacher-temperature 1.0 --teacher-weights-sha256 f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa --teacher-student-anchor-mode eval_no_dropout_autograd_enabled --run-authorized-fit
```

## 5. Remaining Limits & Open Risks

- **Step Compute Overhead:** Moving the student KL anchor to a separate eval-mode forward with autograd changes per-step forward passes from 2 (stochastic student + no-grad teacher) to ~3 (stochastic base forward + eval-mode student KL forward + no-grad teacher forward), within the Worker B measured `1,786.9 MB / 8,150.6 MB` VRAM envelope.
- **No Guarantee of CAL Pass:** As noted in Worker B's review, deterministic eval-mode KL eliminates step-0 dropout variance (`2.18e-9` KL / `4.73e-7` grad vs stochastic `0.003861` / `0.163320`), but weak canonical TRAIN KL on drifted checkpoints (`0.001241` / `0.001548` at `904188aa` / `dc3e`) means eliminating step-0 noise alone does not guarantee CAL gate pass on the future run.
- **Exploratory Scope:** `alpha_kl = 1.0`, `seed = 42` (`n = 1`).
- **Historical Noisy Overlap Disclosure:** `exclude_noisy_test_overlap: false` preserves `3` `bitext_train_noisy` vs eval exact-norm overlaps unmodified to match the prior baseline family.
