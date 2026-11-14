# Worker C Review: `v5` Taxonomy Audit Prep (`7e330b35e6e14ab7dc69d7190781870b5ade1f8f`)

- **Verdict:** **`CHANGES_REQUIRED`** *(prep/data-cleaning scope verdict, NOT model acceptance)*
- **Reviewed Source SHA:** `7e330b35e6e14ab7dc69d7190781870b5ade1f8f` (`minh`)
- **Immutable Archive Checked:** [`artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-prep`](../../artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-prep) (`0` fits executed, `0` `.safetensors`/`.bin`/`.pt` weights, `fit2-taxonomy-audit-v5-prep` model dir absent)
- **Boundary:** Read-only code, archive, lineage, and unit-test verification (`0` source/data edits, `0` model fits, `0` LLM/provider calls). B's in-progress order-facts files were not inspected or touched.

---

## 1. Bottom Line

The **underlying 25-row active-KB quarantine** (`5` domain `track_order` telemetry rows + `12` clean Bitext `return_policy` physical-store rows + `8` noisy Bitext children via `parent_sample_id`) is sound, policy-derived, zero-fit, preserves all `46` classes and `train`/`cal`/`eval`/`test` isolation, keeps hyperparameters/`T>=1.0`/loss/`neg_repeat=12`/frozen gates untouched, and accurately flags context-sensitive store wording and generic `track_delivery` (`270` raw / `390` eff, `263` `ambiguous_retained`).

However, **3 concrete prep/compatibility defects require fixes (`CHANGES_REQUIRED`) before launching a fit**:
1. `--archive-prep` occupies `run-records-<run-id>` while writing `planned_future_cli` with the exact same `--run-id`, causing immediate `FileExistsError` on replay.
2. Mutating `prepare_and_lock_splits()` unconditionally breaks the original Fit2 restoration entrypoint [`scripts/run_faithful_fit2_restore.py`](../../scripts/run_faithful_fit2_restore.py).
3. `prepare_and_lock_contrast_splits()` overwrites `split_summaries` after filtering, so [`semantic_audit_manifest.json`](../../artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-prep/semantic_audit_manifest.json) reports `quarantined_rows: 0` across every train/cal/eval split despite `quarantined_total: 25`.

---

## 2. Findings (`File / Line / Evidence`)

### Finding 1 (High — Runner CLI / Path Uniqueness Collision)
- **Where:** [`scripts/run_boundary_contrast_fit.py:325-333, 364, 371-378, 396-408`](../../scripts/run_boundary_contrast_fit.py#L364-L408), [`prep_manifest.json:24-32`](../../artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-prep/prep_manifest.json#L24-L32)
- **Evidence:** `--archive-prep --run-id fit2-taxonomy-audit-v5-prep` writes to `run-records-<run-id>` (`records_dir`), unlike `--archive-dryrun` which writes `run-records-<run-id>-dryrun`. `_archive_zero_fit_records` simultaneously writes `planned_future_cli: [..., "--run-contrast-fit", "--run-id", "fit2-taxonomy-audit-v5-prep", "--enable-selective-rejector"]`. Running that command fails immediately at line `371-372` (`FileExistsError: MAIN run-records already exists`). Additionally, an interrupted `--archive-prep` creates `dest_dir` upfront (`line 295`) without `status.json` (`incomplete` handling only wraps `--run-contrast-fit` at `lines 510-512`), leaving a partial dir blocking retries.
- **Fix:** Archive prep bundles under `run-records-<run-id>-prep` (mirroring `-dryrun`), or require a separate fit `--run-id` and do not emit a colliding `planned_future_cli`.

### Finding 2 (High — Original Fit2 Restoration Entrypoint Broken)
- **Where:** [`pipeline/training/train_boundary_candidate.py:748-763`](../../pipeline/training/train_boundary_candidate.py#L748-L763), [`scripts/run_faithful_fit2_restore.py:176-188`](../../scripts/run_faithful_fit2_restore.py#L176-L188)
- **Evidence:** `prepare_and_lock_splits()` now unconditionally runs `audit_rows_against_active_kb` and drops `25` rows (`bitext_train_clean`: `7360 -> 7348`, `bitext_train_noisy`: `3677 -> 3669`, `domain_pos_train` `-3`, `domain_pos_cal` `-2`). Executing `run_faithful_fit2_restore.run_preflight_validation()` in a temporary directory failed closed:
  `RuntimeError: Stage 2 boundary dataset hash mismatch: {'boundary_split_manifest': True, 'full_train_split': False, 'full_cal_split': False, 'bitext_train_clean': False, 'bitext_train_noisy': False, 'bitext_cal': True, 'bitext_test_6690': True}`.
  [`tests/unit/test_faithful_fit2_entrypoint.py`](../../tests/unit/test_faithful_fit2_entrypoint.py) passed (`4/4`) only because it mocks `run_preflight_validation` and `prepare_and_lock_splits`.
- **Fix:** Gate the active-KB quarantine filter in `prepare_and_lock_splits()` behind an opt-in parameter (`apply_active_kb_audit: bool = False`, passed `True` by `prepare_and_lock_contrast_splits()`) so `d7ddaf2` restoration remains reproducible.

### Finding 3 (High — `semantic_audit_manifest.json` Split-Summary Accounting Contradiction)
- **Where:** [`pipeline/training/boundary_contrast_data.py:480-485, 611-625`](../../pipeline/training/boundary_contrast_data.py#L480-L485), [`semantic_audit_manifest.json:13-135`](../../artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-prep/semantic_audit_manifest.json#L13-L135)
- **Evidence:** `prepare_and_lock_contrast_splits()` calls `audit_rows_against_active_kb` a second time on already-filtered lists (`pos_train`, `bitext_clean`, `bitext_noisy`, `bitext_cal`) and overwrites `semantic_audit_manifest.json` (`split_summaries`) and `lock["semantic_audit"]`. Every train/cal/eval `split_summary` therefore shows `"quarantined_rows": 0` and `"quarantined_by_intent": {}`, contradicting `"quarantined_total": 25` and the `25` records in `quarantine_records.jsonl`.
- **Fix:** Preserve or merge the pre-filter quarantine counts from `base_lock["semantic_audit"]["split_summaries"]` when assembling the final `semantic_audit_manifest.json`.

### Finding 4 (Medium — Bitext-Gold Tradeoff, Remaining Typo Edge Case in Held-Out Test, & Confounders)
- **Bitext-vs-KB Tradeoff (`bitext_test_6690`):** `10` rows in `bitext_test_6690_readonly` (plus `1` unflagged missing-space typo `sample_029476`: `'could i return some productsat the store'`) carry Bitext's original `return_policy` label for physical-store queries. Removing `20` matching rows from Bitext train (`return_policy` clean `148`, noisy `72`, cal `15`, with `0` store/shop substrings remaining in kept Bitext train/cal) aligns training with SupportIQ's active KB (`POL-RET-001` vs `return_product_in_store`), at the expected tradeoff of lower accuracy on Bitext's `11/6690` physical-store `return_policy` subset; Bitext labels represent a taxonomy disagreement with SupportIQ's KB rather than universally invalid Bitext gold.
- **Minor Regex Precision Note (`track_delivery`):** `263` of `270` train `track_delivery` rows (`390` effective) are flagged `ambiguous_retained`; `3` of the `10` authored `track_delivery` contrast rows (`contrast_auth_pos_train_021`, `_024`, `_027`) did not match `VEHICLE_GPS_TELEMETRY_RE` (`"attempted drop-off"`, `"handoff proof"`, `"doorstep delivery telemetry"` vs `"doorstep telemetry"`). Harmless for retention, slightly overstates `ambiguous_retained` by `3`.
- **Shared Ephemeral Dryrun Path:** [`run_boundary_contrast_fit.py:362`](../../scripts/run_boundary_contrast_fit.py#L362) writes into shared `LOCAL_CONTRAST_ROOT / "dryrun"`, and `dataset_lock_manifest.json` `files.*.path` points to that mutable directory rather than the archive's `datasets/`.

---

## 3. Verified Provenance, Filtering & Hyperparameter Checks

| Check | Verified Result |
| :--- | :--- |
| **Archive Checksums & Revision** | `33/33` files in `sidecar_sha_inventory.json`: `0` SHA mismatches; `12/12` `source_snapshot` hashes match `HEAD` (`7e330b35e6e14ab7dc69d7190781870b5ade1f8f`); `serving_weights_sha256` (`dc7af8cf...`) & `starting_checkpoint` `reconstructed-fit2-supcon-20261113` (`f695b1fe...`, `T=1.0`, `rejector_enabled=false`) match; canonical Bitext `8BC10CFA...` / `1D366E89...` unchanged; `0` fits, `0` weights in archive. |
| **25 Quarantined Rows (`quarantine_records.jsonl`)** | Verified original text/hash/label/`parent_sample_id`: `5` `closure_positive_20261113` `track_order` telemetry contradictions (`cls_trk_live_gps_0`, `cls_trk_live_gps_2`, `cls_trk_partner_portal_2` in train; `cls_trk_sms_alerts_1`, `cls_trk_sms_alerts_2` in cal), `12` `bitext_train_clean` `return_policy` store/shop rows (`sample_029467`..`029277`), and all `8` augmented noisy children (`bitext_trn_aug_sample_029467_0`..`_028947_76`) propagated via `parent_quarantined:`. Zero blanket relabeling. |
| **Context-Sensitive & Uniform Filtering** | Kept `return_policy` rows retain merchant/online phrases (`cls_rpo_window_tier_1` `"official mall"`, `bnd_return_policy_trn_0` `"standard store rules"`, `contrast_auth_pos_eval_100` `"store return policy"`); `0` store/shop substrings remain in `bitext_train_clean` (`148`), `bitext_train_noisy` (`72`), or `bitext_cal` (`15`). Shared rules run across clean, noisy, extra `bitext_train_esc34_pos_*`, `domain`, and `cal` without CAL failure cherry-picking (`0` CAL Bitext rows quarantined; `bitext_test_6690` read-only audited & untouched). |
| **Labels, Isolation & Effective Trainer Counts** | All `46` labels preserved in both `bitext_train_clean + bitext_train_noisy` (`46`) and `bitext_cal` (`46`); `0` `train`/`cal`/`eval+test` `parent_sample_id`/`group_id`/text overlaps; `run_fit_and_lock_candidate` builds `13,881` effective train rows (`12,357` pos CE + `1,524` neg KL, `434` batches @ `bs=32`), matching `dataset_lock_manifest.json` (`13,881`). `track_delivery`: `270` raw (`160` clean + `80` noisy + `20` extra `5x` + `10` authored `5x`) = `390` effective (`263` `ambiguous_retained`). |
| **Frozen Policy & Training Contracts** | Unchanged: `epochs=2`, `lr=1e-5`, `bs=32`, `fit_mode="fit2_supcon_energy"`, `neg_repeat=12`, `4x`/`5x` pos repeats, `min_temperature=1.0`, `selective_calibration.v1` `C_grid=(0.15,0.35,0.75,1.5)`, frozen gates (`final >= 10/12`, `system >= 25/34`, `sa156 >= 26/30`). Diagnosis prose ([`2026-11-14-fit2-v4p1-regression-diagnosis-a.md:108-126`](../audits/2026-11-14-fit2-v4p1-regression-diagnosis-a.md#L108-L126)) cleanly separates implemented prep from unexecuted hypotheses. |

---

## 4. Exact Tests & Checks Executed (`0` Fits)

- `.\.venv\Scripts\python.exe -m pytest tests/unit/test_boundary_contrast_fit.py -v` -> **`15 passed` in `62.83s`**.
- `.\.venv\Scripts\python.exe -m pytest tests/unit/test_faithful_fit2_entrypoint.py -v` -> **`4 passed` in `41.79s`** *(mocked preflight/splits)*.
- Read-only Python archive/checksum/provenance/count simulation -> **`33/33` SHA pass, `12/12` source snapshot pass, `0` weights, `13,881` effective trainer rows verified, `0` Bitext kept `return_policy` store substrings**.
- Read-only `run_faithful_fit2_restore.run_preflight_validation()` in temp dir -> **failed (`RuntimeError: Stage 2 boundary dataset hash mismatch`)**.

---

## 5. Readiness Assessment, Remaining Hypotheses & Recommended Next Sequential Action

- **Ablation Readiness:** **Not ready until Findings 1–3 are fixed (`CHANGES_REQUIRED`).** Once those 3 prep/manifest/restoration fixes are applied and verified, the data-cleaning prep is clean enough for a single fixed-hyperparameter ablation (`epochs=2, lr=1e-5, bs=32, neg_repeat=12`, etc.) **using a fresh `--run-id`** if the coordinator authorizes it.
- **Remaining Unexecuted Hypotheses (Not Tested Here):** Even after cleaning those `25` rows, `v5-prep` holds fixed (1) the `5x`-repeated `20` generic Bitext `track_delivery` rows (`390` eff), (2) `41.7%` compound share at `neg_repeat=12`, (3) imbalanced `SUP11` domain exposure (`delivery_issue`/`cancel_order`/`refund_status`/`payment_issue`/`shipping_costs`/`return_product_online`), and (4) the `776d` `[CLS]` 11-vs-35 rejector. Removing only the `25` rows tests the taxonomy-quarantine effect cleanly, but is not guaranteed by itself to recover non-contrast `SUP11` confidence or `[CLS]` false vetoes.
- **Recommended Next Sequential Action:** Fix Findings 1–3 (`--archive-prep` `-prep` dir suffix / non-colliding `planned_future_cli`, opt-in flag in `prepare_and_lock_splits()` preserving `run_faithful_fit2_restore.py`, and pre-filter `split_summaries` preservation in `semantic_audit_manifest.json`), re-archive the zero-fit prep bundle under a clean SHA, and await coordinator authorization before running any fit.
