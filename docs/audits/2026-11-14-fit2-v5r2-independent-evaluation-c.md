# Fit2 `v5-r2` Independent Stage 2 Evaluation (Worker C)

- **Candidate:** `artifacts/models/candidates/fit2-taxonomy-audit-v5-r2` (`weights=0b2d26c2adc22928a52bdbafe580fa1673d8ae1d112c42f3def643e137eaa33d`, `calibration=ca3d711c78f9c1e960ebf2d700b4445c4538e0bd4b52cc2dd6fb502dc8e472c1`, `T=1.0`, `C=0.15`, `tau=0.76`)
- **Verified Frozen Lineage:** `run-records-fit2-taxonomy-audit-v5-r2` (`fits_started=1`, `fits_completed=1`, `status=complete`; `32/32` sidecar inventory match; archive SHA inventory verified). Shared eval/cal splits (`bitext_test_6690`, `boundary_pos_evaluation=175`, `boundary_neg_evaluation=51`, `full_cal_split=885`) are SHA-identical to `v4p1`; training splits differ strictly by the `25` audited KB-contradiction rows.
- **Reviewed Runtime & Disclosure:** All four models (`serving`, `orig_fit2`, `v4p1`, `v5_r2`) executed on the same Stage-1-`PASS` reviewed code `183cdf6935ad392e2e01e6af331d56a326dfabb9` (branch `minh`, audit doc head `4f0c614fdd6df4c5af29e4ad5e8dd5b914f95f59`). Historical `v4p1` ran at `8c7e12d6bc80bcbdb5aeb3961f6d84f704c93438` (prior to grounding/allowlist/worker commits `013d1c4`..`183cdf6`); `v4p1` rerun on `183cdf69` reproduced identical Runner counts (`8/12`, `27/34`, `251`).
- **Offline Conditions & Scope Limits:** `0` live Gemini calls; `Engine` uses `_MockNoCallLLM` (`_analyse` routing only); `PipelineRunner` uses `_OfflineValidSpyLLM` (draft-eligibility/snapshot stub only, not real LLM quality). Injected faults excluded as designed (`final-case-21`, `final24` uninjected `4`, `sa156` `unc-return_policy-04`). `historical_fresh_34` is historical regression only, not unseen holdout.
- **Verdict:** **`REJECT`** (Production Gate: `REJECT` on `holdout_34_label_unsafe_draft_leak`; also misses `final24 >= 10/12`, `noise420 macro_f1 >= 0.8573`, and `noise420 correct_draft >= 267`).

---

## 1. Four-Model Comparison (`183cdf69` Runtime)

Runner surface shown primarily (`Engine` / `raw_post` / `raw_pre` included where safety/veto behavior diverges):

| Suite / Metric | Target | `Serving` (`dc7af8cf`) | `OrigFit2` (`f695b1fe`) | `v4p1` (`e1039f92`) | `v5-r2` (`0b2d26c2`) |
|---|---|---:|---:|---:|---:|
| `final24` Runner answerable (`active_unans8` leaks) | `>= 10/12` (`0` leaks) | `4/12` (`0`) | `10/12` (`0`) | `8/12` (`0`) | **`7/12` (`0`) FAIL** |
| `sa156` Runner `d34` (`mand63` strict / real leaks) | `>= 25/34` (`0` leaks) | `17/34` (`52/63`, `0`) | `25/34` (`50/63`, `1`) | `27/34` (`53/63`, `0`) | **`26/34` (`53/63`, `0`) PASS** |
| `noise420` `macro_f1_12` / `acc_12` / `ece` | `F1 >= 0.8573` | `0.6817 / 0.6548 / 0.0920` | `0.8573 / 0.8571 / 0.0631` | `0.8505 / 0.8452 / 0.0515` | **`0.8510 / 0.8452 / 0.0684` FAIL** |
| `noise420` Runner `correct_draft` (`raw_post` / `gate_cal`) | `>= 267` | `176` (`182` / `182`) | `260` (`276` / `276`) | `251` (`263` / `264`) | **`250` (`260` / `253`) FAIL** |
| `oos80` leaks (`Runner` / `Engine` / `raw_post` / `raw_pre`) | `0` | `0 / 0 / 2 / 2` | `0 / 0 / 3 / 3` | `0 / 0 / 4 / 4` | **`0 / 0 / 3 / 3`** |
| `pos175` `acc_46` / `f1_46` / `esc34_acc` | — | `0.5257 / 0.2538 / 0.6282` | `0.7657 / 0.4350 / 0.8077` | `0.8171 / 0.4475 / 0.9359` | `0.8114 / 0.4416 / 0.9359` |
| `pos175` `sup11` Runner `corr` (`esc34` leaks, `raw_post`=`Runner`) | `0` leaks | `24/90` (`5` leaks) | `35/90` (`3` Runner / `4` raw) | `33/90` (`1` leak) | **`33/90` (`1` leak) FAIL** |
| `neg51` unsafe draft leaks (`Runner` / `raw_post` / `raw_pre`) | `0` | `4 / 5 / 5` | `1 / 1 / 1` | `1 / 1 / 1` | **`0 / 0 / 0` PASS** |
| `bitext6690` `acc_46` / `post_sup11_corr` (`esc34` leaks) | `0` leaks | `0.9954` / `1590/1613` (`1`) | `0.9963` / `1600/1613` (`1`) | `0.9958` / `1595/1613` (`2`) | `0.9963` / `1592/1613` (`1`) |
| `ind36` Runner `ans` (`mand` / leaks) | `0` leaks | `3/11` (`5/12` / `1`) | `6/11` (`5/12` / `0`) | `3/11` (`8/12` / `0`) | **`3/11` (`9/12` / `0`)** |
| `old_sealed72` Runner `ans` (leaks) | `0` leaks | `4/24` (`1`) | `5/24` (`0`) | `5/24` (`0`) | **`5/24` (`0`)** |
| `historical_fresh34` Runner `ans` (`Runner` / `raw_post` leaks) | Regression only | `2/11` (`0 / 1`) | `4/11` (`1 / 1`) | `3/11` (`0 / 0`) | **`4/11` (`0 / 1` `v4p1-esc-09`)** |

---

## 2. Data-Only Deltas (`v5-r2` vs `v4p1`) & Rejected Criteria

- **Failed Criteria (Production Gate + Targets):**
  1. **Isolated 34-label holdout leak (`holdout_34_label_unsafe_draft_leak`):** `contrast_auth_pos_eval_102` (*"Is returning an item at a brick-and-mortar branch allowed?"*, gold `return_product_in_store`) is still predicted `return_policy` at calibrated `conf=0.971305` and enters `retrieve_draft` on `raw_pre`, `raw_post`, `engine`, and `runner` (`1/78`).
  2. **`final24` Runner answerable utility:** Dropped `8/12 -> 7/12` (`< 10/12`), losing `final-case-07` (`track_order` -> `track_delivery`, `conf=0.445646`, `escalate`).
  3. **`noise420` F1 & draft coverage:** `macro_f1_12 = 0.8510 < 0.8573`; Runner `correct_draft = 250 < 267` (calibrated gate `253 < 267`).
- **Component Deltas (`v5-r2` vs `v4p1`):**
  - **Store-return:** No change on `contrast_auth_pos_eval_102` (both leak at `return_policy`); remaining `in_store` rows escalated cleanly on both.
  - **OOD & Boundary Safety:** `neg51` leaks cleared `1 -> 0` (rejector vetoed `nonretail_ood_eval_019`); `raw_post oos80` leaks fell `4 -> 3` (`0` on Runner); `bitext6690` `raw_post` `esc34` leaks fell `2 -> 1`; `ind36` `mand` strict match improved `8/12 -> 9/12`.
  - **False-Veto & Utility:** Rejector (`tau=0.76`, vs `v4p1` `tau=0.72`) vetoed `13` correct `raw_pre` supported drafts across the 9 suites (`sa156`: `1`, `noise420`: `10`, `pos175`: `2`) vs `12` in `v4p1` (`fresh34`: `1`, `sa156`: `2`, `noise420`: `8`, `pos175`: `1`), contributing to net utility `-1` on `final24`, `-1` on `sa156`, `-1` on `noise420`, `-3` on `bitext6690` `raw_post`, and `+1` on `historical_fresh34` (`v4p1-sup-04`).

---

## 3. Reproducibility & One Next Action

- **Command:** `.venv/Scripts/python.exe -B artifacts/evaluation/fit2_v5r2_independent_20261114/evaluate_v5r2.py`
- **Outputs:** `artifacts/evaluation/fit2_v5r2_independent_20261114/` (`evaluate_v5r2.py`, `gate_report_v5r2.json`, `suites_comparison.json`, `predictions_*.jsonl`, `run_manifest.json`).
- **One Next Action:** Do **not** promote `v5-r2`; fix `return_product_in_store` vs `return_policy` discrimination (e.g., targeted in-store-return phrasing examples such as brick-and-mortar branch/in-person returns) alongside `track_order` vs `track_delivery` (`final-case-07`) and noise/utility calibration rather than relying solely on the 25-row contradiction quarantine + `tau=0.76` rejector.
