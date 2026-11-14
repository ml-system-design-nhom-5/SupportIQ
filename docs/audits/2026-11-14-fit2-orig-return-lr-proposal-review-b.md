# Worker B Independent Diagnosis & LR `5e-6` Proposal Review

- **Reviewed commit:** `9692a5d5a9cfc6999e7d0a94dbf664c82dff6bbd` (`minh`) — [diagnosis A](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-orig-return-fit-v1-diagnosis-a.md), [diagnose.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_orig_return_diagnosis_a_20261114/diagnose.py), [diagnosis_summary.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_orig_return_diagnosis_a_20261114/diagnosis_summary.json)
- **Crosschecked against:** Worker C frozen evaluation `957923bbfab54eb0f4288f9955385ce42074816f` ([evaluation C](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-orig-return-contrast-fit-v1-evaluation-c.md)), [train_boundary_candidate.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L990-L1207), [train_domain_candidate.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_domain_candidate.py#L434-L453), [routing.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/intent/routing.py#L237-L360), and [intent_policy.v2.json](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/config/policies/intent_policy.v2.json#L26-L46)
- **Verdict:** **PASS** (defensible for **minimal prep assignment only** with mandatory CAL-definition corrections below; **not** fit release — bounded fit permission remains coordinator-only)

---

## 1. Independent Crosscheck of Frozen Diagnosis (`9692a5d5`) & Runtime/Calibration Source

All reported exposure ratios, training loss logs, CAL forward metrics, temperature clamp behavior, and Worker C aggregate shifts reproduce cleanly (`<= 3e-6` CPU vs CUDA float rounding, `0` fits executed):

- **Negative exposure dilution & saturated hinge:** [train_boundary_candidate.py#L999-L1089](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L999-L1089) produces `13,080` effective rows/epoch on `v3-prep` (`852` domain pos + `11,040` bitext + `1,188` neg from `99 x 12` = `9.08%`, `409` batches at `bs=32`). On `fit-v1`, [fit_result.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/fit_result.json#L14-L36) shows `neg_loss_sum` saturated (`0.00873 -> 0.00854 -> 0.00853`, ~2.5% of total loss `0.36607 -> 0.34616`), while `pos_loss + supcon_loss` stayed ~97.5% of total loss.
- **`T = 1.0` positive-only Bitext clamp:** [fit_temperature_on_calibration_logits](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_domain_candidate.py#L434-L453) fits `T in [1.0, 2.5]` strictly on `cal_pos_rows = pos_cal (86) + bitext_cal (690)` (`776` rows, `88.9%` Bitext), ignoring `boundary_neg_cal` (`48` rows), pinning `T = 1.0` in both `f695b1fe` and `dc3e88e7` [calibration_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/calibration_manifest.json#L69-L75).
- **CAL & TRAIN forward-pass shifts (independently recomputed):**
  - `pos_train_added_18` (`n=18`): `acc 0.444444 -> 1.000000`, `mean_max_prob 0.504559 -> 0.979646`.
  - `boundary_pos_cal` (`n=86`): `acc` flat at `68/86` (`0.790698`), `mean_max_prob 0.686344 -> 0.722439` (`+0.036095`), `frac_ge_070 0.569767 -> 0.639535`.
  - `boundary_pos_cal_sup12` (`n=48`): `acc` flat at `38/48` (`0.791667`), `mean_max_prob 0.698522 -> 0.734630`, `frac_ge_070 0.583333 -> 0.708333`, `frac_ge_080 0.583333 -> 0.604167`.
  - `boundary_pos_cal_esc34` (`n=38`): `acc` flat at `30/38` (`0.789474`), `mean_max_prob 0.670963 -> 0.707041`, `max_sup12_mass 0.467363 -> 0.682219`.
  - `boundary_neg_cal` (`n=48`): `max_sup12_mass` (sum over 12 supported intents) `0.715693 -> 0.733995` (`0.733992` CUDA), `max_single_sup12_prob` (`max_neg_cal_supported12_prob`) `0.557692 -> 0.582646` (`0.582643` CUDA), `pred_sup12_count` `9/48 -> 10/48`.
- **Worker C non-bitext aggregate shifts (`n=1,245`):** Independently verified bit-exact vs [diagnosis_summary.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_orig_return_diagnosis_a_20261114/diagnosis_summary.json#L616-L678): `supported_12` (`830`) `0.738007 -> 0.760601` (`+0.022594`), `escalated_34` (`196`) `0.683697 -> 0.694738` (`+0.011041`), `ood_or_negative` (`219`) `0.184519 -> 0.192081` (`+0.007562`), `oos80` (`80`) `0.326856 -> 0.352431` (`frac >= 0.70` `0.1625 -> 0.2625`). Routing thresholds (`0.60–0.80`) verified in [intent_policy.v2.json#L28-L45](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/config/policies/intent_policy.v2.json#L28-L45).
- **Causal caveat respected:** No matched zero-delta control exists; the `lr=5e-6` proposal is an exploratory single-LR-factor candidate test vs `f695b1fe` and `fit-v1`, not causal isolation of the `18`-row delta. Candidate `dc3e88e7` remains unpromoted/archived and Original Fit2 `f695b1fe` remains active.

---

## 2. Defensibility of `lr=5e-6` Proposal & Required Exact CAL Definitions

The single-variable `lr=5e-6` proposal (`f695b1fe` init, unchanged `v3-prep` TRAIN/CAL datasets, `epochs=3`, `batch_size=32`, `seed=42`, `fit2_supcon_energy`, `T>=1.0`, rejector OFF, 1-fit stop rule, zero holdout rows copied) is **defensible**. However, **4 exact CAL definition fixes are required before A executes minimal prep**:

1. **Fix rounding bug on `boundary_pos_cal` accuracy floor:**
   - A wrote `acc >= 0.7907`, whereas exact baseline `68/86 = 0.7906976744... < 0.7907` (so tying baseline fails literal `>= 0.7907`).
   - **Required exact definition:** `correct_count >= 68` on `boundary_pos_cal` (`n=86`, `acc >= 68/86`), paired with `correct_count >= 38` on `boundary_pos_cal_sup12` (`n=48`, `acc >= 38/48`) and `correct_count >= 687` on `bitext_cal` (`n=690`, `acc >= 687/690 = 0.995652`).
2. **Close unbounded confidence-drift loophole & guard `esc34`:**
   - A's `"<= +0.015 unless boundary_pos_cal accuracy strictly improves"` removes any upper confidence cap if accuracy improves by `+1/86`.
   - **Required exact definition:** On `boundary_pos_cal` (`86`), enforce `delta_mean_max_prob <= 0.015` when `correct_count == 68`, and a strict bounded ceiling `delta_mean_max_prob <= min(0.025, 0.015 + 0.5 * (acc_cand - 68/86))` when `correct_count > 68`; additionally require on `boundary_pos_cal_esc34` (`38`): `delta_mean_max_prob <= 0.015` and `max_sup12_mass <= 0.55` (baseline `0.467363`, rejected `fit-v1` `0.682219`).
3. **Pin raw-text surface, post-`T` probability, and exact denominators (anti-all-abstain & negative bounds):**
   - Independent check found [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L49) `pseudonymize` alters `2/48` `boundary_neg_cal` rows (`0` in `pos_cal`/`bitext_cal`). Baseline numbers match **unpseudonymized raw text** at `T=1.0`, and future candidates may calibrate `T > 1.0`.
   - **Required exact formula:** Compute `P_T(c | x) = softmax(logits(x) / T)` using `T` from `calibration_manifest.json` on unpseudonymized locked `v3-prep/datasets/*`:
     - **Anti-all-abstain (`boundary_pos_cal_sup12`, `n=48`):** `sum_i (max_c P_T(c|x_i) >= 0.70) >= 26` (`26/48 = 0.541667`, baseline `28/48 = 0.583333`) AND `sum_i (max_c P_T(c|x_i) >= 0.80) >= 24` (`24/48 = 0.500000`, baseline `28/48`) — note this measures unconditioned top-1 probability coverage matching `diagnose.py`, hence pairing with `correct_count >= 38/48` above is mandatory so high-confidence wrong predictions cannot satisfy it alone.
     - **Negative CAL (`boundary_neg_cal`, `n=48`):**
       - Supported-12 mass ceiling: `max_i sum_{c in SUPPORTED_12} P_T(c|x_i) <= 0.715693` (baseline `f695b1fe`, vs `fit-v1` `0.733992`).
       - Supported-12 max-single-class ceiling: `max_{i, c in SUPPORTED_12} P_T(c|x_i) <= 0.557692` (baseline `f695b1fe`, vs `fit-v1` `0.582643`).
       - Negative-predicted-supported count: `sum_i (argmax_c P_T(c|x_i) in SUPPORTED_12) <= 9` (baseline `9/48 = 0.1875`, vs `fit-v1` `10/48`).
     - **Contrast floor (`pos_train_added_18`, `n=18`):** `correct_count >= 15` (`15/18 = 0.833333`).
4. **Gate Separation Rule:**
   - These CAL checks are strictly **a priori TRAIN/CAL stop checks** prior to evaluation and **never replace or relax** Worker C's frozen `10`-suite + `16`-criterion safety/utility acceptance gates (`zero_leak_*` + `5` utility floors). Existing `unseen36` is now **historical**; Worker C must author and freeze a fresh unseen gate after the fit completes.

---

## 3. Minimal Implementation Plan Review (`lr=5e-6` Support)

[run_orig_fit2_return_contrast_fit.py#L60-L93](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py#L60-L93) and `#L146-L148` currently hardcode `lr=2e-5` and fail closed on any other value. To support `lr=5e-6` **without weakening provenance or historical `Option A` immutability**:

- **Versioned profile config (no free-form LR):** Keep `"option_a"` (`lr=2e-5`) intact in a mapping (e.g., `AUTHORIZED_FIT_PROFILES["option_b_lr5e6"] = {..., "lr": 5e-6}`), require explicit `--profile` + matching `--lr 5e-6` CLI flags, and validate against `prep_manifest.json["authorized_fit_profile"]`.
- **New immutable prep bundle (`v4-prep`):** Because `scripts/run_orig_fit2_return_contrast_fit.py` and `prep.py` belong to the `19`-file `RELEVANT_SOURCE_PATHS` closure, archive a clean `run-records-fit2-orig-ret-channel-v4-prep` (preserving `v1`/`v2`/`v3-prep` and `fit-v1` untouched) with bit-identical `15` dataset artifacts (`full_train_split` `63254304...`, `full_cal_split` `dc8c7773...`), updated `19`-file `source_snapshot/` + `source_hashes`, unused run ID `fit2-orig-ret-channel-lr5e6-v1`, and post-fit read-only `cal_guard_report.json` logging using the corrected Section 2 formulas.
- **Independent verification status:** Read-only verification via `codegraph_explore` (no `.codegraph/` mutation) + independent `audit_diagnosis_a.py` recomputation on locked `f695b1fe`, `dc3e88e7`, `v3-prep`, and `1,245` Worker C predictions exited `0`. Await coordinator assignment for A minimal prep and Worker B pre-fit review before any training release.
