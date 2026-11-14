# Original Fit2 Single-Factor Return-Channel Contrast Prep (Worker A, Zero-Fit)

- **Owner / Scope:** Worker A (`minh`), strictly zero-fit preparation (`fits_executed = 0`, no optimizer/calibrator calls, no live LLM calls, no serving changes).
- **Immutable MAIN Prep Bundle:** `artifacts/models/candidates/run-records-fit2-orig-ret-channel-v1-prep/` (generated after clean scoped commit; zero overwrite).
- **Planned Future Fit Namespace (Unused & Unexecuted):** `fit2-orig-ret-channel-fit-v1` (awaiting Worker B checklist review & explicit coordinator fit authorization).

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
- All CAL, EVAL, `bitext_test_6690`, `bitext_train_clean`, `bitext_train_noisy`, `boundary_neg_train`, `split_manifest.json`, and all 10 protocol holdouts remain frozen and untouched.

---

## 2. Single-Factor Contrast Delta & KB Rationale

Reusing `prepare_and_lock_splits(..., apply_active_kb_audit=False, exclude_noisy_test_overlap=False)` reproduces Original Fit2 `run-records-faithful-fit2-20261113/stage2_inputs/` bit-for-bit across all 13 files (`0` hash diffs).

In Original Fit2 `boundary_pos_train.jsonl`, `return_policy` had `11` domain rows (`44` effective) while `return_product_in_store` had `0` domain rows (`0` effective), relying solely on `240` generic Bitext rows (`160` clean + `80` noisy).

**KB Grounding (`approved_kb.v2.json`):**
- `return_policy` (`SUPPORTED_12`, `4x` repeat): `POL-RET-001` (30-day Tiki Trading vs 7-day marketplace return window; original seals/packaging/promotional gifts), `POL-RET-002` (Account > Order Management > Request Return with 3–5 unboxing photos/video; free courier pickup or designated partner post office drop-off; change-of-mind freight; warehouse inspection refund timing), `POL-RET-003` (restricted/final-sale categories vs defective exception).
- `return_product_in_store` (`ESCALATED_34`, `5x` repeat): physical brick-and-mortar retail storefront / branch / showroom / mall counter / shop cashier walk-in return channel — unsupported per `approved_kb.v2.json` (no retail walk-in channel in `POL-RET-002`).

### Authored TRAIN-Only Families (`orig_fit2_return_channel_contrast_v1`)

Implemented in [orig_fit2_return_contrast_data.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/orig_fit2_return_contrast_data.py) (`18` raw TRAIN rows across `4` paired thematic groups `orig_ret_ch_g01..04`):
- **`orig_ret_ch_g01`** (channel & window eligibility): `3` `return_policy` (`orig_ret_ch_g01_rp_00..02`, `POL-RET-001/002`) vs `2` `return_product_in_store` (`orig_ret_ch_g01_ris_00..01`).
- **`orig_ret_ch_g02`** (packaging/media/freight vs walk-in counter/cashier): `3` `return_policy` (`orig_ret_ch_g02_rp_00..02`, `POL-RET-001/002`) vs `2` `return_product_in_store` (`orig_ret_ch_g02_ris_00..01`).
- **`orig_ret_ch_g03`** (restricted categories vs mall showroom/outlet register): `2` `return_policy` (`orig_ret_ch_g03_rp_00..01`, `POL-RET-003`) vs `2` `return_product_in_store` (`orig_ret_ch_g03_ris_00..01`).
- **`orig_ret_ch_g04`** (refund inspection/partner post office vs physical branch receipt): `2` `return_policy` (`orig_ret_ch_g04_rp_00..01`, `POL-RET-002`) vs `2` `return_product_in_store` (`orig_ret_ch_g04_ris_00..01`).

*(Individual row `text_sha256` and `source_hash` values are locked inside `orig_fit2_return_contrast_extension.jsonl` and `dataset_lock_manifest.json` in the `-prep` bundle.)*

---

## 3. Baseline-vs-New Dataset Diff & Raw/Effective Exposure

| Metric / Split | Original Fit2 Baseline | Proposed Extension | Delta |
| --- | --- | --- | --- |
| Changed input files | — | `boundary_pos_train.jsonl`, `full_train_split.jsonl` only | `2 / 13` files (`11` bit-identical) |
| `boundary_pos_train` total (raw) | `181` | `199` | `+18` |
| `full_train_split` total (raw) | `11320` | `11338` | `+18` |
| Effective TRAIN total (`pos*4/5 + bitext*1 + neg*12`) | `13000` | `13080` | `+80` (`+0.62%`) |
| `return_policy` domain (raw / eff @ `4x`) | `11` / `44` | `21` / `84` | **`+10` raw / `+40` eff** |
| `return_product_in_store` domain (raw / eff @ `5x`) | `0` / `0` | `8` / `40` | **`+8` raw / `+40` eff** |
| `return_policy` total incl. Bitext `240` (raw / eff) | `251` / `284` | `261` / `324` | `+10` raw / `+40` eff |
| `return_product_in_store` total incl. Bitext `240` (raw / eff) | `240` / `240` | `248` / `280` | `+8` raw / `+40` eff |
| Bitext 46-class replay (`clean` + `noisy`) | `7360 + 3680` (`46/46`) | `7360 + 3680` (`46/46`) | `0` (bit-identical) |
| `CAL` (`pos=86, neg=48, bitext=690`) | `824` | `824` | `0` (bit-identical) |
| `EVAL` (`pos=122, neg=39, bitext_test=6690`) | `6851` | `6851` | `0` (bit-identical) |

---

## 4. Isolation Verification & Historical Baseline Overlap Disclosure

- **Extension Isolation (`audit_extension_isolation`):**
  - `0` `sample_id`, `parent_sample_id`, `group_id`, or normalized-text overlap against baseline TRAIN, CAL, EVAL, `v5-r2` inputs, or any frozen suite (`final24`, `sa156`, `noise420`, `oos80`, `ind36`, `old_sealed72`, `fresh34`, `pos175`, `neg51`, `bitext6690`, plus remaining `FROZEN_BENCHMARK_PATHS`).
  - Maximum surface similarity across all frozen suites + CAL/EVAL: **`max_jaccard = 0.3889`** (`< 0.55`), **`max_token_f1 = 0.5385`** (`< 0.65`).
- **Historical Baseline `exclude_noisy_test_overlap=False` Disclosure:**
  - Consistent with Original Fit2 (`run-records-faithful-fit2-20261113/stage2_inputs`), retaining `exclude_noisy_test_overlap=False` leaves **`3`** pre-existing `bitext_train_noisy` rows whose noised text normalizes to an eval row (`bitext_trn_aug_sample_031082_1`, `bitext_trn_aug_sample_001393_41`, `bitext_trn_aug_sample_020326_51`), with **`0`** `bitext_train_noisy` vs CAL overlap and **`0`** `bitext_train_clean` vs EVAL overlap. Retained intentionally unmodified to isolate a single experimental factor without bundling dataset-filtering changes.

---

## 5. Recipe Freeze, Hyperparameter Reconciliation & Causal Caveat

**Unchanged Original Fit2 Parameters (`train_boundary_candidate.run_fit_and_lock_candidate`):**
`fit_mode="fit2_supcon_energy"`, `batch_size=32`, `max_length=64`, `seed=42`, `label_smoothing=0.03`, `supcon (0.25, tau=0.12)`, `uniform_kl (0.80)`, `sup12_ceil (3.0, thr=0.18)`, `energy_margin (0.25, m=2.0)`, `neg_repeat=12`, `pos_repeat=4/5`, `min_temperature=1.0`, `enable_selective_rejector=False`.

**Causal Control Caveat:**
Original Fit2 (`f695b1fe...`) was fitted from Fit1 (`95a940b6...`) for `epochs=3, lr=2e-5`. Any warm-start continuation run initialized from converged Fit2 adds extra gradient epochs and full-dataset replay passes on top of `f695b1fe...`. Therefore, comparing a warm-start continuation run against untouched Original Fit2 is **not** a perfectly matched causal control (it confounds the 18-row return-channel TRAIN contrast delta with extra continuation optimization steps). A matched two-fit control from Fit1 is not authorized here.

**Explicit Options Requiring Coordinator / Worker B Sign-Off Before Any Fit (`selected_by_worker_a = null`):**
1. **Option A (Original Fit2 Stage-2 hyperparams):** `epochs=3, lr=2e-5` (exact match to Fit1→Fit2 schedule; higher continuation step budget on converged `f695b1fe...`).
2. **Option B (Historical continuation helper hyperparams):** `epochs=2, lr=1e-5` (lower step/LR perturbation for warm-start continuation from `f695b1fe...`; differs from Fit2 Stage-2 `epochs=3, lr=2e-5`).

Exact proposed future CLIs for both options (reading ONLY the archived `-prep/datasets` snapshot and calling `run_fit_and_lock_candidate(..., enable_selective_rejector=False)`) are recorded verbatim in `prep_manifest.json` under `hyperparameter_reconciliation.options`. **Training remains unauthorized until Worker B PASS and explicit coordinator release.**
