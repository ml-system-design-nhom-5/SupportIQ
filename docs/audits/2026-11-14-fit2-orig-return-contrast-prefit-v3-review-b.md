# Worker B Targeted Pre-Fit Re-Review: Original Fit 2 Return-Channel Contrast (`v3-prep`)

- **Reviewed A commit:** `67b8730fab2e856f44b73ef9e016c4b12fa6989f` (`minh`)
- **Locked prep bundle:** `artifacts/models/candidates/run-records-fit2-orig-ret-channel-v3-prep`
- **Verdict:** **PASS** (authorized to release **one** Option A fit `fit2-orig-ret-channel-fit-v1` only — **not** production/serving acceptance)

## 1. Prior `HEAD` Self-Lock Fix & Provenance Checks

- **Ancestor + Source-Hash Validation:** [run_orig_fit2_return_contrast_fit.py#L163-L189](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py#L163-L189) and [run_orig_fit2_return_contrast_prep.py#L100-L150](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_prep.py#L100-L150) replace strict `HEAD == manifest["git_commit"]` equality with `verify_git_commit_ancestor` (`git merge-base --is-ancestor`), `git status --porcelain --untracked-files=all` across the `19`-file `RELEVANT_SOURCE_PATHS` closure, frozen `source_snapshot/` SHA verification, and exact `source_hashes` equality.
- **Unrelated descendant commits & fail-closed matrix:** Verified by code inspection and [test_orig_fit2_return_contrast_prep.py#L407-L567](file:///F:/Năm%203/SD/project/SupportIQ/tests/unit/test_orig_fit2_return_contrast_prep.py#L407-L567):
  - Doc-only / unrelated descendant commit (`HEAD != prep git_commit`) passes while all `19` tracked dependency-closure files match `source_hashes`.
  - Any committed change, uncommitted edit, or untracked path matching `RELEVANT_SOURCE_PATHS` fails closed (`--untracked-files=all` / `source_hashes != expected_source_hashes`).
  - Malformed, missing, or non-ancestor `git_commit` fails closed (`verify_git_commit_ancestor`).
  - Sidecar SHA inventory mismatch, missing/extra path (including path escapes vs `relative_to`), or tampered `source_snapshot/` / `datasets/` file fails closed (`verify_locked_prep_bundle`), and output path collisions fail closed (`_check_output_paths_unused`).
  - `execute_fit=True` exception path writes `status.json` with `status="incomplete"` and `fits_completed=0`.

## 2. Archive Integrity, Option A Settings & Disclosures

- **`v3-prep` SHA Verification:**
  - `prep_manifest.json` SHA-256: `24094bc72fade9493eceb37c93a6acecd0d00e34545f95bd70d3811be9bd60b6` (matches expected).
  - `sidecar_sha_inventory.json` SHA-256: `376b55c16c15170d7633c4b5f9a5c835fefe1e0dd8531fbdcdfa4ca25a2c9ee2` (`39/39` files present, `0` missing/extra, `0` SHA mismatches).
  - `source_snapshot/` (`19/19` files) matches `prep_manifest.json["source_hashes"]` and current repo `HEAD` with `0` diffs.
- **`v1-prep` & `v2-prep` Preserved Untouched:**
  - `v1-prep`: `prep_manifest.json` `e844861d15962c4aade3f1d029ade201b507136e74220824a65af5d0aa4d01f6`, `sidecar_sha_inventory.json` `51da2f176efda8609d9ddf2b265680c44913d8e66bb698f96c83382f6d909003` (`33/33`, `0` mismatches).
  - `v2-prep`: `prep_manifest.json` `f24fb814c5ce7fa9cbcdd665c431c4cf8fb3319570e64244f1c28600d918d961`, `sidecar_sha_inventory.json` `7beff9d1c29dc2edaa8a36f1e282f39516748f978b81a51504d8aa545fda0a9f` (`34/34`, `0` mismatches).
- **Datasets Bit-Identical to `v2-prep`:** `14/15` files under `v3-prep/datasets/` are byte-for-byte identical to `v2-prep/datasets/`; `dataset_lock_manifest.json` differs solely in `locked_at` timestamp (`11:02:28` vs `11:21:31`).
- **Option A Guard & Unused Namespace:** `--validate-only` executed `0` fits (`validated_only: true`, `fits_executed: 0`, no optimizer), locked `epochs=3`, `lr=2e-05`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=false`, `starting_checkpoint` (`f695b1fe...`, `T=1.0`, `rejector_enabled=false`, `num_labels=46`), `serving_weights_sha256` (`dc7af8cf...`), and clean unused targets for `fit2-orig-ret-channel-fit-v1`.
- **Mandatory Disclosures:** Existing `3` inherited `bitext_train_noisy` eval overlaps remain untouched from baseline Fit 2 (not introduced by the 18-row delta). Warm-starting `epochs=3, lr=2e-5` on `f695b1fe...` yields a comparative candidate evaluation only, not a matched causal control (no second fit authorized).

## 3. Independent Verification Runs

- **CodeGraph:** Queried `codegraph_explore` first without modifying `.codegraph/`.
- **Option A Preflight (pre-commit at `67b8730f`):** `.venv/Scripts/python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir artifacts/models/candidates/run-records-fit2-orig-ret-channel-v3-prep --run-id fit2-orig-ret-channel-fit-v1 --epochs 3 --lr 2e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --validate-only` -> exit `0` (`validated_only: true`, `fits_executed: 0`). Post-review-commit rerun executed immediately after committing this document on `minh` to confirm descendant `HEAD` acceptance.
- **Focused Unit Tests:** `.venv/Scripts/python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py tests/unit/test_boundary_contrast_fit.py tests/unit/test_model_provenance.py tests/unit/test_task_c_evaluation_gates.py tests/unit/test_gate_contract_b.py -q` -> exit `0`, `50 passed, 1 deselected in 171.02s (0:02:51)`.
