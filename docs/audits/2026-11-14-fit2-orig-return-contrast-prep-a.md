# Original Fit2 Single-Factor Return-Channel Contrast Prep v2 (Worker A, Zero-Fit)

- **Owner / Scope:** Worker A (`minh`), strictly zero-fit preparation addressing Worker B's two `BLOCK` items from [prefit review B](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-orig-return-contrast-prefit-review-b.md) (`fits_executed = 0`, no optimizer/calibrator calls, no live LLM calls, no serving changes).
- **Immutable MAIN Prep Bundle:** `artifacts/models/candidates/run-records-fit2-orig-ret-channel-v2-prep/` (generated cleanly after scoped `v2` commit; prior `run-records-fit2-orig-ret-channel-v1-prep/` preserved untouched).
- **Explicit Option A Runner & Unused Fit Namespace:** [run_orig_fit2_return_contrast_fit.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py), target fit ID `fit2-orig-ret-channel-fit-v1` (awaiting Worker B re-review `PASS` & explicit coordinator release).

---

## 1. Frozen Baseline Anchor & Invariants

| Artifact | Path / Ref | Verified SHA-256 / Value |
| --- | --- | --- |
| Original Fit2 Checkpoint | [reconstructed-fit2-supcon-20261113](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors) | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` |
| Fit1 Initializer Reference | [reconstructed-closure-fit1-20261113](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/reconstructed-closure-fit1-20261113/model.safetensors) | `95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6` |
| Serving Model (Untouched) | [distilbert-supportiq](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/trained/distilbert-supportiq/model.safetensors) | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| Calibration / Rejector | Original Fit2 manifest | `T = 1.0`, `min_temperature = 1.0`, `selective_rejector.enabled = false`, `46` labels (`STANDARD_INTENTS_46`) |
| Knowledge Base & Policy | [approved_kb.v2.json](file:///F:/Năm%203/SD/project/SupportIQ/data/knowledge/approved_kb.v2.json), [intent_policy.v2.json](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/config/policies/intent_policy.v2.json) | `kb = f8dcfbbdbb9cb2cd...`, `policy = 8789ee26acdac2e1...` |

All non-target taxonomy rules remain frozen:
- `STANDARD_INTENTS_46` unchanged.
- Existing `82–87` general return-eligibility rows in `return_policy` and `263` generic `track_delivery` rows (`ambiguous_retained`) remain untouched (`apply_active_kb_audit = false`).
- All CAL, EVAL, `bitext_test_6690`, `bitext_train_clean`, `bitext_train_noisy`, `boundary_neg_train`, `split_manifest.json`, and all frozen benchmarks/holdouts remain untouched.

---

## 2. Fixes Applied for B Review Blockers (`v2`)

### 2.1 Blocker 1 Fix — Active-KB Grounding (`POL-RET-001/002/003`, Zero `refund_policy` Collision)

Replaced/cleaned the `4` reviewed `return_policy` rows in [orig_fit2_return_contrast_data.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/orig_fit2_return_contrast_data.py) strictly against `POL-RET-001/002/003` in `approved_kb.v2.json`:
- **`orig_ret_ch_g02_rp_00`** (`POL-RET-001`, polished): *"Must original promotional gifts and factory seals stay unbroken to qualify for a return or exchange?"*
- **`orig_ret_ch_g02_rp_02`** (`POL-RET-001`, replaced freight/refund): *"Must a returned product stay unwashed and unused with its original boxes, accessories, and invoices included?"*
- **`orig_ret_ch_g03_rp_01`** (`POL-RET-003`, replaced custom-made goods): *"When do restricted swimwear or non-returnable clearance outlet items still qualify for a return or exchange?"*
- **`orig_ret_ch_g04_rp_00`** (`POL-RET-002`, replaced warehouse refund timing): *"Which order status enables Request Return/Exchange in Order Management, and within how many business days does courier pickup occur?"*

All `10` `return_policy` (`4x` = `40` eff) and `8` `return_product_in_store` (`5x` = `40` eff) TRAIN-only rows (`18` total across `orig_ret_ch_g01..04`) contain zero refund-timeline / freight-refund / non-KB wording and align verbatim with `POL-RET-001/002/003` vs unsupported brick-and-mortar store walk-in returns.

### 2.2 Blocker 2 Fix — Explicit Fail-Closed Option A Execution & Archival Runner

Added thin explicit runner [run_orig_fit2_return_contrast_fit.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py):
- Consumes **only** locked `run-records-fit2-orig-ret-channel-v2-prep/datasets` (never calls `prepare_and_lock_splits`).
- Enforces **Option A** parameters fail-closed (`epochs=3, lr=2e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy", min_temperature=1.0, enable_selective_rejector=False`; no alternate hardcoded 2-epoch / `1e-5` path).
- Verifies `v2-prep/sidecar_sha_inventory.json`, `new_input_file_hashes`, exact `HEAD == prep_manifest.git_commit`, clean git status + matching `source_hashes` across all `14` tracked `RELEVANT_SOURCE_PATHS`, untouched Serving (`dc7af8cf...`) & Fit2 `f695b1fe...` init (`T=1.0`, rejector `false`), and unused `archive_dir` / `records_dir` / `local_root`.
- On future authorized `--run-option-a-fit`, preserves model weights/tokenizer/config, `calibration_manifest.json`, `candidate_provenance_manifest.json`, inputs snapshot + `inputs_sha256_inventory.json`, `source_snapshot/`, `environment.json`, `run_config.json`, `run.log`, `fit_result.json`, `archive_sha_inventory.json`, and `sidecar_sha_inventory.json`, failing closed unless `validate_calibration_manifest`, `audit_candidate_provenance`, and `verify_reload_from_archive` all pass.

**Planned Option A Command (Recorded in `v2-prep/prep_manifest.json`; NOT Executed):**
```powershell
.venv/Scripts/python.exe -m scripts.run_orig_fit2_return_contrast_fit `
  --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-ret-channel-v2-prep" `
  --run-id fit2-orig-ret-channel-fit-v1 `
  --epochs 3 --lr 2e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --run-option-a-fit
```

---

## 3. Baseline-vs-New Diff, Raw/Post-Privacy Isolation & Inherited Disclosures

- **Stage-2 Diff:** `11/13` baseline files bit-identical vs `run-records-faithful-fit2-20261113/stage2_inputs`; ONLY `boundary_pos_train.jsonl` (`181 -> 199`) and `full_train_split.jsonl` (`11320 -> 11338`, `13000 -> 13080` eff) changed (`+10` `return_policy` / `+40` eff, `+8` `return_product_in_store` / `+40` eff).
- **Delta Raw & Post-Privacy Isolation:** `0` exact text, `parent_sample_id`, `group_id`, or `pseudonymize`-normalized overlaps across all prior splits and frozen suites (`max_jaccard = 0.3889 < 0.55`, `max_token_f1 = 0.5385 < 0.65`, `post_privacy_max_jaccard = 0.3889`, `post_privacy_max_token_f1 = 0.5385`, `pseudonymize_changed_extension_rows = []`).
- **Inherited Historical Noisy Overlap Disclosure:** Retaining `exclude_noisy_test_overlap=False` leaves the `3` pre-existing `bitext_train_noisy` vs `bitext_test_6690` normalized overlaps (`bitext_trn_aug_sample_031082_1`, `001393_41`, `020326_51`; `0` vs CAL; `0` clean vs EVAL) identically unmodified; not fixed here to avoid bundling extra factors, and no global zero-leakage claim is made.
- **Causal Attribution Caveat:** Option A (`epochs=3, lr=2e-5` from `f695b1fe...`) evaluates a comparative continuation candidate rather than a matched causal control (a matched no-added-data continuation control fit is unauthorized). Training remains frozen until Worker B re-review `PASS` and explicit coordinator release.
