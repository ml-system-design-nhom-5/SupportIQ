# Task A Follow-up: Offline CPU-Only Class-Conditional `[CLS]` Centroid & Density Rejection Feasibility Report

- **Follow-up to:** Commit `c6cae7a` (rejected solely on `una-product_information-01` in independent gate commit `8d9b3e0`)
- **Generated:** `2026-11-13T08:27:56+00:00` (CPU-only wall-clock: `345.21s`, density fit: `122.265s`)
- **Primary Result:** **NEGATIVE / DO NOT IMPLEMENT `selective_calibration.v2` FROM `[CLS]` DENSITY.** Post-hoc train-derived `[CLS]` cosine-centroid (`diag1_cosine_centroid_gate`) and tied-covariance Mahalanobis (`diag2_mahalanobis_density_gate`) rejection gates on top of frozen `95a940b6` **do not safely resolve the safety/OOD/multi-intent gap without regression or overlap-driven blanket refusal**.
- **Serving Status:** **NO serving swap.** Production/serving baseline (`dc7af8cf...`) and locked `95a940b6` weights/manifests remain completely untouched.

---

## 1. Non-Mutation & Split / Hash Lineage Verification

All locked weights, manifests, runtime code (`apps/`), evaluation gates (`pipeline/evaluation/classifier_acceptance_gate.py`), and policy/KB assets remained byte-identical before and after analysis.

### Locked Model & Manifest SHA-256
| Artifact | Role | SHA-256 |
|---|---|---|
| `artifacts/evaluation/task_a_closure_20261113/candidate_model/model.safetensors` | Locked Candidate (`95a940b6`) | `95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6` |
| `artifacts/evaluation/task_a_closure_20261113/candidate_model/calibration_manifest.json` | Candidate Calibration Manifest | `6c5487c049a5e184f49a44024d6e1efe9bd2c6edca3202821bc0da82bba76bbe` |
| `artifacts/evaluation/task_a_closure_20261113/candidate_model/candidate_provenance_manifest.json` | Candidate Provenance Manifest | `68738b71d926d67e5f55a054f59b3d47e9a7053754cb73849311174c7ddb42a9` |
| `artifacts/models/trained/distilbert-supportiq/model.safetensors` | Serving Baseline (held) | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |

### Data & Probe Lineage (`suite_role` Separation)
- **Bitext splits (`bitext_train_cal_disjoint = true`):**
  - `cleaned.csv` SHA-256: `8BC10CFA056371BDECB3394BFD4C75EEE7E10022ACE5071833ECD140B2D75846`
  - `splits.csv` SHA-256: `1D366E898F6BA68BE46C5CA0F9059E9862FAD1D7BAFE350D9CDD310DD3E0A04C`
  - Train density sample: `5,520` Bitext `train`-only rows (`120` per class x `46` classes) + `138` `closure_positive_train` (`5,658` positive total) + `75` `closure_negative_train`.
  - Calibration selection sample: `230` `bitext_cal` rows + `66` `closure_positive_calibration` + `42` `closure_negative_calibration`.
- **Closure dataset file hashes:**
  - `closure_positive_train` (`138`): `757A7AC1CE147A0AFB5A061AF0D048B0122800AACAA49A11C188373E6A2C968C`
  - `closure_negative_train` (`75`): `52767989575DEE1D0DE9C0C7F114CFF7A61EDC7FCAA1B5A21F3EE86705932772`
  - `closure_positive_calibration` (`66`): `773E2316B6964D0DCFB518C2F4246EA225C1D99BC52D00E9170B416B2C461FF7`
  - `closure_negative_calibration` (`42`): `033E0ED66DF9B9E6C3FB201D90695748F9ACB74F1554FC180B64DCB2CCE88B05`
  - `closure_positive_evaluation` (`102`): `472CC60DDBD8836EF3E9E37A57D0397CD9AA097CD05B7250A8373161B65CD646`
  - `closure_negative_evaluation` (`33`): `D7F6CD0E2A692BB134613619E801CFD6BE94D5A6B26245AA19770A75ECDE90D2`
  - `closure_combined_train` (`213`): `4084FDD402EAF641A9AB5A8BD2563BAEB81EEF7E377217B06E4FEEB4ECFA2853`
  - `closure_combined_calibration` (`108`): `D7D88E77991EE94062E8D4CA668359C6F18BA75158922581593D0A6AAFC77219`
- **Fresh Unseen Probe (`suite_role = "fresh_unseen_probe"`):**
  - `fresh_probe_positive.jsonl` (`78` = `36` `SUPPORTED_12` incl. `3` `human_agent`, + `42` `ESCALATED_34` across `14` families): SHA-256 `c6486f75f38fd283539157a1ce82ae212ff9dfe76f0dfeeffd9c8301a321e800`
  - `fresh_probe_negative.jsonl` (`45` = `18` `compound_multi_intent`, `12` `unsupported_product_or_merchant`, `9` `underspecified_ambiguous`, `6` `off_domain_unrelated`): SHA-256 `9d2e14513ae72ac24c6a29db29345eb9a809874e0cac0aa8adab82d1692ef45f`
  - Disjointness audit: `0` exact normalized matches and `flagged_count = 0` against `1,074` prior closure/calibration rows (`max_token_f1 = 0.6452`, `max_jaccard = 0.4762`, `max_word_tfidf_cosine = 0.4142`, `max_char_tfidf_cosine = 0.5521`), against `1,009` frozen benchmark rows (`max_token_f1 = 0.5714`, `max_jaccard = 0.4000`, `max_word_tfidf_cosine = 0.3963`), and against Bitext `cleaned.csv` (`0` exact matches).
- **Previously Seen Development Suites (`suite_role = "already_seen_development"`):**
  - `closure_positive_evaluation` (`102`), `closure_negative_evaluation` (`33`), `ml_noise_420` (`420`), `ml_oos_80` (`80`), `system_acceptance_156` (`156`), `final_acceptance_24` (`24`), and `bitext_test_6690` (`6,690`, `4,928` `other_34`) are all strictly labeled `already_seen_development`.

---

## 2. Two CPU-Only Diagnostics Evaluated (Calibration-Only Tuning)

All centroids, cosine stats (`pred_cos`, `pred_cos_z`, `cos_esc_margin`, `cos_neg_margin`, `sup11_2nd_cos_gap`), and tied within-class `LedoitWolf(assume_centered=True)` precision matrix (`shrinkage = 0.06914`) were fit **strictly on `train`**. Logistic combiners (`C in [0.05..2.0]`) and thresholds (`tau`) were selected **strictly on `calibration`**:

| Diagnostic | Feature Keys | Selected `(C, tau)` | Cal `sup11` Draft (`n=33`) | Cal `esc34` Unsafe | Cal `neg` False Draft (`n=42`) |
|---|---|---|---|---|---|
| **Baseline Linear (`95a940b6`)** | `cls_l2_plus_logit_geometry_v1` (776d) | locked `tau = 0.74` | — | — | — |
| **Diag 1: Cosine Centroid Gate** | `linear_logit`, `pred_cos`, `pred_cos_z`, `cos_esc_margin`, `cos_neg_margin`, `sup11_2nd_cos_gap` | `C = 0.15`, `tau = 0.58` | `19` raw / `15` corr | `0` | `2` |
| **Diag 2: Tied Mahalanobis Gate** | `linear_logit`, `d2_pred_z`, `mahal_esc_margin`, `mahal_neg_margin` | `C = 0.05`, `tau = 0.50` | `19` raw / `15` corr | `0` | `2` |

---

## 3. Side-by-Side Evaluation Comparison

### A. Fresh Unseen Probe (`suite_role = "fresh_unseen_probe"`, 78 pos + 45 neg)
| Metric | Baseline Linear (`95a940b6`) | Diag 1: Cosine Centroid | Diag 2: Tied Mahalanobis |
|---|---|---|---|
| `SUPPORTED_11` correct draft / total (`n=33`) | `11 / 33` (`33.33%`) | `13 / 33` (`39.39%`) | `13 / 33` (`39.39%`) |
| `SUPPORTED_11` precision among eligible | `1.0000` (`11/11`) | `1.0000` (`13/13`) | `1.0000` (`13/13`) |
| `human_agent` escalated | `3 / 3` | `3 / 3` | `3 / 3` |
| `ESCALATED_34` accuracy / unsafe drafts (`n=42`) | `76.19%` / `0` | `76.19%` / `0` | `76.19%` / `0` |
| `negative_45` false draft / false accept | `1 / 45` (`2` accept) | `1 / 45` (`1` accept) | **`2 / 45` (`2` accept)** (regressed) |
| └─ `compound_multi_intent` (`n=18`) false draft | `1` | `1` | **`2`** (regressed) |
| └─ `unsupported` (`12`), `underspecified` (`9`), `off_domain` (`6`) | `0 / 0 / 0` | `0 / 0 / 0` | `0 / 0 / 0` |

### B. Already-Seen Development Suites (`suite_role = "already_seen_development"`)
| Suite & Metric | Baseline Linear (`95a940b6`) | Diag 1: Cosine Centroid | Diag 2: Tied Mahalanobis |
|---|---|---|---|
| `closure_dev_pos_102`: `sup11` corr (`n=66`) / prec | `19` (`28.79%`) / `82.61%` | `19` (`28.79%`) / `82.61%` | `23` (`34.85%`) / `85.19%` |
| `closure_dev_pos_102`: `human_agent` (`n=6`) / `esc34` unsafe | `5 / 6` / `0` | `5 / 6` / `0` | `5 / 6` / `0` |
| `closure_dev_neg_33`: false draft / false accept | `0 / 0` | `0 / 0` | `0 / 0` |
| `ml_noise_420`: corr (`cov`) / prec / safe routing | `196` (`46.67%`) / `86.34%` / `92.62%` | `193` (`45.95%`) / `87.33%` / `93.33%` | `208` (`49.52%`) / `87.39%` / `92.86%` |
| **`ml_oos_80`**: false drafts (`ids`) | **`0 / 80`** (`[]`) | **`1 / 80`** (`oos-multi_intent-02`) | **`1 / 80`** (`oos-multi_intent-02`) |
| **`system_acceptance_156`**: answerable (`n=34`) / prec | `20` (`76.92%`) | `22` (`78.57%`) | `22` (`78.57%`) |
| **`system_acceptance_156`**: mandatory unsafe leaks (`excl. uninjected`) | **`1`** (`una-product_information-01`) | **`0`** (`score=0.4647 < 0.58`) | **`1`** (`una-product_information-01`, `0.5003 >= 0.50`) |
| `system_acceptance_156`: `escalated_34` macro F1 / mandatory strict match | `0.7059` / `22 / 63` | `0.7059` / `22 / 63` | `0.7059` / `22 / 63` |
| `final_acceptance_24`: answerable (`n=12`) / prec / real leaks | `8` / `100%` / `0` | `7` / `100%` / `0` | `8` / `100%` / `0` |
| `bitext_test_6690`: `other_34` unsafe drafts (`n=4,928`) | **`1 / 4,928`** | **`1 / 4,928`** | **`1 / 4,928`** |

*(Known uninjected runtime/fault exclusions in `system_acceptance_156` and `final_acceptance_24` remain `unc-return_policy-04` and `final-case-21`, matching `8d9b3e0`.)*

---

## 4. Raw Score & Geometry Distributions (Why `[CLS]` Density Fails to Separate the Gap)

### Fresh Unseen Probe Feature Quantiles (Shared Geometry on Frozen `95a940b6`)
| Slice (`n`) | Metric | Mean | P25 | P50 | P75 | P90 | Max |
|---|---|---|---|---|---|---|---|
| `sup11_correct` (`29`) | Baseline `score` | `0.5312` | `0.0832` | `0.6885` | `0.9299` | `0.9911` | `0.9996` |
| `sup11_correct` (`29`) | Diag 1 `score` | `0.4437` | `0.0767` | `0.3500` | `0.7937` | `0.9519` | `0.9953` |
| `sup11_correct` (`29`) | `pred_cos` | `0.7575` | `0.7186` | `0.7394` | `0.8343` | `0.8917` | `0.9390` |
| `sup11_correct` (`29`) | `cos_esc_margin` | `0.3673` | `0.2706` | `0.3297` | `0.4723` | `0.5632` | `0.6120` |
| `sup11_correct` (`29`) | `d2_pred_z` | `9.9471` | `6.7155` | `9.7922` | `11.8483` | `16.3686` | `22.9524` |
| `sup11_correct` (`29`) | `mahal_esc_margin` | `3270.3` | `1465.4` | `2633.7` | `4537.5` | `7155.8` | `8292.7` |
| `compound_multi_intent` (`18`) | Baseline / Diag1 `score` | `0.1234` / `0.1277` | `0.0000` / `0.0005` | `0.0042` / `0.0110` | `0.0376` / `0.1053` | `0.3774` / `0.4296` | `0.9075` / `0.8398` |
| `compound_multi_intent` (`18`) | `pred_cos` / `d2_pred_z` | `0.6636` / `14.04` | `0.5688` / `9.35` | `0.6455` / `12.44` | `0.6848` / `17.08` | `0.8531` / `19.96` | `0.9130` / `36.41` |
| `neg_other` (`27`) | Baseline / Diag1 `score` | `0.0478` / `0.0230` | `0.0000` / `0.0001` | `0.0001` / `0.0006` | `0.0044` / `0.0059` | `0.0932` / `0.0315` | `0.6684` / `0.4263` |
| `escalated_34` (`42`) | Baseline / Diag1 `score` | `0.0154` / `0.0065` | `0.0000` / `0.0001` | `0.0002` / `0.0008` | `0.0019` / `0.0035` | `0.0224` / `0.0111` | `0.3913` / `0.0948` |

### `ml_oos_80` & `system_acceptance_156` Score Quantiles & `una-product_information-01` Profile
- **`una-product_information-01`** (`pred_intent = delivery_time`, `cal_conf = 0.8851`):
  - `linear_p_in = 0.8692`, Diag 1 `score = 0.4647` (`manual_fallback`), Diag 2 `score = 0.5003` (**STILL `retrieve_draft`**)
  - `pred_cos = 0.7007`, `pred_cos_z = -10.4704`, `cos_esc_margin = 0.3514`, `cos_neg_margin = 0.0086`, `sup11_2nd_cos_gap = 0.2858`, `d2_pred_z = 15.9668`, `mahal_esc_margin = 4064.2268`, `mahal_neg_margin = 1838.2851`.
- **`ml_oos_80` (`n=80`) score quantiles:** Baseline `p90=0.1614, max=0.9956` (`0` drafts — predicted escalated or below threshold); Diag 1 `p90=0.0588, max=0.9018` (**`1` leak: `oos-multi_intent-02`**); Diag 2 `p90=0.1214, max=0.8399` (**`1` leak: `oos-multi_intent-02`**).
- **`system_acceptance_156` mandatory (`n=62` excl. uninjected):** Baseline `p90=0.9037, max=0.9984`; Diag 1 `p90=0.7269, max=0.9933`; Diag 2 `p90=0.7224, max=0.9296`.

### Diagnosis of Failure Mode
1. **Total overlap between valid fresh queries and target leaks in frozen `95a940b6` `[CLS]` space:** Over `50%` of valid `sup11_correct` fresh queries have smaller `cos_esc_margin` (`p50 = 0.3297`) and smaller `mahal_esc_margin` (`p50 = 2633.7`) than `una-product_information-01` (`0.3514` and `4064.2`), and `25%+` have `pred_cos <= 0.7186` vs `0.7007`.
2. **Tight synthetic Bitext train variance creates extreme OOD z-scores even on clean in-domain queries:** Because Bitext training clusters are tight, naturally worded `SUPPORTED_11` fresh queries already exhibit `d2_pred_z` `p50 = 9.79` (`p90 = 16.37`), overlapping `una-product_information-01` (`15.97`) and `compound_multi_intent` (`p25–p75 = [9.35, 17.08]`).
3. **Zero net safety win:** Neither diagnostic resolves `compound_multi_intent` (`1/45` and `2/45` fresh negative leaks) or `bitext_test_6690` `other_34` (`1/4,928`), both regress `ml_oos_80` (`0 -> 1` via `oos-multi_intent-02`), and `diag2` still fails `una-product_information-01`. Meanwhile, Diag 1's blocking of `una-product_information-01` relies on an uncalibrated `cos_neg_margin = 0.0086` proximity to the small `75`-row negative train set rather than clean semantic separation, drops `final_acceptance_24` coverage (`8/12 -> 7/12`), and still leaves `2/42` false drafts on `closure_negative_calibration`.

---

## 5. Recommendation

- **Do NOT add a `selective_calibration.v2` runtime patch or schema contract built on post-hoc `[CLS]` centroid/Mahalanobis density**, and **do NOT promote `95a940b6`**.
- **Artifact Location:** [feasibility_results.json](file:///C:/Users/PC/orca/workspaces/SupportIQ/supportiq-final-routing/artifacts/evaluation/task_a_feasibility_20261113/feasibility_results.json), [closure_feasibility_probes.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/supportiq-final-routing/pipeline/training/closure_feasibility_probes.py), [offline_cls_density_feasibility.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/supportiq-final-routing/pipeline/training/offline_cls_density_feasibility.py).
