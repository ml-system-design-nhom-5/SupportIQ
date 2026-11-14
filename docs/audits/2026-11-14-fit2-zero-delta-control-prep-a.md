# Fit2 Matched Zero-Delta Control Prep Audit (Worker A)

- **Scope & Status:** Strictly **ZERO-FIT PREP ONLY** (`fits_executed: 0`, optimizer/calibrator/holdouts untouched, `is_promotion_candidate: false`).
- **Prep Run ID / Schema:** `fit2-orig-zero-delta-control-v1` (`orig_fit2_zero_delta_control_prep.v1`)
- **Immutable Prep Bundle:** [`artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep`](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep)
- **Frozen Source+Test Git Commit:** `118196095ee040d3606fc6960a2fa94ae8d89957`
- **`prep_manifest.json` SHA-256:** `5ad2f3eb888979e6cd913850aa423c77cae1cc60b345b3326ee17fa0c7aa3b92`
- **`sidecar_sha_inventory.json` SHA-256:** `0200ab011fd5afdf280c0c1c1dac5e46d85a81fe381e5ef9bc39d599b7c3952c`
- **Test Proof:** `59 passed, 2 deselected` (11/11 unit tests in `tests/unit/test_orig_fit2_return_contrast_prep.py` + 48 tests in `test_boundary_contrast_fit.py`, `test_faithful_fit2_entrypoint.py`, `test_gate_contract_b.py`, `test_task_c_evaluation_gates.py`, `test_model_provenance.py`); `--validate-only` passed (`fits_executed: 0`).

---

## 1. Control Design & Anchors

- **Starting Initializer:** Original Fit2 [`reconstructed-fit2-supcon-20261113`](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/reconstructed-fit2-supcon-20261113) (`model.safetensors` SHA-256 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `T=1.0`, `selective_rejector=False`, `num_labels=46`). Neither rejected candidate weights nor fresh `distilbert-base` are used.
- **Serving Anchor (Unmodified):** `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`.
- **Locked Hyperparameters (`option_a`):** `epochs=3, lr=2e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy", min_temperature=1.0, enable_selective_rejector=False` (`loss`, `neg_repeat=12`, `supcon_weight=0.25`, `calibrator`, and optimizer schedules untouched).
- **Dataset Delta:** Strictly **0 added rows** (`extension_pos_train_added = 0`, `orig_fit2_return_contrast_extension.jsonl` absent). `datasets/` holds 14 files total: `dataset_lock_manifest.json` (`orig_fit2_zero_delta_control_lock.v1`, `delta_absent=True`) plus all 13 files **bit-identical** to `artifacts/models/candidates/run-records-faithful-fit2-20261113/stage2_inputs`:
  - `domain_pos_train = 181` (vs `199` in `v3`/`v4`)
  - `full_train_split_rows = 11,320` (vs `11,338` in `v3`/`v4`)
  - `effective_train_total = 13,000` (vs `13,080` in `v3`/`v4`; exposure delta = `0`)
  - `historical_bitext_train_noisy_vs_eval_norm_overlap_count = 3` (`bitext_trn_aug_sample_031082_1`, `bitext_trn_aug_sample_001393_41`, `bitext_trn_aug_sample_020326_51`; `0` in clean/CAL), retained bit-for-bit from Original Fit2 `stage2_inputs`.

| Bit-Identical Stage-2 File (`13/13` matched) | SHA-256 |
| --- | --- |
| `split_manifest.json` | `44eebb254c3b6d472dfda68d07c0d36efe5390113b04802890d5155033318387` |
| `boundary_pos_train.jsonl` | `c0f0213bb4e9f3771a223d04c1621018c47945f72a05b3f6d708b9ae5b26a0af` |
| `boundary_neg_train.jsonl` | `6cce9f4a1dbaacce45c487073ba234ef677655dbf2174f67b614e8dd885ac56f` |
| `boundary_pos_calibration.jsonl` | `265126f0372269de58abdf2fee74d541d914d5409a98bc6946c03909e29bbab3` |
| `boundary_neg_calibration.jsonl` | `ecb39a6849992c42fb6be1bb2fa784cb1902002268c414d5962cecada46769db` |
| `boundary_pos_evaluation.jsonl` | `0833c7b89d4a59ada66a2c20bff30a49992c5e066a08bb5954616f49047dc036` |
| `boundary_neg_evaluation.jsonl` | `f65af533a081b0a972406d261cf6a63e208f2254258d31364fbefcfc77896a59` |
| `bitext_train_clean.jsonl` | `36f6e74f7dd009459e0a79710197dc44437ca5539d3b5a46b1e014f5b3bafea0` |
| `bitext_train_noisy.jsonl` | `5233abffaf4c6dbf78c548f3af06cb14aa96f2063611d1b61eb4a6be59573261` |
| `bitext_cal.jsonl` | `54e9e86ae6ae076a9245fb5d3af60d1ce28c345fe492200824fe26078a83a3a9` |
| `bitext_test_6690.jsonl` | `c2279c30a6e7a9fde7488ea78d80a05fa560eb4ea9c02c746ffd87f6767c50b8` |
| `full_train_split.jsonl` | `c0012ccb4b1eb695470966b1e17c2cd0f5f92cf538782ba132410ebfbf5660bc` |
| `full_cal_split.jsonl` | `dc8c7773db46a1bbebcdf67b83c640b9635a4724f0c262dd9fa61ede3c139672` |

---

## 2. CAL Guard Control Mode & Verified Worker C Caveats

- **Control CAL Mode (`matched_zero_delta_control_11_checks`):** Evaluates the exact same 11 non-extension CAL checks and `3e-6` tolerance (no loosened thresholds), omitting **only** `pos_train_added_18_correct_count >= 15` because extension rows do not exist (`cal_guard_mode="control"`). Emits `CONTROL_CAL_NO_REGRESSION_SCIENTIFIC_ONLY` or `CONTROL_CAL_DRIFT_OR_REGRESSION_DETECTED` (`is_promotion_candidate: false`).
- **Caveat 1 (`mean_max_prob` definition — verified on CAL only):** `_summarize_positive_surface` computes `mean_max_prob` across **all** `86` / `38` rows regardless of prediction correctness. Using frozen `cal_attribution_breakdown.v1` on `boundary_pos_cal` (`86`), `sup12` (`48`), and `esc34` (`38`):

| Model (Weights SHA prefix) | `pos_cal` corr | `pos_cal` all `mmp` | `pos_cal` corr `mmp` | `pos_cal` incorr `mmp` | `esc34` corr | `esc34` all `mmp` (Δ) | `esc34` corr `mmp` (Δ) | `esc34` incorr `mmp` (Δ) | Control 11-check Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `orig_fit2` (`f695b1fe`) | `68/86` | `0.686344` | `0.732839` | `0.510698` | `30/38` | `0.670962` (`—`) | `0.724323` (`—`) | `0.470862` (`—`) | Baseline anchor |
| `prior_2e5` (`dc3e88e7`) | `68/86` | `0.722439` | `0.753907` | `0.603560` | `30/38` | `0.707041` (`+0.036078`) | `0.730540` (`+0.006218`) | `0.618916` (`+0.148055`) | FAIL (`6/11` failed) |
| `cand_lr5e6` (`b7a28547`) | `66/86` | `0.724639` | `0.771944` | `0.568534` | `30/38` | `0.708544` (`+0.037581`) | `0.736837` (`+0.012515`) | `0.602444` (`+0.131582`) | FAIL (`7/11` failed) |

  Notice that in both prior candidates, `esc34` `all_mean_max_prob` drift (`+0.0361` / `+0.0376`) came disproportionately from **incorrect** predictions (`+0.1481` / `+0.1316`) rather than confident correct predictions (`+0.0062` / `+0.0125`), and `cand_lr5e6` also dropped `2` correct `sup12` rows (`38/48 -> 36/48`) and raised `boundary_neg_cal` `pred_sup12` (`9 -> 11`). False-causal attribution guardrail: these are read-only CAL observations on `+18`-row candidates; causal separation requires executing this 0-delta control.
- **Caveat 2 (`token_truncation_audit.train_all`):** In this zero-delta control, `token_truncation_audit_max_length_64.train_all.count` is truthfully `11320` (matching `full_train_split.jsonl = 11320`). In untouched historical sealed `fit-v1` and `lr5e6-v1`, `candidate_provenance_manifest.json` also logged `train_all.count = 11320` alongside `11338` actual input rows because [`train_boundary_candidate.py`](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L1260) reads the static field `token_truncation_audit_max_length_64` copied from `dataset_lock_manifest.json` (cosmetic provenance artifact only; sealed archives untouched).

---

## 3. Frozen Attribution Hypotheses & Quoted Future CLI (NOT Executed)

1. **If `fit2-orig-zero-delta-control-v1` exhibits the same CAL drift (`boundary_neg_cal` `pred_sup12 > 9` / `max_sup12_mass` drift and/or `pos_cal` / `esc34` `mean_max_prob` drift > `0.015`):** Continuation optimization of converged `f695b1fe` for 3 extra epochs at `lr=2e-5` (even with 0 added data) causes the CAL regression — isolating the failure to the continuation-optimization regime rather than the 18 return-contrast rows.
2. **If `fit2-orig-zero-delta-control-v1` passes all 11 non-extension CAL checks (`CONTROL_CAL_NO_REGRESSION_SCIENTIFIC_ONLY`):** Continuation optimization at `lr=2e-5` alone does NOT reproduce the regression, attributing `prior_2e5`'s `6/11` failure to interaction with the `+18` return-contrast rows / upsampled schedule (`80` effective rows).

Exact quoted runner CLI (**NOT executed here**, gated behind review/coordinator release):

```powershell
.venv/Scripts/python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep --run-id fit2-orig-zero-delta-control-v1 --profile option_a --epochs 3 --lr 2e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --run-authorized-fit
```
