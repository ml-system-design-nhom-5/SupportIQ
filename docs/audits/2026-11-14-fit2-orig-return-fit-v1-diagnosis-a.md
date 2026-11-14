# Root-Cause Diagnosis & Minimal Next-Experiment Proposal: `fit2-orig-ret-channel-fit-v1` (Worker A, Zero-Fit)

- **Context & Verdict:** Worker C independent evaluation ([evaluation C](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-orig-return-contrast-fit-v1-evaluation-c.md), commit `957923bbfab54eb0f4288f9955385ce42074816f`) **`REJECT`**ed `fit2-orig-ret-channel-fit-v1` (`dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d`): all `5` utility floors passed (`final24 ans12 = 10/12`, `sa156 sup34 = 28/34`, `noise420 macro F1 = 0.862970`, `Gate = 283/420`, `Runner = 276/420`), while `7/16` safety gates failed (`pos175`, `neg51`, `oos80`, `ind36`, `sa156 mand63`, `bitext6690`, `unseen36`).
- **Active State Preserved:** Candidate `fit2-orig-ret-channel-fit-v1` is preserved unpromoted; Serving (`dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`), Original Fit2 (`f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`), Fit1 (`95a940b6...`), and `v1`/`v2`/`v3` preps remain untouched (`0` fits executed here).
- **Read-Only Evidence Artifact:** [diagnose.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_orig_return_diagnosis_a_20261114/diagnose.py) and [diagnosis_summary.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_orig_return_diagnosis_a_20261114/diagnosis_summary.json) (forward passes strictly on locked `v3-prep` TRAIN/CAL + aggregation of Worker C's frozen predictions; zero training/calibrator calls).

---

## 1. Observed Facts: Frozen Training Dynamics, TRAIN/CAL Behavior & Broad Aggregate Shifts

### 1.1 Training Loss Saturation & Negative Exposure Dilution (`stage2_fit2.log` vs `fit_result.json`)

| Run (Init -> Output) | Epoch | `mean_loss` | `pos_loss_sum` | `neg_loss_sum` | `supcon_loss_sum` |
| --- | --- | --- | --- | --- | --- |
| Original Fit2 (`Fit1 95a940b6 -> f695b1fe`, `13,000`/ep) | 1 | `0.88022` | `0.31068` | `0.42278` | `0.14676` |
| | 2 | `0.37035` | `0.26310` | `0.00916` | `0.09809` |
| | 3 | `0.35608` | `0.25600` | `0.00893` | `0.09115` |
| Option A `fit-v1` (`f695b1fe -> dc3e88e7`, `13,080`/ep) | 1 | `0.36607` | `0.26084` | `0.00873` | `0.09650` |
| | 2 | `0.34935` | `0.25266` | `0.00854` | `0.08816` |
| | 3 | `0.34616` | `0.25066` | `0.00853` | `0.08698` |

Observed structural ratios in [train_boundary_candidate.py#L999-L1089](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L999-L1089) (`diagnosis_summary.json`):
- **Effective exposures per epoch (`v3-prep`):** `13,080` total (`409` batches at `batch_size=32`): `11,040` Bitext + `852` domain positive vs `1,188` (`99` rows x `12`) boundary negatives (`9.08%` of examples; `~2.91` neg/batch vs `9.14%` / `2.92` in Original Stage-2).
- **Saturated hinge penalties on `neg_train_99`:** Before Option A even began, `f695b1fe` already had `mean_max_prob=0.02397`, `max_sup12_mass=0.22215` (barely above `ceil_thr=0.18`), and `mean_energy=-3.7856` vs `pos_energy=-6.640` (gap `2.85 > neg_energy_margin=2.0`, so `l_eng` hinged at `0.0`). Throughout all `1,227` steps (`3` epochs at `lr=2e-5`), `neg_loss_sum` stayed flat at `~0.0085` (`~2.5%` of loss), while `pos_loss + supcon_loss` (`~0.34`, `~97.5%` of loss) continued shrinking (`pos: 0.2608 -> 0.2507`, `supcon: 0.0965 -> 0.0870`).

### 1.2 Independent Locked TRAIN & CAL Forward-Pass Shifts (`f695b1fe` vs `dc3e88e7`)

| Locked `v3-prep` Split (`n`) | Metric | `orig_fit2` (`f695b1fe`) | `cand_fit_v1` (`dc3e88e7`) | Delta |
| --- | --- | --- | --- | --- |
| `pos_train_added_18` (`18`) | `acc` / `mean_max_prob` | `0.4444` / `0.5046` | **`1.0000`** / **`0.9796`** | `+0.5556` / `+0.4751` |
| `neg_train_99` (`99`) | `mean_max_prob` / `max_sup12` | `0.0240` / `0.2222` | `0.0234` / `0.2196` | `-0.0005` / `-0.0025` |
| **`boundary_pos_cal` (`86`)** | `acc` (unchanged!) | `0.790698` | `0.790698` | **`0.000000`** |
| | `mean_max_prob` / `frac>=0.70` | `0.686344` / `0.5698` | **`0.722439`** / **`0.6395`** | **`+0.036095`** / **`+0.0698`** |
| | `mean_margin` / `mean_entropy` | `0.637025` / `1.4796` | **`0.682247`** / **`1.3462`** | **`+0.045222`** / `-0.1334` |
| `boundary_pos_cal_sup12` (`48`) | `acc` / `mean_max_prob` / `frac>=0.70` | `0.7917` / `0.6985` / `0.5833` | `0.7917` / **`0.7346`** / **`0.7083`** | `0.0` / **`+0.0361`** / **`+0.1250`** |
| `boundary_pos_cal_esc34` (`38`) | `acc` / `mean_max_prob` / `max_sup12` | `0.7895` / `0.6710` / `0.4674` | `0.7895` / **`0.7070`** / **`0.6822`** | `0.0` / **`+0.0361`** / **`+0.2149`** |
| `bitext_cal` (`690`) | `acc` / `mean_max_prob` | `0.998551` / `0.9778` | `0.998551` / `0.9767` | `0.0` / `-0.0011` |
| **`boundary_neg_cal` (`48`)** | `mean_max_prob` / `mean_entropy` | `0.097638` / `3.6416` | `0.083921` / `3.6850` | `-0.0137` / `+0.0433` |
| | `pred_sup12_rate` / **`max_sup12_mass`** | `0.1875` (`9/48`) / `0.715693` | **`0.2083`** (`10/48`) / **`0.733992`** | `+1/48` / **`+0.0183`** |
| | manifest `max_neg_cal_supported12_prob` | `0.557692` | **`0.582643`** | **`+0.024951`** |

- **Why `temperature = 1.0` remained clamped (`cal_temperature_sweep`):** [fit_temperature_on_calibration_logits](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_domain_candidate.py#L434-L453) evaluates NLL strictly on positive `cal_pos_rows = boundary_pos_cal + bitext_cal` (`776` rows, `88.9%` clean Bitext trained with `label_smoothing=0.03` to `~0.977` confidence, `0` negative CAL rows). `cal_pos_nll` strictly worsens for `T > 1.0` on `cand_fit_v1` (`0.15066` at `T=1.0` vs `0.17326` at `T=1.10`, `0.22953` at `T=1.25`, `0.38294` at `T=1.50`), so `T` stays pinned at `min_temperature=1.0`. Even forcing `T=1.25` leaves `neg_cal_max_sup12_mass = 0.5829` while dragging `cal_pos_mean_max_prob` down `0.9485 -> 0.8701`.

### 1.3 Broad Aggregate Confidence Shifts Across Frozen Suites (Not Only Named Fails)

Aggregating Worker C's `1,245` non-bitext paired predictions (`diagnosis_summary.json`):
- **`supported_12` (`n=830`):** Mean confidence rose broadly **`0.738007 -> 0.760601` (`+0.022594`**, `64.6%` of cases increased), `frac >= 0.70`: `68.9% -> 73.0%`, `frac >= 0.80`: `61.2% -> 65.4%`. This directly drives utility gains (`noise420` `n=420`: `0.8245 -> 0.8491`, `ECE 0.0631 -> 0.0388`, Runner `+16`; `sa156 sup34`: `+3`) because marginal `0.62–0.79` supported predictions cross the `0.65–0.80` `decide_route` thresholds ([routing.py#L240-L348](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/intent/routing.py#L240-L348), [intent_policy.v2.json#L28-L41](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/config/policies/intent_policy.v2.json#L28-L41)).
- **`escalated_34` (`n=196`):** Mean confidence ALSO rose broadly **`0.683697 -> 0.694738` (`+0.011041`**, `59.2%` increased; `cand_pos122` `+0.0208`, `pos175` `+0.0152`, `sa156` `+0.0182`, `frac >= 0.80` `55.6% -> 57.1%`), even as `return_product_in_store` misclassifications dropped (`pred_sup12_count` `34 -> 21`). However, escalated inputs already mispredicted into `cancel_order` / `request_refund` just below the `0.80` threshold (`ind36` `g2-esc-06`: `0.7803 -> 0.8768`; `g2-esc-09`: `0.7814 -> 0.8886`) were pushed past `0.80` into `retrieve_draft`.
- **`ood_or_negative` (`n=219`) is bifurcated:** On synthetic in-template negatives matching `neg_train` (`cand_neg39`, `neg51`, `unseen36::ood`), median confidence decreased slightly (`median_delta = -0.00286`, `69.4%` non-increasing), **yet** on realistic natural-text `oos80` (`n=80`), mean confidence jumped **`0.326856 -> 0.352431` (`+0.025575`, `56.25%` increased)** and `oos80` **`frac >= 0.70` jumped `+10.0 pp` (`16.25% -> 26.25%`)**, pushing `oos-other_domain-16` (`0.4972 -> 0.7506 >= 0.70`) and `neg51` `nonretail_ood_eval_023` (`"federal tax return"` `return_policy` `0.5486 -> 0.8009`) past draft thresholds.

---

## 2. Observed Facts vs. Hypotheses & Causal Attribution Limits

| Evidence / Question | **Observed Fact** | **Working Hypothesis (Unverified Without Control)** |
| --- | --- | --- |
| **3-epoch continuation over converged `f695b1fe`** | `boundary_pos_cal` gained `+0.0361` mean confidence across both `sup12` and `esc34` at `0.0000` accuracy change; `oos80` `>=0.70` jumped `+10.0 pp`; `neg_loss` sat at `~0.0085` for all `3` epochs; `T=1.0` stayed locked (`88.9%` Bitext dominates positive NLL). | Running `1,227` additional gradient steps at `lr=2e-5` on `f695b1fe` sharpens classifier margins globally on domain-like queries while memorized `neg_train` fails to constrain off-manifold OOD or boundary `esc34` confidence. |
| **18-row return-contrast delta** | `pos_train_added_18` jumped `44.4% -> 100%` acc; `unseen36 ret_esc` jumped `0.111 -> 0.778`; `return_policy` absorbed `"federal tax return"` (`0.549 -> 0.801`) and `"archived legacy shipping policy"` (`0.452 -> 0.662`); `boundary_neg_cal` `max_sup12` rose `0.7157 -> 0.7340`. | Adding `+40` effective `return_policy` exposures without matched return-adjacent negatives widened the `return_policy` attractor basin on out-of-scope "return/policy" phrases. |
| **Causal Attribution Limit** | **No matched zero-delta continuation control exists.** | Cannot isolate what exact share of `oos80` / `g2-esc-06/09` / `noise420` confidence inflation comes from `3`-epoch continuation vs. the `18`-row delta. |

**Why utility improved alongside safety regressions:** Both `noise420` (`+16` Runner) and `g2-esc-06/09` / `oos-other_domain-16` sit in the same `0.50–0.79 -> 0.75–0.89` probability band governed by fixed `intent_policy.v2.json` gates (`0.65–0.80` with rejector OFF). Any mechanism that increases confidence broadly without widening separation between valid `SUPPORTED_12` vs. ambiguous `ESCALATED_34` / `OOD` trades safety leaks for supported draft coverage.

---

## 3. Minimal Next-Experiment Proposal (NOT Executed — Pending Coordinator Review)

- **Primary Recommendation: Single-Variable Low-Budget Continuation on Locked `v3-prep` (`lr = 5e-6` vs `2e-5`)**
  - **Rationale:** Changing ONLY `lr: 2e-5 -> 5e-6` (`0.25x` step size) directly tests the continuation-drift hypothesis in **one** run while preserving the verified KB-grounded `18`-row contrast fix (`v3-prep`).
    - **If `lr = 5e-6` eliminates broad `boundary_pos_cal` / `boundary_neg_cal` / `oos80` confidence inflation while preserving `pos_train_added_18` (`>=85%`) and `return_product_in_store` gains:** proves continuation step-size drove the safety leaks and yields a candidate directly.
    - **Counterevidence (if `return_policy` / `boundary_neg_cal` still inflates at `lr = 5e-6`):** isolates the `18`-row `return_policy` exposure (`40` eff) as needing paired return-adjacent hard negatives, NOT mere LR reduction.
  - **Clean Alternative (Pure Causal Attribution Only):** If the coordinator requires exact variance decomposition before any LR change, run **ONE matched zero-delta continuation control** (`0` added contrast rows using Original Stage-2 dataset `c0012ccb`, identical `f695b1fe` init, `epochs=3, lr=2e-5, batch_size=32, seed=42, T>=1.0, rejector=OFF`). (Note: useful purely for causal attribution; cannot fix `return_product_in_store`.)

### 3.1 Exact Protocol Specification for Primary Proposal (`fit2-orig-ret-channel-lr5e6-v1`, Zero Changes Until Approved)

1. **Source Base & Checkpoint:** Anchor on `minh` commit after coordinator approval of config/runner update (ancestor of `v3-prep`), starting weights **strictly** Original Fit2 (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`, `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`). Never warm-start from rejected `fit2-orig-ret-channel-fit-v1` (`dc3e88e7`).
2. **Unchanged Data & Recipe:** Consume locked `run-records-fit2-orig-ret-channel-v3-prep/datasets` bit-for-bit (`full_train_split` `63254304...`, `full_cal_split` `dc8c7773...`), preserving `STANDARD_INTENTS_46`, `263` generic `track_delivery` rows (`ambiguous_retained`), `3` disclosed inherited `bitext_train_noisy` overlaps (`0` delta overlaps), `epochs=3`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`.
3. **Single Variable Changed:** `lr = 5e-6` (requiring explicit Option-B/bounded-LR authorization & manifest schema update; fail-closed against unauthorized hyperparameter drift).
4. **Validation, Provenance & Archiving:** Same fail-closed provenance (`git merge-base --is-ancestor`, `--untracked-files=all` on `19` dependency-closure files, `source_snapshot/` SHA verification, `sidecar_sha_inventory.json`, `archive_sha_inventory.json`, `validate_calibration_manifest`, `audit_candidate_provenance`, `verify_reload_from_archive`, untouched Serving `dc7af8cf...`).
5. **TRAIN/CAL-Only Selection Guard (Anti-Overconfidence & Anti-All-Abstain Before Evaluation):**
   Candidate advances to Worker C evaluation **iff ALL pass on locked TRAIN/CAL**:
   - **No all-abstain collapse:** `boundary_pos_cal_sup12` (`48` rows) `frac >= 0.70` stays `>= 0.54` (baseline `0.5833`), `frac >= 0.80` stays `>= 0.50` (`0.5833`), and `bitext_cal` `acc >= 0.995` (`0.9986`).
   - **No uncompensated confidence inflation:** `boundary_pos_cal` (`86` rows) `mean_max_prob` drift vs `f695b1fe` (`0.6863`) is `<= +0.015` unless `boundary_pos_cal` accuracy strictly improves.
   - **Negative CAL ceiling guard:** `boundary_neg_cal` (`48` rows) `max_sup12_mass <= 0.7157` (must not exceed `f695b1fe`'s `0.715693`, vs `fit-v1`'s `0.733992`) and `max_neg_cal_supported12_prob <= 0.5577` (`f695b1fe`'s `0.557692`, vs `fit-v1`'s `0.582643`).
   - **Contrast learning floor:** `pos_train_added_18` accuracy `>= 0.833` (`>= 15/18`) and `boundary_pos_cal` accuracy `>= 0.7907`.
6. **Frozen Regression Criteria & Stop Rule (Worker C Evaluation):**
   - Retain all `5` utility floors (`final24 >= 10/12`, `sa156 >= 25/34`, `noise420 macro F1 >= 0.8573`, `Gate >= 267`, `Runner >= 260`), `0` leaks on `old_sealed72`, `fresh34`, `final24_active_unans8`, `ind36` (`0` vs `2` in `fit-v1`), plus net reduction in `oos80`, `neg51`, `pos175`, `sa156 mand63`, and `unseen36` (remembering existing `unseen36` is now **historical**; Worker C must author a fresh held-out check if evaluating).
   - **Stop Rule:** Maximum **1** authorized fit under this proposal; if TRAIN/CAL guard or Worker C safety gates fail, **STOP** continuation tuning from `f695b1fe` and escalate to re-anchoring Stage-2 from Fit1 (`95a940b6`) with `boundary_neg_cal`-aware calibration or targeted negative curriculum rather than repeating bounded LR sweeps.
