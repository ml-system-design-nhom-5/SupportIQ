# Fit2 v5-r2 Prep Re-Review (Worker C)

**Verdict:** `PASS_READY` (zero-fit prep validated; no fit executed or authorized)
**Reviewed Commit:** `d380fee4af685e046a728542e0cf6eccfbd0f258` (`fix(prep): isolate faithful Fit2 restore, reconcile audit summaries, and namespace -prep archival`)
**Prior Review:** [2026-11-14-fit2-v5-taxonomy-prep-review-c.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-v5-taxonomy-prep-review-c.md)
**Prep Archive Audited:** `artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2-prep`

---

## 1. Resolution of Prior Findings

### Finding 1 — Isolated `-prep` Archival Namespace & Non-Colliding Future CLI: **RESOLVED**
- [validate_zero_fit_prep_namespace](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_boundary_contrast_fit.py#L453-L458) writes zero-fit prep archives to `MAIN/run-records-<run-id>-prep` and fails closed upfront (`FileExistsError`) if any of `prep_records_dir`, `fit_archive_dir`, `fit_records_dir`, or `fit_local_dir` already exists or collides.
- `--archive-prep` rejects `--run-contrast-fit` (`ValueError`), transitions `status.json` from `preparing` -> `complete` (`"fits_executed": 0, "prep_archive": true`; or `incomplete` on failure), and emits `planned_future_cli`:
  - `python -m scripts.run_boundary_contrast_fit --run-contrast-fit --run-id fit2-taxonomy-audit-v5-r2 --enable-selective-rejector`
- All three `planned_future_paths` (`fit2-taxonomy-audit-v5-r2`, `run-records-fit2-taxonomy-audit-v5-r2`, and `artifacts/evaluation/boundary_contrast_20261114/fit2-taxonomy-audit-v5-r2`) were verified non-existent (`Path.exists() == False`).

### Finding 2 — Faithful Restore Opt-Out, Candidate Safeguards & Hash Preservation: **RESOLVED**
- In [prepare_and_lock_splits](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L670-L682), active-KB quarantine is opt-in (`apply_active_kb_audit: bool = False`) and noisy-vs-test exclusion defaults on (`exclude_noisy_test_overlap: bool = True`).
- [run_faithful_fit2_restore.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_faithful_fit2_restore.py#L180-L186) keeps `apply_active_kb_audit=False` and explicitly passes `exclude_noisy_test_overlap=False` at both Stage 2 preflight (`L185`) and Stage 2 training (`L355`).
  - Confirmed via read-only comparison: `exclude_noisy_test_overlap=False` yields `3680` `bitext_train_noisy` rows containing `3` historical normalized text matches with `bitext_test_6690` (`bitext_trn_aug_sample_001393_41`, `bitext_trn_aug_sample_020326_51`, `bitext_trn_aug_sample_031082_1`) while `sample_id` parents remain disjoint (`train_test_overlap: 0`); `exclude_noisy_test_overlap=True` removes those `3` rows (`3677` pre-audit -> `3669` post-audit).
  - Neither `dataset_lock_manifest.json` (`augmentation_parent_disjointness` reports parent IDs only; `boundary_audit_summary` reports domain/frozen overlap only) nor `run_faithful_fit2_restore.py` claims noisy-child text isolation against `bitext_test_6690` (non-blocking minor observation: Stage 2 lock/preflight metadata does not explicitly emit `exclude_noisy_test_overlap: false`).
- Candidate prep ([prepare_and_lock_contrast_splits](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/boundary_contrast_data.py#L297-L303)) hardcodes `apply_active_kb_audit=True` and relies on `exclude_noisy_test_overlap=True`; [run_boundary_contrast_fit.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_boundary_contrast_fit.py#L462-L589) runs preflight -> copies SHA-verified datasets -> executes [run_fit_and_lock_candidate](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L958-L980) from those locked JSONLs with no CLI flag to disable contamination guards.
- Real unmocked zero-fit restore check (`test_faithful_fit2_restore_real_preflight_hashes_unaffected`) matches exact **8/8 Closure (`c6cae7a`) + 7/7 Boundary (`d7ddaf2`)** dataset hashes without mutating `run-records-original-fit2-20261113`.

### Finding 3 — Semantic Audit Summary Reconciliation: **RESOLVED**
- Reconciled [semantic_audit_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2-prep/semantic_audit_manifest.json) against [quarantine_records.jsonl](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2-prep/quarantine_records.jsonl) and all locked JSONLs under `datasets/`:

| Split | Input | Kept | Quarantined | `status_counts` (`valid` / `ambiguous_retained` / `quarantined_kb_contradiction`) | Intent / Reason |
|---|---:|---:|---:|---|---|
| `contrast_pos_train` | 303 | 300 | 3 | `274 / 26 / 3` | `track_order` (`kb_pol_ord_001_vehicle_gps_telemetry_contradiction`) |
| `contrast_pos_calibration` | 137 | 135 | 2 | `123 / 12 / 2` | `track_order` (`kb_pol_ord_001_vehicle_gps_telemetry_contradiction`) |
| `contrast_pos_evaluation` | 175 | 175 | 0 | `162 / 13 / 0` | — |
| `bitext_train_clean` | 7360 | 7348 | 12 | `7052 / 296 / 12` | `return_policy` (`kb_pol_ret_001_physical_instore_channel_contradiction`) |
| `bitext_train_noisy` | 3677 | 3669 | 8 | `3526 / 143 / 8` | `return_policy` (`parent_quarantined:...`) |
| `bitext_cal` | 690 | 690 | 0 | `660 / 30 / 0` | — |
| `bitext_test_6690_readonly` | 6690 | 6680 | 10 *(read-only)* | `6388 / 292 / 10` | Audit-only; JSONL stays `6690` rows |

- `quarantined_total == active_quarantined_sum == len(quarantine_records.jsonl) == 25` (`12 + 8 + 3 + 2`), and [build_semantic_audit_manifest](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py) / [run_boundary_contrast_fit.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_boundary_contrast_fit.py#L196-L223) fail closed on any sum mismatch.

---

## 2. Archived `v5-r2-prep` Integrity, Invariants & Ablation Readiness

- **Immutable Archive Audit (`run-records-fit2-taxonomy-audit-v5-r2-prep`):**
  - `35` files total (`34` entries in `sidecar_sha_inventory.json`, `0` mismatches, `0` uninventoried files); **0 weight files** (`.safetensors`/`.bin`/`.pt`/`.ckpt`); `status.json` = `{"status": "complete", "fits_executed": 0, "prep_archive": true}`.
  - `git_commit` = `d380fee4af685e046a728542e0cf6eccfbd0f258`; all `12` files in `source_snapshot/` match `prep_manifest.json`, commit `d380fee4`, and current working tree (`0` diffs).
  - All `15` `dataset_hashes` match `datasets/` byte-for-byte.
- **Lineage & Training Invariants Preserved:**
  - `46/46` `STANDARD_INTENTS_46` present in `bitext_train_clean + bitext_train_noisy` (`0` missing).
  - Canonical Bitext lineage intact (`cleaned_sha256` `8BC10CFA056371BDECB3394BFD4C75EEE7E10022ACE5071833ECD140B2D75846`, `splits_sha256` `1D366E898F6BA68BE46C5CA0F9059E9862FAD1D7BAFE350D9CDD310DD3E0A04C`).
  - Generic `track_delivery` retained for 46-class replay (`160` clean, `80` noisy, `15` cal, `30` `domain_pos_train` -> `270` raw / `390` effective; `263` raw `ambiguous_retained`).
  - Existing archives verified intact: `reconstructed-fit2-supcon-20261113/model.safetensors` (`f695b1fe...`), `fit2-boundary-contrast-v4p1/model.safetensors` (`e1039f92...`), `run-records-original-fit2-20261113`, `run-records-fit2-boundary-contrast-v4p1`, and `run-records-fit2-boundary-contrast-v4p1-dryrun`.
- **Controlled Data-Only Ablation Readiness (Not Fit Authorization):**
  - `run_boundary_contrast_fit.py --run-contrast-fit` keeps exact `v4p1` hyperparameters anchored to `reconstructed-fit2-supcon-20261113` (`f695b1fe...`): `fit2_supcon_energy`, `epochs=2`, `batch_size=32`, `lr=1e-5`, `seed=42`, `min_temperature=1.0`, `neg_repeat=12`, and `776d` rejector `c_grid=(0.15, 0.35, 0.75, 1.5)` over `13881` effective train rows (`434` batches/epoch). Only the locked datasets differ (`25` KB-contradiction rows removed).

---

## 3. Verification Commands & Observed Results

1. **Focused unit & real preflight suite:**
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_boundary_contrast_fit.py tests/unit/test_faithful_fit2_entrypoint.py -v`
   - Result: **22 passed in 147.75s (0:02:27)** (`0` failed, `0` skipped), including `test_faithful_fit2_restore_real_preflight_hashes_unaffected` (real `8/8` Closure + `7/7` Boundary hash check).
2. **Real zero-fit contrast preflight determinism probe (temp dir, `0` fits):**
   - Executed `scripts.run_boundary_contrast_fit.run_preflight_validation` in an isolated `TemporaryDirectory`:
   - Result: `DRY_RUN: True`, `FITS_EXECUTED: 0`, `DATASET_HASH_MATCH_PREP: True`, `COUNTS_MATCH_PREP: True`, `EXPOSURE_MATCH_PREP: True`.
3. **Read-only archive/checksum/lineage audit:**
   - Verified `34/34` `sidecar_sha_inventory.json` hashes, `12/12` `source_snapshot/` SHAs vs commit & working tree, `15/15` `dataset_hashes`, `25` quarantine rows matching `semantic_audit_manifest.json` and JSONLs, `46/46` classes, `0` weight files, and untouched existing archives.
