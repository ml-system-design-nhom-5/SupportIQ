# Worker C Zero-Delta Control Verification Audit (`fit2-orig-zero-delta-control-v1`)

**Reviewer:** Worker C (`review` / independent CAL verification)
**Target Control:** `fit2-orig-zero-delta-control-v1` (commit `70cf073447adc14f1b6378d41b7cab6b300d3168` on `minh`, A's audit: [2026-11-14-fit2-zero-delta-control-fit-a.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-zero-delta-control-fit-a.md))
**Scope:** Strictly read-only control integrity + CAL/canonical-TRAIN verification. **Zero** new fits, **zero** calibrator fitting, **zero** paid LLMs, **zero** holdout/OOD/full eval/unseen-gate inference.
**Verifier Script & Outputs:**
- Script: [verify_control_cal.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_zero_delta_control_review_c_20261114/verify_control_cal.py)
- Metrics JSON: [control_cal_comparison.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_zero_delta_control_review_c_20261114/control_cal_comparison.json)
- Manifest: [run_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_zero_delta_control_review_c_20261114/run_manifest.json)

---

## 1. Verdict & Executive Summary

- **Scientific Control Status Verified:** `is_promotion_candidate=false` (`CONTROL_CAL_DRIFT_OR_REGRESSION_DETECTED`), `cal_guard_passed=false` (`6/11` integer checks pass, `5/11` float drift/ceiling checks fail).
- **Independent Guard Reproduction:** Exact match (`max_guard_float_diff = 0.0 <= 3e-6`) against [cal_guard_report.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1/cal_guard_report.json); **no CAL guard bug found**.
- **`ModelContainer` Runtime Parity:** `134/134` boundary CAL rows checked, `0` intent mismatches, `max_confidence_abs_diff = 2.18e-6 <= 3e-6`.
- **Core Scientific Finding:** Adding `0` rows and continuing Stage-2 `fit2_supcon_energy` (`lr=2e-5`, `3` epochs, `T=1.0`, `enable_selective_rejector=false`) from `reconstructed-fit2-supcon-20261113` **is already sufficient** to trigger the exact same `5` CAL float regressions (`+0.025622` pos mean-max-prob, `+0.020045` esc34 mean-max-prob, `0.607555` esc34 max `sup12` mass, `0.734620` neg max `sup12` mass, `0.609309` neg max single `sup12` prob). Thus the `+18`-row return-channel delta is **not necessary** for CAL drift. However, `0`-delta continuation is **not proven to be the exclusive cause** of prior `+18`-row failures (`407` vs `409` batches/epoch, `1,221` vs `1,227` steps, `n=1` seed, sharp divergence on `esc34` wrong-prediction confidence `-0.046481` vs `+0.148055`/`+0.131582` and `neg_cal pred_sup12` `9` vs `10`/`11`, and unmeasured holdout/OOD behavior).

---

## 2. Independent Archive, Sidecar, Prep & Untouched Artifact Verification

| Artifact / Check | Result | Verified Detail / SHA-256 |
|---|---|---|
| Control archive (`fit2-orig-zero-delta-control-v1`) | **PASS (`6/6`)** | Inventory `ab01eb821e47923018adfbb6269ecdef1201ef21a1c58b6b7638cdabd8e3f337`; `model.safetensors` `904188aab6cb45d1150cbd5f0890ee06a1732177d0c7b2c62e43d54a05ffc0ee`; `calibration_manifest.json` `70e86f044d3f2f496bc5682e472a35e64d60ab4b51a2e6ade2757b75140c2c5e` |
| Control sidecar (`run-records-fit2-orig-zero-delta-control-v1`) | **PASS (`40/40`)** | Inventory `df5e33b608516763bfd29cfe8a13c316b832170c3b7b0ba49aa9f4d9c1e6b5f1`; `cal_guard_report.json` `4224d16e6f7d3dde6f2c87b64ea61e89d4c1ef6afb1efb6ee8691eb3d2f3e4c3` |
| Prep & Promotion Flag | **PASS** | `prep_manifest.json` `5ad2f3eb888979e6cd913850aa423c77cae1cc60b345b3326ee17fa0c7aa3b92`; `is_promotion_candidate=false` in both `prep_manifest.json` & `cal_guard_report.json`; no `orig_fit2_return_contrast_extension.jsonl`; zero `orig_ret_ch_*` IDs |
| Stage-2 Input Fidelity (`13` locked files) | **PASS (`13/13`)** | Bit-identical SHA-256 across all `13` files vs `run-records-faithful-fit2-20261113/stage2_inputs`; `11,320` raw / `13,000` effective (`11,812` pos + `1,188` neg) |
| Source Snapshot & LR Propagation | **PASS** | `source_snapshot/` matches `run_config.json` `source_hashes` and current disk (`0` diffs); `option_a`, `lr=2e-5` verified in `AUTHORIZED_FIT_PROFILES["option_a"]`, `prep_manifest.json`, `run_config.json`, and `cli_argv`; `epochs=3`, `batch_size=32`, `seed=42`, `min_temperature=1.0`, `enable_selective_rejector=false` |
| Historical Noisy-Bitext Overlaps | **UNCHANGED** | `noisy_vs_cal=0`, `noisy_vs_eval_total=3`, `noisy_vs_bitext_test=3`, `clean_vs_cal=0`, `clean_vs_eval_total=0` |
| Untouched Checkpoints | **PASS** | `orig_fit2`: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`; `prior_2e5`: `dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d`; `cand_lr5e6`: `b7a285479b853b5bed9ad1c67caaeed1b45107bd78bf8e53e23f6ec4f332feb2`; `serving`: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`; `fit1`: `95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6` |

---

## 3. Independent 11-Check Zero-Delta Control CAL Guard Reproduction

Post-`T=1.0` pure `float64` softmax on `cuda` reproduced every check in `cal_guard_report.json` (`max_guard_float_diff = 0.0 <= 3e-6`):

| Check | Rule / Limit | Recomputed (`zero_delta_control`) | Baseline (`orig_fit2`) | Result |
|---|---|---|---|---|
| `boundary_pos_cal_correct_count` | `>= 68` | `68` / `86` | `68` / `86` | PASS |
| `boundary_pos_cal_sup12_correct_count` | `>= 38` | `38` / `48` | `38` / `48` | PASS |
| `bitext_cal_correct_count` | `>= 687` | `689` / `690` | `689` / `690` | PASS |
| `boundary_pos_cal_sup12_conf_ge_070_count` | `>= 26` | `31` | `28` | PASS |
| `boundary_pos_cal_sup12_conf_ge_080_count` | `>= 24` | `29` | `28` | PASS |
| `boundary_neg_cal_pred_sup12_count` | `<= 9` | `9` | `9` | PASS |
| `boundary_pos_cal_delta_mean_max_prob` | `<= 0.015` | `+0.025622` (`0.711966`) | `0.686344` | **FAIL** |
| `boundary_pos_cal_esc34_delta_mean_max_prob` | `<= 0.015` | `+0.020045` (`0.691008`) | `0.670962` | **FAIL** |
| `boundary_pos_cal_esc34_max_sup12_mass` | `<= 0.55` | `0.607555` | `0.467362` | **FAIL** |
| `boundary_neg_cal_max_sup12_mass` | `<= 0.715693` | `0.734620` | `0.715693` | **FAIL** |
| `boundary_neg_cal_max_single_sup12_prob` | `<= 0.557692` | `0.609309` | `0.557692` | **FAIL** |

---

## 4. Four-Way Paired CAL & Canonical TRAIN Right/Wrong Comparison

### 4.1 CAL Positive Surfaces (`boundary_pos_cal` `n=86`, `sup12` `n=48`, `esc34` `n=38`, `bitext_cal` `n=690`)

| Surface | Metric | `orig_fit2` (`f695`) | `zero_delta_control` (`9041`, `+0`) | `prior_2e5` (`dc3e`, `+18`) | `cand_lr5e6` (`b7a2`, `+18`) |
|---|---|---|---|---|---|
| `pos_cal` (`86`) | Correct / Acc | `68` (`0.790698`) | `68` (`0.790698`) | `68` (`0.790698`) | `66` (`0.767442`) |
| `pos_cal` (`86`) | Right `mean_max_prob` | `0.732839` | `0.767703` (`+0.034864`) | `0.753907` (`+0.021068`) | `0.771944` (`+0.039105`) |
| `pos_cal` (`86`) | **Wrong `mean_max_prob`** | `0.510698` | **`0.501403` (`-0.009295`)** | **`0.603560` (`+0.092863`)** | **`0.568534` (`+0.057836`)** |
| `pos_cal` (`86`) | `mean_true_class_prob` | `0.592221` | `0.615244` (`+0.023023`) | `0.606338` (`+0.014117`) | `0.607450` (`+0.015228`) |
| `sup12` (`48`) | Correct / `>=0.70` / `>=0.80` | `38` / `28` / `28` | `38` / `31` / `29` | `38` / `34` / `29` | `36` / `33` / `29` |
| `sup12` (`48`) | Right / Wrong `mean_max_prob` | `0.739562` / `0.542566` | `0.772121` / `0.563021` | `0.772354` / `0.591276` | `0.801199` / `0.545928` |
| `esc34` (`38`) | Correct / `max_sup12_mass` | `30` / `0.467362` | `30` / **`0.607555`** | `30` / **`0.682218`** | `30` / `0.491472` |
| `esc34` (`38`) | Right `mean_max_prob` | `0.724323` | `0.762108` (`+0.037786`) | `0.730540` (`+0.006218`) | `0.736837` (`+0.012515`) |
| `esc34` (`38`) | **Wrong `mean_max_prob`** | `0.470862` | **`0.424381` (`-0.046481`)** | **`0.618916` (`+0.148055`)** | **`0.602444` (`+0.131582`)** |
| `esc34` (`38`) | `mean_true_class_prob` | `0.593392` | `0.615858` (`+0.022466`) | `0.595683` (`+0.002291`) | `0.600616` (`+0.007224`) |
| `bitext_cal` (`690`) | Correct / `all_mean_max_prob` | `689` / `0.977800` | `689` / `0.977043` | `689` / `0.976676` | `689` / `0.977113` |

### 4.2 CAL Negative (`boundary_neg_cal`, `n=48`) & Canonical TRAIN (`pos=181`, `neg=99`, `added_18=18`)

| Surface | Metric | `orig_fit2` (`f695`) | `zero_delta_control` (`9041`, `+0`) | `prior_2e5` (`dc3e`, `+18`) | `cand_lr5e6` (`b7a2`, `+18`) |
|---|---|---|---|---|---|
| `neg_cal` (`48`) | `pred_sup12_count` (net vs `orig`) | `9` (`0`) | **`9` (`+2 / -2`)** | **`10` (`+2 / -1`)** | **`11` (`+2 / -0`)** |
| `neg_cal` (`48`) | `mean_sup12_mass` | `0.248401` | `0.247651` | `0.250610` | `0.258908` |
| `neg_cal` (`48`) | `max_sup12_mass` / `max_single` | `0.715693` / `0.557692` | **`0.734620` / `0.609309`** | **`0.733993` / `0.582643`** | **`0.745128` / `0.589594`** |
| `pos_train` (`181`) | Correct / `all_mean_max_prob` | `181` / `0.979132` | `181` / `0.979789` | `181` / `0.979531` | `181` / `0.979782` |
| `neg_train` (`99`) | `pred_sup12` / `max_sup12_mass` | `0` / `0.222151` | `0` / `0.218654` | `0` / `0.219649` | `0` / `0.221119` |
| `added_18` (`18`) | Correct / `all_mean_max_prob` | `8/18` (`0.504559`) | `7/18` (`0.489361`) | `18/18` (`0.979646`) | `18/18` (`0.977994`) |

Row-level flips vs `orig_fit2` confirm a shared unanchored-continuation signature across all three continued runs: `cls_e34_avonl_cal_1_af025937dd54` flips to wrong in all 3, and `cls_neg_off_cal_finance_1_c16b2323f38a` + `bnd_neg_homonym_cal_0_b32c79aceec4` enter `pred_sup12` in all 3 (`zero_delta_control` exits 2 negatives to stay net `0`, whereas `prior_2e5` exits 1 and `cand_lr5e6` exits 0).

---

## 5. Scientific Assessment (Limits of Inference)

1. **Not necessary (`+18` rows not required for CAL drift):** `zero_delta_control` holds the `+18`-row delta at `0`, holds `enable_selective_rejector=false`, and preserves `13/13` Stage-2 inputs bit-for-bit, yet fails the same `5` CAL float checks. Source inspection ([train_boundary_candidate.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L1033-L1089)) confirms continued `fit2_supcon_energy` applies unanchored Stage-2 CE (`label_smoothing=0.03`) + SupCon (`0.25`) + negative KL/ceiling/energy for `3` extra epochs (`epoch 1->3 mean_loss 0.35475 -> 0.34606`), sharpening weights without a KL/logit anchor to `orig_fit2`.
2. **Not exclusive cause:** We **cannot** attribute prior `+18`-row regressions solely to Stage-2 continuation because:
   - Batch/step/schedule mismatch: `control` has `13,000` effective examples (`407` batches/ep, `1,221` steps) vs `13,080` (`409` batches/ep, `1,227` steps) in `+18` runs, changing `DataLoader` shuffle ordering, `get_linear_schedule_with_warmup` decay slope, and `neg_rng` draw alignment.
   - `n=1` seed (`seed=42`).
   - Sharp behavioral divergence on CAL: `zero_delta_control` lowered `esc34` wrong-prediction confidence (`-0.046481`) and held `neg_cal pred_sup12=9`, whereas both `+18` runs spiked `esc34` wrong confidence (`+0.148055` / `+0.131582`) and increased `neg_cal pred_sup12` (`10` / `11`).
3. **OOD / holdout unmeasured:** `fit2-orig-zero-delta-control-v1` has `is_promotion_candidate=false` and zero holdout/OOD evaluations; CAL drift does not isolate what would happen on held-out/OOD slices without gating those separately on an eligible candidate.

---

## 6. Proposed Next Original Fit2 Options (TRAIN / CAL Only — Proposal Only)

Both options start cleanly from sealed `reconstructed-fit2-supcon-20261113` (`f695...`) — never from any drifted continuation — and disallow unanchored LR sweeps or holdout-case patching:

| Dimension | Option A: Anchored Stage-2 Continuation (Recommended First) | Option B: Frozen-Encoder / Bounded Head + CAL Calibration / Rejector |
|---|---|---|
| **Mechanism** | Fine-tune `fit2_supcon_energy` with return-channel TRAIN contrast **plus** explicit teacher KL + logit L2 anchor to frozen `orig_fit2` on canonical Stage-2 positives/negatives + `esc34`-vs-`sup12` margin penalty on TRAIN. | Freeze `orig_fit2` transformer encoder (or all layers except classifier head + small L2 tether to `orig_fit2` head weights), fit return-channel delta, then fit `T >= 1.0` + bounded `selective_rejector` strictly on TRAIN/CAL logit geometry. |
| **Why it targets observed failure** | Directly removes the unconstrained Stage-2 continuation drift proven by `zero_delta_control` while letting representation adapt for the return channel (`added_18`). | Guarantees zero encoder drift on canonical `esc34`/`neg` representations (`sup12` mass ceiling stability), using TRAIN/CAL calibration to damp `esc34`/`neg` overconfidence. |
| **Main risk** | Too strong KL anchor suppresses `return_product_in_store` vs `return_policy` discrimination; weak anchor still leaks `esc34`/`neg` mass. | Frozen features may underfit subtle return-channel phrasing if `orig_fit2` embeddings already conflate `return_policy` vs `return_product_in_store`. |
| **Verification Gate** | Canonical TRAIN accuracy + `18`-row TRAIN check + strict read-only 12-check CAL guard (`<= 3e-6`) before any holdout/OOD eval. | Same strict TRAIN + read-only 12-check CAL guard (`T >= 1.0`, rejector CAL-only); run C full eval only if all 12 checks pass. |
