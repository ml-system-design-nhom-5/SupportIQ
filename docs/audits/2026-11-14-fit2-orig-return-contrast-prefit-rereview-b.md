# Worker B Pre-Fit Re-Review: Original Fit 2 Return-Channel Contrast (`v2-prep`)

- **Target commit:** `bfb50e871041546d31d5dbd1e99080c96b32bfe2` (`minh`)
- **Locked prep bundle:** `artifacts/models/candidates/run-records-fit2-orig-ret-channel-v2-prep`
- **Verdict:** **BLOCK** (new runner self-lockout on branch progression; original `v1` blockers resolved)

## 1. Blocking Finding

1. **`git_commit == HEAD` strict check locks out execution after any audit commit on `minh`** — [run_orig_fit2_return_contrast_fit.py#L155-L161](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py#L155-L161)
   - `verify_locked_v2_prep_bundle` checks `source_prov["git_commit"] != manifest.get("git_commit")` against `bfb50e871041546d31d5dbd1e99080c96b32bfe2`.
   - Once this review commit (or any coordinator/audit commit) advances `HEAD` on `minh`, executing the planned Option A CLI on `minh` will fail closed immediately with `ValueError: Repo HEAD commit <HEAD> differs from locked prep commit bfb50e871041546d31d5dbd1e99080c96b32bfe2`, even when all 14 `source_hashes` entries are bit-identical.
   - [test_orig_fit2_return_contrast_prep.py#L255-L258](file:///F:/Năm%203/SD/project/SupportIQ/tests/unit/test_orig_fit2_return_contrast_prep.py#L255-L258) masked this by monkeypatching `verify_orig_relevant_source_provenance` to return the expected `git_sha`.
   - **Remediation:** Replace strict `HEAD == manifest["git_commit"]` equality with `source_prov["source_hashes"] == (manifest.get("source_hashes") or {})`, ancestor verification (`git merge-base --is-ancestor <manifest_commit> HEAD`), and clean working tree status for `RELEVANT_SOURCE_PATHS` (note: because `scripts/run_orig_fit2_return_contrast_fit.py` is hashed inside `source_hashes`, modifying it requires re-archiving `v3-prep`; alternatively, Coordinator would have to run Option A from a detached worktree at `bfb50e871041546d31d5dbd1e99080c96b32bfe2`).
   - **Minor test coverage gap (non-blocking alone):** No unit test executes the `execute_fit=True` exception path ([run_orig_fit2_return_contrast_fit.py#L375-L378](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py#L375-L378)) to verify `status.json == "incomplete"` and `fits_completed == 0`.

## 2. Original `v1` Blockers — Verified Fixed

- **KB Grounding & `refund_policy` Collision:** All 18 rows report `sem_status: "valid"`. All 4 revised `return_policy` rows (`orig_ret_ch_g02_rp_00`, `orig_ret_ch_g02_rp_02`, `orig_ret_ch_g03_rp_01`, `orig_ret_ch_g04_rp_00`) in [orig_fit2_return_contrast_data.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/orig_fit2_return_contrast_data.py) align accurately with `POL-RET-001`, `POL-RET-002`, and `POL-RET-003` with zero `refund_policy`, `freight`, `warehouse`, or `custom-made` wording. `ext_intent_counts` matches `{"return_policy": 10, "return_product_in_store": 8}` (`10x4=40` vs `8x5=40`).
- **Option A Runner & Archival Pre-Checks:** `--validate-only` run exited `0` (`validated_only: true`, `fits_executed: 0`), verifying [prep_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-ret-channel-v2-prep/prep_manifest.json) settings (`epochs=3`, `lr=2e-05`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=false`), `starting_checkpoint` (`T: 1.0`, `rejector_enabled: false`, `num_labels: 46`, `serving_weights_sha256: "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302"`), fail-closed `status.json="incomplete"` handler on exception, and clean unused fit targets (`archive_dir: false`, `records_dir: false`, `local_dir: false`, `local_children: ["dryrun"]`).

## 3. Archive Integrity, Isolation & Causal Caveat

- **`v1-prep` Untouched:** `prep_manifest.json` SHA-256 `e844861d15962c4aade3f1d029ade201b507136e74220824a65af5d0aa4d01f6`; `33/33` `sidecar_sha_inventory.json` hashes verified (`0` mismatches).
- **`v2-prep` Intact:** `prep_manifest.json` SHA-256 `f24fb814c5ce7fa9cbcdd665c431c4cf8fb3319570e64244f1c28600d918d961`; `34/34` `sidecar_sha_inventory.json` hashes verified (`0` mismatches); `source_snapshot/` diffs `[]`.
- **Stage-2 Delta Integrity:** `full_train_split.jsonl` SHA-256 `63254304c1ccd722a5fc40b23ee37ee239006f7e66b10a2d81371417190571d0`; `boundary_pos_train.jsonl` SHA-256 `7aba414e3c2ad01e77b2dfb51252bb7ffbf8b53581b088a472e0a4cae39dc91e`; `11/13` Stage-2 files bit-identical to `run-records-faithful-fit2-20261113/stage2_inputs`; exact prefix + 18-row suffix confirmed.
- **Leakage & Privacy Isolation:** `gate_ext_passed: true`, `raw_max_jaccard: 0.3889`, `raw_max_token_f1: 0.5385`, `post_privacy_max_jaccard: 0.3889`, `post_privacy_max_token_f1: 0.5385`, `pseudonymize_changed_ext_rows: []`, `prep_cal_overlap_count: 0`. `gate_full` fails solely on `split_text_overlap:train_vs_eval` with `orig_vs_prep_eval_overlap_identical: true` for the exact 3 inherited `bitext_train_noisy` rows (`bitext_trn_aug_sample_031082_1`, `bitext_trn_aug_sample_001393_41`, `bitext_trn_aug_sample_020326_51`), distinct from the 18-row delta.
- **Causal Control Caveat:** `option_a_execution_plan.causal_control_caveat` notes that continuing from post-Fit-2 `f695b1fe...` (`epochs=3`, `lr=2e-05`) without an unaugmented continuation control leaves extra-step vs 18-row-contrast attribution confounded (no second fit authorized).

## 4. Verification Runs

- **CodeGraph:** Queried `codegraph_explore` first; index was stale / unindexed for new commit `bfb50e87`, so direct git diff and file reads were used without mutating `.codegraph/`.
- **Option A Preflight (`fits_executed: 0`):** `.venv/Scripts/python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-ret-channel-v2-prep" --validate-only` -> exit `0` (`validated_only: true`, `fits_executed: 0`).
- **Unit Suites:** `.venv/Scripts/python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py tests/unit/test_boundary_contrast_fit.py tests/unit/test_model_provenance.py tests/unit/test_task_c_evaluation_gates.py tests/unit/test_gate_contract_b.py -q` -> exit `0`, `49 passed, 1 deselected in 167.81s (0:02:47)`.
