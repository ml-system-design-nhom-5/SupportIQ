# Independent Pre-Fit Review: Original Fit2 Return-Channel Contrast Prep (Worker B)

- **Reviewer / Scope:** Worker B (`minh`), strictly read-only independent pre-fit audit (`fits_executed = 0`, zero prep reruns, zero dataset/code/artifact edits).
- **Reviewed Commit & Bundle:** Commit [`da178055`](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-orig-return-contrast-prep-a.md) on `minh`; immutable bundle [`run-records-fit2-orig-ret-channel-v1-prep`](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-ret-channel-v1-prep/prep_manifest.json) (`prep_manifest.json` SHA-256 `e844861d15962c4aade3f1d029ade201b507136e74220824a65af5d0aa4d01f6`).
- **Governing Checklist & Protocol:** [Pre-Fit Checklist (B)](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-next-prefit-checklist-b.md) (`55ec18ba`), [Evaluation Protocol (C)](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-next-evaluation-protocol-c.md) (`b21afeba`), and Coordinator **Option A** authorization (`epochs=3`, `lr=2e-5`, init `f695b1fe...`, `T >= 1.0`, `selective_rejector.enabled=false`).

## Verdict: `BLOCK`

Do **not** launch the single authorized Option A fit against `run-records-fit2-orig-ret-channel-v1-prep` yet. Provenance, baseline bit-identity, delta isolation, and inherited-leakage separation **pass cleanly**, **but** two targeted defects must be fixed before spending the single fit budget:

1. **KB Grounding & Sibling-Intent Contamination (`orig_ret_ch_g04_rp_00` and `orig_ret_ch_g02_rp_02`):** Two of the 10 added `return_policy` TRAIN rows cite `POL-RET-002` inaccurately and fall semantically under sibling `SUPPORTED_12` intent **`refund_policy`** (`POL-REFUND-001` / `POL-REFUND-002`), creating an avoidable cross-intent regression hazard on `final24` (`final-case-03`) and `sa156` (`sup/ans-refund_policy-*`).
2. **Option A Execution & Archival Gap:** [`run_boundary_contrast_fit.py`](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_boundary_contrast_fit.py#L547-L585) hardcodes Option B (`epochs=2, lr=1e-5`) on `v4p1` splits and cannot be used, while `prep_manifest.json`'s inline `planned_cli` omits archiving to `planned_future_paths["archive_dir"]` / `records_dir` and skips post-fit provenance, calibration, reload, and SHA verification.

---

## 1. Independent Verification Summary (Zero Fits, Read-Only)

| Check | Outcome | Verified Evidence |
| :--- | :--- | :--- |
| **Bundle & Sidecar Integrity** | PASS | `prep_manifest.json` SHA `e844861d15962c4aade3f1d029ade201b507136e74220824a65af5d0aa4d01f6`; `33/33` files match `sidecar_sha_inventory.json` (`0` mismatches, `0` extra files). |
| **Source Snapshot & No Premature Fit** | PASS | `13/13` files in `source_snapshot/` match `da178055` & working tree (`0` diffs); `archive_dir`, `records_dir`, and `local_dir` do not exist (`dryrun` only). |
| **Anchors & Canonical Lineage** | PASS | Init `f695b1fe...` (`T=1.0`, rejector `false`, `46` labels), Fit1 `95a940b6...`, Serving `dc7af8cf...`, Bitext `cleaned.csv` `8BC10CFA...` & `splits` `1D366E89...`. |
| **Stage-2 Bit-Identity & Single-Factor Diff** | PASS | `11/13` files bit-identical vs [`stage2_inputs`](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-faithful-fit2-20261113/stage2_inputs/split_manifest.json); ONLY `boundary_pos_train.jsonl` (`181 -> 199`) and `full_train_split.jsonl` (`11320 -> 11338`, effective `13000 -> 13080`) changed by exact 18-row suffix. |
| **Balance & Non-Target Retention** | PASS | `return_policy` domain `11 -> 21` (`44 -> 84` eff @ `4x`), `return_product_in_store` `0 -> 8` (`0 -> 40` eff @ `5x`); `46/46` replay classes intact; all `240` Bitext `track_delivery` (`ambiguous_retained`) & `251` baseline `return_policy` rows + `CAL=824` + `EVAL=6851` untouched. |
| **Delta Isolation vs. Inherited Leakage** | PASS (delta) / Inherited disclosure | `check_split_isolation_and_gold_contamination` on the `18` added rows passes (`0` text/group/parent/ID overlaps vs `CAL`, `EVAL`, `full_train_split`, `v5-r2`, and all 15 frozen suites; `max_jaccard=0.3889`, `max_token_f1=0.5385`, `0` `pseudonymize` diffs). Full `11338`-row check triggers `split_text_overlap:train_vs_eval` solely on the **3 identical inherited** `bitext_train_noisy` vs `bitext_test_6690` rows (`bitext_trn_aug_sample_031082_1`, `bitext_trn_aug_sample_001393_41`, `bitext_trn_aug_sample_020326_51`, `0` vs `CAL`, `0` new leaks). |
| **KB Grounding & Sibling-Intent Semantics** | **FAIL (`2` rows)** | `orig_ret_ch_g04_rp_00` & `orig_ret_ch_g02_rp_02` fail active-KB `POL-RET-001/002/003` grounding and collide with `refund_policy`. |
| **Unit Tests** | PASS | `tests/unit/test_orig_fit2_return_contrast_prep.py`: `4 passed in 57.94s`. Combined (`+ test_boundary_contrast_fit.py`, `test_model_provenance.py`, `test_task_c_evaluation_gates.py`): `42 passed, 1 deselected in 160.77s` (`real_model` deselected per `pytest.ini`). |

Note on CodeGraph compliance: `codegraph_explore` was invoked first per repository rules; existing `train_boundary_candidate.py` callers/source resolved directly, while commit `da178055`'s new files (added after `.codegraph/` was indexed) were inspected directly on disk without mutating `.codegraph/`.

---

## 2. Blocking Findings in Detail

### 2.1 Blocker 1 — KB Grounding & `refund_policy` Label Collision in Added Rows

Audit of all 18 rows in [`orig_fit2_return_contrast_data.py`](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/orig_fit2_return_contrast_data.py#L94-L225) against [`approved_kb.v2.json`](file:///F:/Năm%203/SD/project/SupportIQ/data/knowledge/approved_kb.v2.json#L99-L245) and frozen `sa156` / `final24` labels:

- **`orig_ret_ch_g04_rp_00` (`return_policy`, `policy_source="POL-RET-002"`, `4x` effective) — Misgrounded / Sibling-Intent Mismatch:**
  *"How long after parcel inspection at the warehouse does Tiki issue a refund for an approved return?"*
  - `POL-RET-002` covers only the Tiki app return form, 3–5 unboxing photos/video, courier pickup, and partner post office drop-off; it contains **zero** warehouse-inspection or refund-issuance timeline language.
  - Warehouse inspection after return and refund turnaround live in `POL-REFUND-001` (`supported_intents: ["refund_policy", "request_refund"]`) and `POL-REFUND-002` (`supported_intents: ["refund_policy", "refund_status", "request_refund"]`) — neither supports `return_policy`.
  - In [`sa156`](file:///F:/Năm%203/SD/project/SupportIQ/data/benchmarks/system/v2/acceptance/cases.jsonl#L105-L110), `ans-refund_policy-01` (*"How long does it take for an approved refund to reach my payment method?"*) and `ans-refund_policy-02` (*"What is the refund timeline after a return has been approved?"*) are ground-truth **`refund_policy`**. Indeed, `orig_ret_ch_g04_rp_00` was the closest extension row to `ans-refund_policy-01` (`noise420` / `llm_cases`) and `app-gold-ans-07` (`app_retrieval_gold_v2`).
- **`orig_ret_ch_g02_rp_02` (`return_policy`, `policy_source="POL-RET-002"`, `4x` effective) — Misgrounded / `refund_policy` Overlap:**
  *"Who covers return freight when a buyer sends back an item strictly for change of mind?"*
  - `POL-RET-002` specifies free courier pickup within 1–2 business days and does **not** define change-of-mind return freight allocation; non-refundability of shipping fees for personal preference sits in `POL-REFUND-001` (`refund_policy`, `request_refund`) and is explicitly tested under `refund_policy` in [`final-case-03`](file:///F:/Năm%203/SD/project/SupportIQ/data/benchmarks/final_acceptance/cases.jsonl#L3).
- **Non-blocking polish items to clean in the same edit:**
  - `orig_ret_ch_g03_rp_01` references *"custom-made goods"*, which is not in `POL-RET-003` (use e.g. *"swimwear or non-returnable clearance outlet items"* from `POL-RET-003`).
  - `orig_ret_ch_g02_rp_00` ends with *"qualify for a return refund"* — replace *"return refund"* with *"return or exchange"* (`POL-RET-001`) to avoid pulling refund phrasing toward `return_policy`.
- **Approved rows (no changes needed):** All `8` `return_product_in_store` rows (`g01_ris_00..g04_ris_01`) cleanly target unsupported physical storefront / branch / showroom / mall counter / retail cashier walk-in returns without matching `final-case-*` or eval templates, and the remaining `6` `return_policy` rows (`g01_rp_00..02`, `g02_rp_01`, `g03_rp_00`, `g04_rp_01`) align cleanly with `POL-RET-001/002/003`.

### 2.2 Blocker 2 — Option A Fit & Archival Workflow

In [`run_fit_and_lock_candidate`](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L958-L1275), passing `epochs=3, batch_size=32, lr=2e-5, seed=42, fit_mode="fit2_supcon_energy", enable_selective_rejector=False` preserves `T >= 1.0`, `selective_rejector.enabled=False`, `max_length=64`, and emits both `calibration_manifest.json` and `candidate_provenance_manifest.json`. However:
- `scripts/run_boundary_contrast_fit.py` cannot be run (it hardcodes `epochs=2, lr=1e-5` and builds `v4p1` splits).
- `prep_manifest.json`'s inline `planned_cli` writes only to `local_dir/candidate_model`; it does not archive into `planned_future_paths["archive_dir"]` / `records_dir` or run `validate_calibration_manifest`, `audit_candidate_provenance`, `verify_reload_from_archive`, or SHA inventories. Adding a dedicated, zero-ambiguity Option A fit runner (reading only locked `-prep/datasets` with Option A locked as default/enforced) guarantees durable parity with archived fit bundles.

---

## 3. Inherited Limitation & Causal Continuation Control Disclosure

1. **Inherited Leakage vs. Delta Integrity:** Retaining `exclude_noisy_test_overlap=False` leaves the `3` pre-existing `bitext_train_noisy` vs `bitext_test_6690` normalized text overlaps identically unchanged from Original Fit2 (`0` new overlaps, `0` `CAL` overlaps). Do **not** describe this dataset as having zero global `train_vs_eval` leakage; equally, do **not** alter `exclude_noisy_test_overlap` here, as doing so would bundle a second experimental factor.
2. **Causal Control Flag (No Second Fit Authorized Now):** Warm-starting from Original Fit2 (`f695b1fe`) for `epochs=3, lr=2e-5` applies 3 full continuation epochs over `13,080` effective rows on top of converged weights. Strictly attributing behavioral deltas to the `+18` return-channel rows rather than extra continuation gradient passes would require a **matched no-added-data continuation control** (`epochs=3, lr=2e-5` from `f695b1fe` without the 18 rows). **No second fit is authorized at this stage**; C's post-fit evaluation report must carry this single-run attribution caveat explicitly unless a follow-up control is separately authorized.

---

## 4. Required Actions to Unblock (`v2-prep`)

1. Replace `orig_ret_ch_g04_rp_00` and `orig_ret_ch_g02_rp_02` in `ORIG_FIT2_RETURN_CONTRAST_ROWS` with strictly `POL-RET-001/002/003`-documented return-policy rules (e.g., `Account > Order Management > Request Return/Exchange` status prerequisite or `1–2 business days` courier pickup window from `POL-RET-002`, and unwashed/unused condition with original packaging, accessories, and invoices from `POL-RET-001`, keeping zero refund-timeline / fee-refundability wording), plus the minor `g03_rp_01` / `g02_rp_00` wording cleanups.
2. Re-run zero-fit archival into an immutable new bundle (e.g., `run-records-fit2-orig-ret-channel-v2-prep`) and verify isolation + unit tests.
3. Add a thin Option A fit + archival entrypoint (or complete planned command) consuming only the locked `v2-prep/datasets` snapshot with `epochs=3, lr=2e-5, enable_selective_rejector=False`, archiving `archive_dir` + `records_dir` with `validate_calibration_manifest`, `audit_candidate_provenance`, and `verify_reload_from_archive`.
