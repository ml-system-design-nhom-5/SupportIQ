# Original Fit2 Masked Teacher-KL Implementation & Zero-Fit Prep Audit (Worker A)

- **Date:** 2026-11-14
- **Role / Dispatch:** Worker A (`task_156bad5e3a95`, branch `minh`)
- **Predecessor Proposal Review:** [2026-11-14-fit2-teacher-kl-proposal-review-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-teacher-kl-proposal-review-b.md) (`PASS`)
- **Frozen Source & Test Commit:** `6b7a0c4c020fa9565b9e11ce4864c05f8895f3d5`
- **Training Executed (`fits_executed`):** `0` (strictly zero-fit implementation + prep archive; awaiting Worker B review PASS and coordinator release)

## 1. Implementation Scope

Implemented opt-in profile `option_a_teacher_kl` across three tracked source files and five unit tests without altering base profiles (`option_a`, `lr5e6`, `zero_delta_control`, `DEFAULT_PREP_PROFILE = "lr5e6"`):

1. [train_boundary_candidate.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py)
   - Extended `_BoundaryDataset` with optional `teacher_anchor_mask`.
   - Added `build_teacher_anchor_mask` reading `orig_fit2_return_contrast_extension.jsonl` (`orig_ret_ch_*` `sample_id`s), masking out (`m_i = 0`) the locked extension rows in `pos_train` and masking in (`m_i = 1`) canonical `pos_train`, `bitext_clean + bitext_noisy`, and `neg_train`; fails closed on empty/missing extension provenance, missing IDs, or leakage into `bitext`/`neg_train`.
   - Added `compute_masked_teacher_kl_loss` implementing batch-masked `KL(p_teacher || p_student)` over `sum(m_i)` (returning finite `0.0` when `sum(m_i) == 0`).
   - Added `_load_and_verify_frozen_teacher` enforcing `eval()`, `requires_grad_(False)`, exact teacher weights SHA-256 verification, 46-label `id2label` bijection, and `tokenizer.json` hash match against `init_model_dir`.
   - Extended `run_fit_and_lock_candidate` with opt-in `teacher_kl_weight` (default `0.0`, disabled), `teacher_temperature` (default `1.0`), `teacher_model_dir`, and `expected_teacher_weights_sha256`; logs `avg_teacher_kl_loss`, `weighted_teacher_kl_loss`, `anchor_rows_seen`, and `excluded_rows_seen` per epoch, verifies teacher `model.safetensors` SHA-256 unchanged post-loop, never trains/calibrates/saves the teacher checkpoint, and records teacher provenance in `candidate_provenance_manifest.json` (`training_lineage`).
2. [run_orig_fit2_return_contrast_prep.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_prep.py)
   - Added `"option_a_teacher_kl"` to `AUTHORIZED_FIT_PROFILES`: `lr=2e-5`, `epochs=3`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`, `init_weights_sha256=f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `teacher_weights_sha256=f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `teacher_kl_weight=1.0`, `teacher_temperature=1.0`.
   - Preserved `CAL_GUARD_DEFINITION` (`12` checks including `pos_train_added_18 >= 15`), `UNCHANGED_ORIGINAL_RECIPE_PARAMETERS`, `DEFAULT_PREP_PROFILE = "lr5e6"`, and `is_promotion_candidate=True`.
   - Archived `teacher_anchor_config` and explicit `--teacher-kl-weight 1.0 --teacher-temperature 1.0 --teacher-weights-sha256 ... --run-authorized-fit` into `prep_manifest.json` when `--profile option_a_teacher_kl`.
3. [run_orig_fit2_return_contrast_fit.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py)
   - Added `--teacher-kl-weight`, `--teacher-temperature`, and `--teacher-weights-sha256`.
   - Enforced fail-closed validation: `option_a_teacher_kl` requires exact `1.0`, `1.0`, and `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, forbids combining with `zero_delta_control`, and rejects mismatched `prep_manifest.json` / `teacher_anchor_config`. Base profiles `option_a` and `lr5e6` forbid non-zero `teacher_kl_weight`, non-`1.0` `teacher_temperature`, or `teacher_weights_sha256`.
   - Output subdirectory resolves to `candidate_model_option_a_teacher_kl`; persists `teacher_anchor_config` in `run_config.json`, verifies post-fit teacher SHA and `training_lineage`, and runs the 12-check CAL guard (`output` planned at `fit2-orig-teacher-kl-v1`).
4. [test_orig_fit2_return_contrast_prep.py](file:///F:/Năm%203/SD/project/SupportIQ/tests/unit/test_orig_fit2_return_contrast_prep.py)
   - Added the 5 Worker B unit tests covering: (1) identity `student == teacher` KL `< 1e-7` + zero-mask finite `0.0`, (2) teacher immutability (`grad is None`, bitwise tensor preservation, hash/tokenizer checks) + student weight update, (3) exact `13,000` active / `80` excluded mask + leak/missing fail-closed checks, (4) default profile isolation & CLI fail-closed guards, and (5) `option_a_teacher_kl` prep plan & runner forwarding closure.

## 2. Sealed Zero-Fit Prep Bundle & Dataset Parity

- **Prep Bundle Directory:** `artifacts/models/candidates/run-records-fit2-orig-teacher-kl-v1-prep`
- **Status:** `{"status": "complete", "fits_executed": 0, "prep_archive": true}`
- **Schema / Mode:** `orig_fit2_return_contrast_prep.v4` (`return_contrast`, `is_promotion_candidate: true`)
- **Planned Future Fit Run ID:** `fit2-orig-teacher-kl-v1` (not yet executed)
- **`prep_manifest.json` SHA-256:** `3234e31bea47402b4d6ef2da1ceb0fe3434e470c707c848dbc538918b2049286`
- **`sidecar_sha_inventory.json` SHA-256:** `3eece60d243a68b1bb7c12f9bd2012c6b7ab4fdfe4c54defc4b47532d3e56233`
- **Starting Student & Frozen Teacher Checkpoint:** Original Fit2 (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113`), `model.safetensors` SHA-256 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`
- **Serving Checkpoint Unchanged:** `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`
- **Dataset Parity vs `run-records-fit2-orig-ret-channel-v4-prep/datasets`:**
  - Same `15` dataset files (`bitext_cal.jsonl`, `bitext_test_6690.jsonl`, `bitext_train_clean.jsonl`, `bitext_train_noisy.jsonl`, `boundary_neg_calibration.jsonl`, `boundary_neg_evaluation.jsonl`, `boundary_neg_train.jsonl`, `boundary_pos_calibration.jsonl`, `boundary_pos_evaluation.jsonl`, `boundary_pos_train.jsonl`, `dataset_lock_manifest.json`, `full_cal_split.jsonl`, `full_train_split.jsonl`, `orig_fit2_return_contrast_extension.jsonl`, `split_manifest.json`).
  - `14` data/split files are byte-for-byte identical; only `dataset_lock_manifest.json` differs (`b0a1ffa5...` vs `a07d1342...`) due to generation timestamp metadata.
- **Mask Coverage Verified on Archived Splits:** `canonical_pos=772` (`181` raw) + `bitext=11,040` + `neg=1,188` = `13,000` anchor rows (`m_i = 1`); `orig_ret_ch_* = 80` effective (`18` raw) excluded (`m_i = 0`); total `13,080` effective TRAIN rows.

## 3. Verification Evidence

- **Targeted Pytest Suite (ran on final source+test state `6b7a0c4c020fa9565b9e11ce4864c05f8895f3d5`):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py tests/unit/test_boundary_contrast_fit.py tests/unit/test_faithful_fit2_entrypoint.py tests/unit/test_gate_contract_b.py tests/unit/test_task_c_evaluation_gates.py tests/unit/test_model_provenance.py -v`
  - Result: `64 passed, 2 deselected` in `276.21s` (`pytest.ini` marker deselection).
- **Runner `--validate-only` (after archiving prep bundle & after final commit):**
  - Returns `"validated_only": true, "fits_executed": 0`, verifying prep `git_commit` (`6b7a0c4c...`) is an ancestor of `HEAD`, matching all `RELEVANT_SOURCE_PATHS` hashes, starting checkpoint SHA, Serving SHA, and `teacher_anchor_config`.
- **Fail-Closed Negative CLI Guards (all exited `1`):**
  - `wrongSHA` -> `ValueError: option_a_teacher_kl requires exact teacher_weights_sha256=f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`
  - `wrongcoef` (`0.5`) -> `ValueError: option_a_teacher_kl requires explicit teacher_kl_weight=1.0; got 0.5`
  - `wrongprofile` (`lr5e6` vs `option_a_teacher_kl` prep) -> `ValueError: Requested profile 'lr5e6' mismatches locked prep authorized_fit_profile 'option_a_teacher_kl'`
  - `collision` (duplicate `--archive-prep` on `fit2-orig-teacher-kl-v1`) -> `FileExistsError: MAIN prep records already exist`

## 4. Disclosed Limits & Caveats

- `alpha_kl = 1.0` (`teacher_kl_weight=1.0`, `teacher_temperature=1.0`) is an exploratory regularization choice under a single-run budget and has not been validated as optimal over alternate weights (`0.5`, `2.0`, etc.).
- Teacher-KL applies strictly on TRAIN replay anchors (`m_i = 1`); CAL and EVAL surfaces are never anchored to the teacher during training.
- Historical `bitext_train_noisy` vs eval 3-row exact-norm overlap (`exclude_noisy_test_overlap: false`) and single-factor Fit2 recipe settings (`UNCHANGED_ORIGINAL_RECIPE_PARAMETERS`) are preserved without bundling unrelated changes.
