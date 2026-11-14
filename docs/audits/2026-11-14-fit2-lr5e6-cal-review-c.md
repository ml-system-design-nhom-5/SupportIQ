# Worker C Independent CAL Guard Verification — `fit2-orig-ret-channel-lr5e6-v1`

- **Definitive CAL Verdict:** **`CAL_GUARD_REJECT_DO_NOT_PROMOTE`** (**DO NOT PROMOTE**; `5/12` PASS, **`7/12` FAIL** — independently reproduced to `1.57e-6` float tolerance, `0` integer/status mismatches)
- **Scope:** Bounded CAL-only verification on `minh` (`440a6d59960905c0af7c543c97a94484faee27a2`, `64.2s`, CUDA+CPU). Zero full EVAL/OOD/held-out reruns, zero new fits/calibrators/threshold searches, zero paid LLM calls.
- **Preserved State:** Candidate archive & sidecar, Original Fit2 (`f695b1fe...`), active Serving (`dc7af8cf...`), prior `2e-5` candidate, `.local/ai.env`, datasets, and `.gitkeep` untouched.

---

## 1. Archive, Sidecar, Recipe & LR Propagation Verification (`PASS` — No Propagation Bug)

1. **Inventory Integrity (`0` mismatches):**
   - Archive `archive_sha_inventory.json` (`4d1f9204b8d8cd4a3f55543baec1d74b29f75c2253810591b1600013d9e49855`): `6/6` verified (`model.safetensors` = `b7a285479b853b5bed9ad1c67caaeed1b45107bd78bf8e53e23f6ec4f332feb2`, `calibration_manifest.json` = `a62c3a138cb6340c14c6e2ba20e97c81ee54a9dd7488249382546d07d75482da` with `T=1.0`, `min_temperature=1.0`, `selective_rejector.enabled=false`).
   - Sidecar `sidecar_sha_inventory.json` (`4b5f53e479115bb182cc9e9557c7ddea4b7f1b2bbd801f4cd96089b48a7c69b5`): `41/41` verified; `inputs_sha256_inventory.json` (`89bb77cb9f0c2111185ab938e875c493be8a9a86ab8700412f33f7db191190dc`): `15/15` verified; `v4-prep` sidecar: `39/39` verified; `cal_guard_report.json`: `01d4b9956c563fba64512aa92ff3f1daf12cd732b8fb9d630e993f69a44613a4`.
   - Baselines unchanged: Original Fit2 init `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, Serving `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`; `source_snapshot/` vs `run_config.json` & HEAD: `0` mismatches.
2. **Real Optimizer & LR `5e-6` Propagation Verified:**
   - `AUTHORIZED_FIT_PROFILES["lr5e6"]["lr"] == 5e-6` → `validate_profile_settings` fail-closed (`abs(lr - 5e-6) <= 1e-12`) → `run_authorized_fit` passes `lr=float(profile_cfg["lr"])` → `run_fit_and_lock_candidate` constructs `torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)` + `get_linear_schedule_with_warmup(0.10 * total_steps)` (`epochs=3`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `train_total_examples=13080`). Actual LR propagated as **`5e-6`** (not silent `2e-5`).
3. **Inherited Overlap Disclosure (unchanged):**
   - Same `3` canonical `bitext_train_noisy` vs `bitext_test_6690` normalized-text overlaps inherited from Original Fit2 (`test_idx=203` `sample_001360`, `3137` `sample_020916`, `4685` `sample_031234`), `0` added overlap from the 18-row contrast extension.

---

## 2. Independent CAL Guard Recomputation, Code Audit & Tolerance Check

- **Exact agreement:** Independent CPU `float64` & CUDA `float64` forward passes over raw unpseudonymized locked surfaces (`pos_cal=86` [`sup12=48` + `esc34=38`], `bitext_cal=690`, `neg_cal=48`, `added_18=18`; post-`T=1.0` softmax) reproduced `cal_guard_report.json` with `0` integer mismatches, `0` status flips, `cpu_vs_gpu_cand_passed_equal=true`, and max CPU-vs-sealed float diff **`1.571724e-06`** (`<= 3e-6` tolerance; GPU vs sealed matches to `<= 2.1e-7` on deltas and exact on `esc34_max_sup12_mass`/`neg_cal` maxima).
- **`ModelContainer` runtime parity (134 rows: `pos_cal` + `neg_cal`):** `0` intent mismatches across all 3 models (`orig_fit2` max conf diff `1.82e-6`, `cand_lr5e6` `2.11e-6`, `prior_2e5` `3.39e-6`).
- **Classified code/methodology observations (no blocking guard bug):**
  1. *Benign cosmetic provenance mismatch (`low`, non-blocking):* `candidate_provenance_manifest.json` reports `token_truncation_audit.train_all.count = 11320` instead of `11338` because `audit_token_truncation` reads the baseline repo split rather than `prep/datasets/full_train_split.jsonl`; the real optimizer loop consumed locked `inputs/boundary_pos_train.jsonl` (`+18` rows → `13,080` effective examples, verified `18/18` accuracy).
  2. *Confidence drift formula note (`methodological`, non-blocking):* `_summarize_positive_surface` averages `mean_max_prob` across all `86` (`pos_cal`) / `38` (`esc34`) rows regardless of correctness. Thus wrong-intent high-confidence flips (e.g. `cls_e34_avonl_cal_1_af025937dd54`: *"Is this cosmetic bundle sold online via web checkout as well as in retail booths?"* flipping `availability_online @ 0.125375` → `return_product_in_store @ 0.834627`, `+0.709252`) contribute to `delta_mean_max_prob`. Regardless, independent `neg_cal` (`11/48 > 9`, `max_sup12_mass`, `max_single_sup12`) and `pos_cal` accuracy drops (`66/86 < 68`, `sup12 36/48 < 38`) still fail cleanly.

---

## 3. Baseline vs Prior `2e-5` vs `lr=5e-6` CAL Comparison (No Full Eval Rerun)

Both continuation candidates (`2e-5` and `5e-6`) fail the frozen CAL guard checks, confirming lower LR alone did not cure CAL confidence inflation or OOD `sup12` leakage (`tol = 3e-6`):

| CAL Guard Metric / Check | Rule | `orig_fit2` (`f695b1fe`) | `prior_2e5` (`dc3e88e7`, eval REJECT `7/16`) | `cand_lr5e6` (`b7a28547`) | `lr5e6` Status |
| --- | --- | --- | --- | --- | --- |
| `pos_cal_correct_count` (`n=86`) | `>= 68` | `68` (`0.686344`) | `68` (`0.722439`) | **`66`** (`0.724639`) | **FAIL** |
| `pos_cal_sup12_correct_count` (`n=48`) | `>= 38` | `38` (`0.698522`) | `38` (`0.734630`) | **`36`** (`0.737381`) | **FAIL** |
| `bitext_cal_correct_count` (`n=690`) | `>= 687` | `689` | `689` | `689` | PASS |
| `pos_train_added_18_correct` (`n=18`) | `>= 15` | `8` (`0.504559`) | `18` (`0.979646`) | `18` (`0.977994`) | PASS |
| `pos_cal_sup12_conf_ge_070` (`n=48`) | `>= 26` | `28` | `34` | `33` | PASS |
| `pos_cal_sup12_conf_ge_080` (`n=48`) | `>= 24` | `28` | `29` | `29` | PASS |
| `neg_cal_pred_sup12_count` (`n=48`) | `<= 9` | `9` | `10` (CAL FAIL) | **`11`** | **FAIL** |
| `pos_cal_delta_mean_max_prob` | `<= 0.015` | `0.0` | `+0.036095` (CAL FAIL) | **`+0.038295`** | **FAIL** |
| `pos_cal_esc34_delta_mean_max_prob` | `<= 0.015` | `0.0` | `+0.036078` (CAL FAIL) | **`+0.037581`** | **FAIL** |
| `pos_cal_esc34_max_sup12_mass` | `<= 0.55` | `0.467363` | `0.682219` (CAL FAIL) | `0.491473` | PASS |
| `neg_cal_max_sup12_mass` | `<= 0.715693` | `0.715693` | `0.733995` (CAL FAIL) | **`0.745129`** | **FAIL** |
| `neg_cal_max_single_sup12_prob` | `<= 0.557692` | `0.557692` | `0.582646` (CAL FAIL) | **`0.589595`** | **FAIL** |

- **Representative CAL failure rows (`cand_lr5e6` vs `orig_fit2`):**
  - `cls_neg_cmi_cal_can_rqr_pmth_1_e84a3760e441` (`compound_multi_intent` *"Please abort my unpacked purchase, file the money-back request, and tell me which e-wallets you accept."*): `cancel_order` `sup12_mass` `0.715693 -> 0.745129` (`2e-5`: `0.733995`), max single `0.557692 -> 0.589595` (`2e-5`: `0.582646`).
  - `bnd_neg_homonym_cal_0_b32c79aceec4` (*"How do freelancers submit quarterly state tax return forms before April?"*): `orig` `submit_product_feedback @ 0.0496` → `lr5e6` `return_policy @ 0.1682` (`sup12_mass 0.2261 -> 0.3321`), matching `2e-5`'s tax-"return" attraction.
  - `cls_rpr_qc_inspection_2_80de0abcbaeb` (*"Why might warehouse quality control reject a returned package on arrival?"*): `orig` `return_product @ 0.5699` → `lr5e6` misclassified `return_policy @ 0.4100`.

---

## 4. Scientific Limitations & Recommended Next Direction (Proposal Only)

- **Why no causal claim can isolate `5e-6` or `+18` rows yet:** Both `2e-5` and `5e-6` warm-started from an already-converged Original Fit2 checkpoint (`f695b1fe`) and ran `3` fresh `AdamW` epochs + linear warmup across `13,080` examples while fitting `T >= 1.0` (`min_temperature=1.0`), with no matched zero-added-data continuation control. Thus, we cannot claim that nothing on this family could improve — only that **lowering LR alone (`2e-5 -> 5e-6`) under 3-epoch warm-start continuation did not solve CAL confidence inflation or OOD `sup12` leakage**.
- **Recommended next direction (do not execute more heuristic warm-start LR sweeps):**
  1. **Run a controlled causal ablation first:** compare a **single-stage fit from `distilbert-base-uncased`** with the `+18` rows baked into Original Fit2's recipe vs a **matched `0`-delta `lr=5e-6` continuation control** from `f695b1fe` to separate continuation optimization drift from dataset effects.
  2. **Fix calibration/OOD at the head or regularizer rather than full-backbone LR scaling:** replace `min_temperature=1.0`-clamped continuation with **logit/KL-anchor distillation toward `orig_fit2` on non-target classes**, and/or a **decoupled post-hoc OOD gate / adapter / Platt-or-temperature recalibration** tuned on `cal_split` without touching backbone weights for 18 rows.

---

## 5. Worker C Verification Artifacts (`artifacts/evaluation/fit2_lr5e6_cal_review_c_20261114/`)

| Artifact | SHA-256 |
| --- | --- |
| `verify_cal_guard.py` | `a1a38a1d501e293fc278a2f9105cc134b37ecdd07076d4a796b819335b29cfe3` |
| `cal_verification_summary.json` | `5075aa2894746c032ab269d30a4d14422f3c2278acae84cd2bef75dfbefa118e` |
| `cal_case_predictions.jsonl` | `a4af3cd8a57c8777ab90ab8671cfbbeab1e3e53ed2dd91dbcd2463615b452bc5` |
| `run_manifest.json` | `7f084338f552591da9f5cb90fda710b9e5e53c7679e6bba6bb2394aebf76569c` |
