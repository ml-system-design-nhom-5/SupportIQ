# Fit2 v4.1 Preparation Re-Review (Worker B)

- **Verdict:** `PASS_READY` *(ready strictly for one future coordinator-authorized bounded GPU continuation fit + fixed four-point CPU `C` grid; does NOT authorize execution, acceptance, or promotion)*
- **Reviewed Implementation Commit:** `9ff541b4f4fbdecc4f6f1a7fa9d46a88d928ba2c` (`minh`)
- **Diff Reviewed:** `e456fb7..9ff541b4f4fbdecc4f6f1a7fa9d46a88d928ba2c` (`6` files, `+514 / -53`), following prior Worker B review `docs/audits/2026-11-14-fit2-v4-prep-review-b.md` at `e456fb7`.
- **Dry-Run Archive Verified:** `artifacts/models/candidates/run-records-fit2-boundary-contrast-v4p1-dryrun` (`fits_executed = 0`)

---

## 1. Resolution of All Five Prior Findings

| # | Prior Finding | Verification in `9ff541b4f4fbdecc4f6f1a7fa9d46a88d928ba2c` | Status |
|---|---|---|---|
| 1 | Degenerate all-abstain / unsafe CAL selector | `fit_selective_rejector_from_arrays` (`pipeline/training/train_boundary_candidate.py`) now enforces `zero_unsafe = (total_unsafe == 0)` AND `nonzero_cov` on both `cal_dom` (when present) and `bitext_cal` (when present), failing closed with diagnostic `ValueError` (`evaluated`, `safe`, `nonzero_cov`, `max_dom_corr_when_safe`, `max_bitext_corr_when_safe`, `min_unsafe_when_nonzero_cov`) if no feasible `(C, threshold)` exists. Trained weights in `local_root/candidate_model_contrast` are saved at lines 833-836 prior to rejector selection, and `scripts/run_boundary_contrast_fit.py` catches exceptions into `status.json` (`status = "incomplete"`, preserving evidence without creating an incomplete archive). | Resolved |
| 2 | `human_agent` & `bitext_cal` CAL bookkeeping | `esc34_unsafe_draft` and `human_unsafe_draft` are tracked on both `cal_dom_intents` and `bitext_cal_intents` and combined into `non_draft_unsafe`; `sup11_cov_score` averages present domain and Bitext `SUPPORTED_11` rates (`pos_dom_corr / sup11_dom_raw` and `pos_bit_corr / sup11_bit_raw`). Scaler and logistic regression remain fitted strictly on `TRAIN`; temperature and `(C, threshold)` selection remain strictly on `CAL` with zero evaluation dependence. | Resolved |
| 3 | Noisy train vs `bitext_test_6690` overlap | `prepare_and_lock_splits` excludes `test_norms` (from `lineage.test_df["instruction"]`) for `bitext_train_noisy_rows` and `safe_records`, reducing `bitext_train_noisy` to `3677` rows (from `3680`). `prepare_and_lock_contrast_splits` (`pipeline/training/boundary_contrast_data.py`) loads `bitext_test_6690.jsonl`, verifies zero train/cal/eval parent overlap, and runs `check_split_isolation_and_gold_contamination` with `eval_rows = full_eval_all + bitext_test`. Verified `0` text/group overlaps across all pairs. | Resolved |
| 4 | Unclean working tree vs provenance | `RELEVANT_SOURCE_PATHS` (12 tracked files in `scripts/run_boundary_contrast_fit.py`) is checked via `git status --porcelain -- <paths>` and SHA-256 hashed (`verify_relevant_source_provenance`), catching dirty/untracked/missing relevant files while ignoring unrelated user files (`D artifacts/models/.gitkeep`, user `.pptx`, untracked `audit-b`, `boundary_contrast_20261114`). Post-fit runner records `source_snapshot/` + `source_hashes`, calls `audit_candidate_provenance(archive_dir, archive_dir / "candidate_provenance_manifest.json")` checking `REQUIRED_PROVENANCE_FIELDS = ("training_lineage", "dataset_hashes", "base_model", "git_commit")`, 46-label bijection, `provenance_status`, and `artifact_hashes` before `verify_reload_from_archive`. Failure marks `status.json = "incomplete"`. | Resolved |
| 5 | Disabled rejector metadata parity | `GateSequenceClassifier.predict` (`pipeline/evaluation/classifier_acceptance_gate.py:667-729`) gates `_evaluate_experimental_rejector` and `output_hidden_states` on `rejector_active`, emitting `selective_accepted = None` and `rejector_decision = None` when `rejector.enabled is False`, matching `apps/ml_inference/app.py`. | Resolved |

---

## 2. Dry-Run Archive & Lineage Verification (`v4p1`)

Checked `artifacts/models/candidates/run-records-fit2-boundary-contrast-v4p1-dryrun`:
- `dryrun_manifest.json`: `git_commit = "9ff541b4f4fbdecc4f6f1a7fa9d46a88d928ba2c"`, `planned_run_id = "fit2-boundary-contrast-v4p1"`, `dry_run = true`, `fits_executed = 0`, `bitext_train_noisy = 3677`, `total_effective_train_rows = 13901`, `bitext_train_noisy` SHA `1b2f07e06ac323ae7a2c227eddcfbf4a8009c4f5939e3bbf2340ef129d0abe14`, `full_train_split` SHA `478ccecb556951cf7f3814d100c38e922963c24aea34ed965c75850d643db7df`.
- `sidecar_sha_inventory.json`: all `28` entries (`14` datasets + `dryrun_manifest.json` + `environment.json` + `12` `source_snapshot/` files) verified with `0` SHA mismatches, and all `12` `source_snapshot/` files match working tree `9ff541b4f4fbdecc4f6f1a7fa9d46a88d928ba2c` byte-for-byte.
- Preserved artifacts & canonical lineage:
  - Prior archive `run-records-fit2-boundary-contrast-v4-dryrun` intact (`0` mismatches against its inventory).
  - Serving baseline SHA: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`.
  - Original Fit2 init checkpoint (`reconstructed-fit2-supcon-20261113`): `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`.
  - Canonical Bitext CSV (`cleaned.csv`): `8bc10cfa056371bdecb3394bfd4c75eee7e10022ace5071833ecd140b2d75846`; `split_assignments.csv`: `1d366e898f6ba68be46c5ca0f9059e9862fad1d7bafe350d9cdd310dd3e0a04c`.

---

## 3. Test Review & Verification Results

New tests in `tests/unit/test_boundary_contrast_fit.py` cover concrete failure modes (all-abstain/zero-domain/zero-Bitext/human-agent unsafe leaks, `bitext_train_noisy` overlap exclusion against Bitext test, dirty relevant file rejection vs unrelated user file allowance, disabled rejector `None` metadata parity, and post-fit provenance failure marking `status.json = "incomplete"`).

- **Focused re-verification run on `9ff541b4f4fbdecc4f6f1a7fa9d46a88d928ba2c`:**
  ```text
  .venv/Scripts/python.exe -m pytest tests/unit/test_boundary_contrast_fit.py tests/unit/test_gate_contract_b.py tests/unit/test_model_runtime_parity_b.py tests/unit/test_task_c_evaluation_gates.py tests/unit/test_model_provenance.py tests/unit/test_intent_client_rejector_routing.py -q
  ```
  Result: `119 passed, 1 deselected in 63.30s` (`real_model` marker deselected by `pytest.ini` config).
- **Artifact & isolation verification script on `v4p1-dryrun`:**
  Result: `28` sidecars verified (`0` mismatches), `12` source snapshots matched, `bitext_train_noisy` len `3677`, `check_split_isolation_and_gold_contamination` across `full_eval_all + bitext_test` passed (`0` group/text overlaps).
- **Unchanged code baseline (reused from prior Worker B verification on `f5913ad`):**
  Earlier broader suite passed `127 passed, 1 deselected` + `164 passed` (`291` total passes excluding `real_model`) for unchanged runtime/routing/evaluation modules.

---

## 4. Remaining Non-Blocking Notes & Unproved Claims

- `RELEVANT_SOURCE_PATHS` tracks the `12` fit/data/gate/routing/policy files needed for training and provenance; runtime inference files (e.g., `apps/ml_inference/app.py`, `apps/ai_service/engine.py`) remain intentionally outside that guard list during dry-run/fit.
- All accuracy, OOD leak, Brier, and draft-coverage targets in `docs/superpowers/plans/2026-11-14-fit2-v4-taxonomy-calibration-plan.md` remain **unmeasured design targets** (`fits_executed = 0`); actual acceptance depends on post-fit `Task C` evaluation once a coordinator authorizes execution.
