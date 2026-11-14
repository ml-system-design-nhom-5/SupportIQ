# Fit2 v4p1 Diagnosis Independent Review (Worker B)

- **Reviewed commit:** `6f175a779f8df11a48aa7b65b5d23eff04f8ea59` (`docs/audits/2026-11-14-fit2-v4p1-regression-diagnosis-a.md`)
- **Primary evidence checked:** `711a9fc5254b30940a4e58e2b95c03900c59bf3c` (`docs/audits/2026-11-14-fit2-v4p1-independent-evaluation-c.md`), `artifacts/evaluation/fit2_v4p1_independent_20261114/{suites_comparison,gate_report_v4p1,run_manifest}.json`, `artifacts/models/candidates/fit2-boundary-contrast-v4p1/calibration_manifest.json`, `artifacts/models/candidates/run-records-fit2-boundary-contrast-v4p1/inputs/*.jsonl`, `pipeline/training/{train_boundary_candidate,train_domain_candidate}.py`, `apps/ml_inference/app.py`, `apps/core_backend/config/policies/intent_policy.v2.json`.
- **Verdict:** **Empirical diagnosis verified (`REJECT` upheld); Section 6 remediation requires changes before any retry (`CHANGES_NEEDED_IN_PROPOSAL`).**

---

## 1. Verification of Worker A's Empirical Claims & Root Causes

| Area | A's Claim (`6f175a7`) | Direct Verification | Status |
|---|---|---|---|
| Gate outcome | `REJECT` on `holdout_34_label_unsafe_draft_leak` | `gate_report_v4p1.json`: `REJECT`, `['holdout_34_label_unsafe_draft_leak']` | **Verified** |
| `isolated_eval_pos175_neg51` | `SUP11` `raw_pre 49/44 -> raw_post 48/43 -> engine 47/42 -> runner 36/33` (vs `orig_fit2` `48/40 -> 47/39 -> 43/35`); `ESC34` acc `0.9359` vs `0.8077`, leaks `4 -> 1` (`contrast_auth_pos_eval_102`, `0.9780`); `neg51` leak `1 -> 1` (`nonretail_ood_eval_019`, `0.6860`) | Exact match in `suites_comparison.json` (`0.977992` on `contrast_auth_pos_eval_102`; `0.685986` on `nonretail_ood_eval_019` vs `orig_fit2` `0.710946`) | **Verified** |
| `ml_noise_420` | `8` `SUP11` false vetoes (`correct_draft 271 -> 263`), `acc_12` `0.8571 -> 0.8452` | Exact match (`raw_pre 296/271` -> `raw_post 288/263`; `acc_12` `0.857143 -> 0.845238`) | **Verified** |
| `final_acceptance_24` | `ans12_correct` `10 -> 8` (`final-case-05`, `final-case-06` newly dropped) | Exact match (`ans12_dropped`: `['final-case-02', 'final-case-05', 'final-case-06', 'final-case-08']`) | **Verified** |
| RC1 (`return_policy` vs `return_product_in_store`) | Bitext `return_policy` rows describe in-store returns; `contrast_auth_pos_cal_072` in `boundary_pos_calibration` (`rp_cal_01`) | Confirmed (`bitext_train_clean`: 12 in-store/shop `return_policy` rows, `bitext_train_noisy`: 7; `contrast_auth_pos_cal_072` in `boundary_pos_calibration.jsonl` / `full_cal_split.jsonl`) | **Verified** |
| RC2 (Probability compression) | Compound negative loss (`0.80*l_kl + 3.0*l_ceil` at `ceil_thr=0.18`, `0.25*SupCon`, `0.25*l_eng`) + `min_temperature=1.0` + `ESC34` exposure skew | `train_boundary_candidate.py:808,866,946`; `full_train_split.jsonl`: `return_product_in_store=271`, `order_history=270`, `track_delivery=270` vs `refund_policy=252`, `cancel_order=251`, `delivery_issue=251`, `return_product_online=240` | **Verified** |
| RC3 (`776d` rejector pathology) | `y=1: 2,356` vs `y=0: 6,410` (`92.1%` in-distribution), `bias=-3.0511`, `cls_l2=3.3355`, `geo_l2=0.1409`, negative geometry weights | Exact match (`y=0: 6,410` = `5,902` (`92.07%`) in-dist + `508` 4x neg; `y=1: 2,356`; tail `raw_max_prob=-0.0181`, `raw_margin=-0.0792`, `cal_max_prob=-0.0181`, `cal_margin=-0.0792`, `logit_max=-0.0149`, `logit_logsumexp=-0.0803`) | **Verified** |

---

## 2. Required Corrections to Section 6 Before Any Retry

1. **Bitext `return_policy` regex mismatch (`_INSTORE_CHANNEL_RE` misses 19/19 Bitext rows) & `track_delivery` replay:**
   - Checking A's Section 6 Step #1 against the actual `v4p1` inputs shows `_INSTORE_CHANNEL_RE` (`brick-and-mortar|physical store|physical shop|retail branch|retail store|storefront|store counter|walk-in|cashier|in person at (?:a|your|the) (?:store|shop|branch)`) matches **`0` rows** in `bitext_train_clean` (`160` `return_policy`), `bitext_train_noisy` (`80`), and `bitext_cal` (`15`).
   - Actual conflicting Bitext `return_policy` rows use phrasing such as `"in store"`, `"at the shop"`, `"in shop"` (`12` clean + `7` noisy = `19` matches under `\b(store|shop|branch|brick|physical|in-store|in store|stroe)\b`; `0` in `bitext_cal`). Reusing `_INSTORE_CHANNEL_RE` unchanged on Bitext will leave all `19` rows uncleaned.
   - Similarly, `_VEHICLE_GPS_TELEMETRY_RE` matches **`0`** Bitext `track_delivery` rows (`clean`/`noisy`/`cal`). The `track_delivery` inflation (`270` in `full_train_split`, including `20` `bitext_train_esc34_pos_train` rows) comes from sourcing/upweighting extra Bitext `track_delivery` replay rather than GPS-keyword leakage. Any Bitext edit must also preserve calibration/eval integrity rather than filtering `bitext_cal` blindly or breaking locked source provenance.

2. **`min_temperature=0.75` violates the serving validation contract (`apps/ml_inference/app.py:305-306`):**
   - Although `train_domain_candidate.py:438` has a legacy default `min_temperature: float = 0.75`, `train_boundary_candidate.py:866,946` explicitly enforces `min_temperature=1.0` because serving rejects `< 1.0` at startup:
     - `apps/ml_inference/app.py:305-306`: `if min_temp < 1.0: raise ValueError(f"Calibration manifest min_temperature must be >= 1.0, got {min_temp!r}")`
     - `apps/ml_inference/app.py:313-314`: enforces `temp >= min_temp`.
   - Even apart from the contract error, temperature sharpening (`T < 1.0`) scales all logits equally—raising OOD/ESC34 confidences (e.g., `nonretail_ood_eval_019` `0.6860`) toward draft thresholds rather than improving `SUP11` margin separation. Fix `SUP11` confidence compression in the training objective/exposure (`T >= 1.0`).

3. **Rejector ablations & non-retail OOD gap (`nonretail_ood_eval_019`):**
   - Disabling the rejector first (`selective_rejector.enabled=false`, already supported at `train_boundary_candidate.py:696,920` and handled cleanly when `None` in serving) is the right clean baseline so `[CLS]` topic bias does not mask classifier behavior.
   - Do not assume an `8d` `logit_geometry_v1` rejector (`Section 6 #3` fallback) will solve `v4p1`'s failures: a confidence/entropy feature head cannot separate wrong-intent `ESC34 -> SUP11` predictions at `0.9780` (`contrast_auth_pos_eval_102`), and its separation near `[0.65..0.75]` (`nonretail_ood_eval_019` vs short `SUP11`) is untested.
   - Finally, `nonretail_ood_eval_019` leaked across every layer in both `orig_fit2` (`0.7109`) and `v4p1` (`0.6860`), indicating the retrieval relevance / domain-scope gate also needs independent inspection outside classifier-head tuning.

---

## 3. Scope Statement
- **No training runs, code edits, dataset modifications, helper workers, or provider calls** were performed in this review, and **no retry fit is authorized** until Section 6 is revised for the defects above and approved by the coordinator.
