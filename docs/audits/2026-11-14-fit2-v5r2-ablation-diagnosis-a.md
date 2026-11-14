# Fit2 `v5-r2` Root-Cause Diagnosis (Worker A)

- **Scope & Verdict:** Read-only root-cause diagnosis of Worker C's Stage 2 `REJECT` evaluation (`evaluate_v5r2.py`, runtime `183cdf6935ad392e2e01e6af331d56a326dfabb9`, branch `minh`) of data-only ablation `fit2-taxonomy-audit-v5-r2` (`0b2d26c2`, `T=1.0`, `C=0.15`, `tau=0.76`). **Verdict: Stop speculative quarantine/seed/rejector microtuning.** Removing `20` Bitext `return_policy` training rows left `contrast_auth_pos_eval_102` leaking at `conf=0.9713`, shifted batch count (`435 -> 434`) across unrelated intents (`final-case-07`), and pushed `tau` to `0.76`, where the `776d` rejector vetoed **`13/13` correct `SUPPORTED_11` drafts** and **`0/13` wrong/unsafe drafts** across the 9 suites.

---

## 1. Four-Model Comparison & Denominator Audit (`183cdf69` Runtime)

From `suites_comparison.json` and `gate_report_v5r2.json` (`_MockNoCallLLM` / `_OfflineValidSpyLLM`, `0` human/live LLM calls):

| Suite / Metric | Surface | `Serving` (`dc7af8cf`) | `OrigFit2` (`f695b1fe`) | `v4p1` (`e1039f92`) | `v5-r2` (`0b2d26c2`) |
|---|---|---:|---:|---:|---:|
| `final24` ans (`active_unans8` leaks) | `raw_pre` / `Runner` | `4/12` (`1` / `0`) | `10/12` (`0` / `0`) | `8/12` (`0` / `0`) | **`7/12`** (`0` / `0`) |
| `sa156` `sup34` (`mand63` strict / leaks) | `raw_pre` / `Runner` | `17/34` (`39`->`52`, `12`->`0`) | `25/34` (`42`->`50`, `9`->`1`) | `27/34` (`46`->`53`, `6`->`0`) | **`26/34`** (`46`->`53`, `6`->`0`) |
| `noise420` `f1_12` / `acc_12` / `ece` | classifier | `0.6817 / 0.6548 / 0.0920` | `0.8573 / 0.8571 / 0.0631` | `0.8505 / 0.8452 / 0.0515` | **`0.8510 / 0.8452 / 0.0684`** |
| `noise420` `corr_draft` (`wrong`) | `raw_pre` / `raw_post` / **`bare (gate)`** / `Runner` | `182 / 182 / 177 / 176` (`33w`) | `276 / 276 / 267 / 260` (`27->26w`) | `271 / 263 / 255 / 251` (`25->24w`) | **`270 / 260 / 253 / 250`** (`24->23w`) |
| `oos80` leaks | `raw_pre` / `bare` / `Engine` / `Runner` | `2 / 2 / 0 / 0` | `3 / 3 / 0 / 0` | `4 / 4 / 0 / 0` | **`3 / 3 / 0 / 0`** |
| `pos175` `sup11` corr (`esc34` leaks) | `raw_pre` / `raw_post` / `Runner` (`gate_cal`) | `29 / 29 / 24` (`6/6/5`) | `40 / 40 / 35` (`4/4/3`) | `44 / 43 / 33` (`1/1/1`) | **`44 / 42 / 33`** (`34/39` `gate`, `1/1/1`) |
| `pos175` `acc_46` / `esc34_acc` | classifier | `0.5257 / 0.6282` | `0.7657 / 0.8077` | `0.8171 / 0.9359` | **`0.8114 / 0.9359`** |
| `neg51` leaks | `raw_pre` / `raw_post` / `Runner` | `5 / 5 / 4` | `1 / 1 / 1` | `1 / 1 / 1` | **`0 / 0 / 0`** |
| `bitext6690` `acc_46` / `post_sup11` (`esc34`) | `raw_pre` -> `raw_post` | `0.9954` / `1590` (`1`) | `0.9963` / `1600` (`1`) | `0.9958` / `1595` (`2`) | `0.9963` / `1593->1592` (`1`) |
| `ind36` ans (`mand` / leaks) | `Runner` | `3/11` (`5/12` / `1`) | `5/11` (`5/12` / `0`) | `3/11` (`8/12` / `0`) | **`3/11`** (`9/12` / `0`) |
| `old_sealed72` ans (leaks) | `Runner` | `4/24` (`1`) | `5/24` (`0`) | `5/24` (`0`) | **`5/24`** (`0`) |
| `historical_fresh34` ans (`raw_pre` / `Runner` leaks) | reg. only | `2/11` (`1` / `0`) | `4/11` (`1` / `1`) | `3/11` (`1` / `0`) | **`4/11`** (`1` / `0` `v4p1-esc-09`) |

**Denominator Audit (`noise420 >= 267`, `pos175`, Gate Rule):**
1. **`noise420` target `>= 267` is `OrigFit2`'s `bare`/`gate` count, not `Runner`:** In `OrigFit2`, `raw_pre = 276/303`; `bare` (`decide_route`, no KB retrieval) drops `9` correct + `1` wrong (`missing_order_id` slot guard) -> **`267/293`**; `Runner` drops `7` more correct drafts via KB retrieval (`no_evidence`/`below_relevance_threshold`: `6`, `requires_authority` + KB: `1`) -> **`260/286`**. Placing `>= 267` on the `Runner` row compares `v5-r2`'s `Runner` (`250`) against `OrigFit2`'s `bare` (`267`), whereas `v5-r2`'s matching unvetoed `gate`/`bare` (`candidate_evaluation` in `gate_report_v5r2.json`) is **`263/286`** (calibrated: **`253/276`**). Also note `classifier_acceptance_gate.py:1379-1380` enforces non-regression vs **`Serving` (`177`)**, not `267`; in `gate_report_v4p1.json`, `v4p1` calibrated `noise420` is `255` (not `264`).
2. **`pos175` surface gap:** `gate_report_v5r2.json` evaluates fixed `is_personal_lookup=False` (`decide_route`, denominator `supported_12=97`: `36/41` uncalibrated vs `34/39` calibrated), while `evaluate_v5r2.py` reports `sup11=90` at `raw_post=42/47` and `Runner=33/38` (slot/KB drops).

---

## 2. Rejector vs Encoder Attribution & No-Veto Counterfactual

Across all 9 evaluation suites (`predictions_v5_r2.jsonl`), every rejector veto on `raw_pre == retrieve_draft` was a false alarm, while **`neg51` cleared before the rejector**:

- **Rejector veto precision (`v5-r2`, `tau=0.76`):** **`13/13` vetoed `raw_pre == retrieve_draft` cases are correct `SUPPORTED_11` drafts (`0/13` wrong/unsafe)**: `noise420`: `10` (`sup-delivery_issue-02` x2, `sup-delivery_issue-05` x4, `sup-shipping_costs-05` x2, `sup-delivery_time-03` x1, `sup-return_product-03` x1), `pos175`: `2` (`cls_can_bundle_promo_1_14b716000ef4` `0.9120`, `cls_rpr_reschedule_courier_0_8a1587b8d79d` `0.8508`), `sa156`: `1` (`sup-delivery_issue-05`, `draft_expected=False`). On `bitext6690`, `raw_post` lost `1` more (`1593 -> 1592`) and stopped `0` `esc34` leaks (`1 -> 1`). (`v4p1` similarly vetoed `12/12` correct, `0` wrong.)
- **Correction to C's report on `neg51` (`nonretail_ood_eval_019`):** In `v4p1`, `nonretail_ood_eval_019` predicted `delivery_time` at `0.6860` (`raw_pre=retrieve_draft`, `s=0.8950`). In `v5-r2`, **encoder confidence dropped to `0.5929 < 0.65` (`raw_pre_action=clarify`)**; the rejector's `s=0.7546 < 0.76` merely converted `clarify -> manual_fallback`. So `neg51` cleared in **`raw_pre` BEFORE the rejector** (`neg51 raw_pre_leaks = 0`).
- **Stored-score no-veto counterfactual (no recalibration):**
  - `noise420`: `bare_noveto = 263/286` (exact `gate_report_v5r2.json` uncalibrated `candidate_evaluation`; vs `253/276` calibrated, `-4` vs `OrigFit2` `bare=267`), `runner_noveto <= 260/283` (at least `3` of the `10` vetoed `delivery_issue` typos also fail KB retrieval when unvetoed in `orig_fit2`).
  - `pos175`: `gate_noveto = 36/41` (`candidate_evaluation` vs `34/39` calibrated, `esc34_unsafe=1` unchanged); `raw_pre=44/49` vs `raw_post=42/47`; `runner_noveto = 33/38` (both vetoed `pos175` rows also carry `requires_authority` in `runner_reasons`).
  - `final24`: **`0` rejector vetoes**; `10 -> 8 -> 7` loss is 100% encoder confidence/label shift: `final-case-05` (`refund_status` `0.8056 -> 0.5027 -> 0.3793`), `final-case-06` (`cancel_order` `0.8343 -> 0.6918 -> 0.7959`, policy threshold `0.80`), `final-case-07` (`track_order 0.6717 -> track_delivery 0.4456`).
  - `sa156`: net `sup34` `27 -> 26` is encoder-only (`ans-return_policy-05` `0.68 -> 0.51`, `sup-refund_policy-03` `0.66 -> 0.48`, `ans-refund_policy-07` `0.82 -> 0.80` clarified, vs gain on `ans-cancel_order-01` `0.74 -> 0.85`).

---

## 3. Exact `v4p1` -> `v5-r2` Data Diff & Retained TRAIN/CAL Root Causes

1. **Exact Input Diff (`run-records-fit2-taxonomy-audit-v5-r2` vs `v4p1`):**
   - **SHA-identical (`0` diff):** `full_cal_split` (`885`, SHA `116231be...`), `bitext_cal` (`690`), `bitext_test_6690` (`6690`), `boundary_pos_train` (`300`), `boundary_neg_train` (`127`), `boundary_pos_calibration` (`135`), `boundary_neg_calibration` (`60`), `boundary_pos_evaluation` (`175`), `boundary_neg_evaluation` (`51`).
   - Of the `25` rows in `quarantine_records.jsonl`, **`5` `closure_positive_20261113` `track_order` GPS rows** (`3` train, `2` cal) were **already absent in `v4p1`**.
   - **Actual diff = `20` Bitext `return_policy` TRAIN rows only** (`12` `bitext_train_clean` + `8` `bitext_train_noisy` children; unweighted `11464 -> 11444`, effective weighted `13901 -> 13881`, `bs=32, seed=42` -> **`435 -> 434` batches/epoch**). Altering dataset length by `-20` changed every shuffled mini-batch and linear warmup step (`1305 -> 1302`), causing global confidence drift on unrelated intents without changing a single CAL row (`cal_dom_corr`: `29/53 -> 28/53`; `max_neg_cal_sup12`: `0.5209 -> 0.6085`).

2. **Why `contrast_auth_pos_eval_102` (`"Is returning an item at a brick-and-mortar branch allowed?"`) Still Leaks:**
   - Fixed-model inference on retained `v5-r2` `full_train_split` already gives **`100.0%` TRAIN accuracy** on both `return_policy` (`241/241`, effective `304`) and `return_product_in_store` (`271/271`, effective `399`).
   - Policy-eligibility syntax (`is it possible` / `allowed` / `can i` / `could i` / `accept`) appears in **`87/241` (`36%`)** retained `return_policy` TRAIN rows (plus `1/241` using `"standard store rules"`), whereas ALL `12` `authored_contrast_pos_train` `return_product_in_store` rows ask action/location questions (`"Can I bring..."`, `"Which retail store locations accept..."`, `"Can a store associate..."`, `"Will a physical branch accept..."`) and **none** use `"Is returning ... at a ... branch allowed?"` policy framing.
   - Consequently, quarantining 20 Bitext `return_policy` `"in store/shop"` rows actually **increased** false `return_policy` confidence on CAL's `"Do your brick-and-mortar shops accept walk-in returns?"` (`0.700 -> 0.811`, `s: 0.611 -> 0.7536`) and kept `contrast_auth_pos_eval_102` at `conf=0.9713, s=0.9971`. Structurally, `approved_kb.v2.json` (`POL-RET-001/002/003`) covers general return policy (`return_policy` is `SUPPORTED_11`), creating an inherent semantic conflict whenever a user asks **about store-return eligibility/policy** (`return_product_in_store` is `ESCALATED_34`).

3. **Why `final-case-07` Flipped (`track_order` vs `track_delivery`):**
   - In retained `v5-r2` TRAIN, `track_delivery` has **`270` raw (`390` effective)** rows vs `track_order` **`258` raw (`312` effective)**, and `run_config.json` explicitly flags **`263/270` `track_delivery` TRAIN rows as `ambiguous_retained`** (generic `"where my package/shipment is"` queries lacking GPS/courier telemetry; `gps/courier_kw=86`, `pkg/shipment/parcel/order_kw=156`).
   - Fixed-model inference on retained `v5-r2` `full_train_split` already misclassifies **`12/258` (`4.7%`) `track_order` TRAIN rows as `track_delivery`** (`conf=0.67-0.95`). Adding the `435 -> 434` batch-shuffle drift tipped `final-case-07` (`track_order 0.6717 -> track_delivery 0.4456`).

4. **Why the `776d` CAL Rejector Failed (`C=0.15, tau=0.76`):**
   - In `v5-r2`'s `776d` LR rejector (`cls_l2_plus_logit_geometry_v1`), `||w[:768]||_2 = 2.020` vs `w[768:]` in `[-0.088, +0.016]` (`bias=-3.573`), so decisions rely heavily on a high-dimensional CLS hyperplane rather than calibrated uncertainty.
   - `fit_selective_rejector_from_arrays` (`train_boundary_candidate.py:548`) requires **`total_unsafe == 0`** strictly on the `885`-row CAL set. In `v5-r2`, the single CAL error (`"Do your brick-and-mortar shops accept walk-in returns?"`, `return_policy conf=0.811`, `s=0.7536`) forced `tau=0.76, C=0.15` (from `v4p1` `tau=0.72, C=0.75`; `feasible: 101 -> 60`), cutting too tightly around CAL embeddings and vetoing `13/13` correct unseen `SUPPORTED_11` drafts (`noise420` typos, `pos175`, `sa156`).

---

## 4. Recommendation & Uncertainties

- **Do NOT run another quarantine/seed/threshold micro-tweak.** It cannot resolve `return_policy` vs `return_product_in_store` policy-question overlap or `track_order` vs `track_delivery` Bitext overlap, and the `776d` hard-zero CAL rejector is net harmful (`-10` `noise420`, `-2` `pos175` `gate`, `0` unsafe leaks stopped in `pos175`/`noise420`/`oos80`).
- **Next Step (requires B/C review before any code, data, or training):**
  1. **Evaluate dropping/ablating the `776d` rejector** (uncalibrated `bare` on `v5-r2` already recovers `263` on `noise420` and `36/41` on `pos175` with `0` additional `esc34`/`oos` leaks in `gate_report_v5r2.json`).
  2. **Fix the root data/taxonomy conflict rather than keyword quarantine:** decide policy scope for store-return eligibility questions (`return_product_in_store` vs `return_policy` / KB coverage) and audit/rebalance the `263` `ambiguous_retained` generic `track_delivery` Bitext rows (`390` eff vs `track_order` `312` eff) before any new fit.
- **Uncertainties:** Offline simulation only (`_MockNoCallLLM`, `_OfflineValidSpyLLM`, `0` human participants); `noise420` `runner_noveto` is upper-bounded (`<= 260`) because unvetoed `delivery_issue` typos can still fail KB retrieval; `53`-row domain `sup11` CAL set is sensitive to single-sample shifts.
