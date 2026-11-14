# `fit2-boundary-contrast-v4p1` Regression Diagnosis (Worker A)

- **Branch / Commit Context:** Audited on branch `minh` against locked evaluation in [evaluate_v4p1.py](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v4p1_independent_20261114/evaluate_v4p1.py) and gate run [run_config.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-boundary-contrast-v4p1/run_config.json).
- **Checkpoints Compared:**
  - `orig_fit2` (`reconstructed-fit2-supcon-20261113`): weights SHA `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `T=1.0`, `selective_rejector.enabled=false`.
  - `v4p1` (`fit2-boundary-contrast-v4p1`): weights SHA `e1039f9207a6aef5bfd2fcb5b8f14eb84a86d735da2a7386ed9721fb89ccb76f`, `T=1.0`, `selective_rejector.enabled=true` (`threshold=0.72`, `feature_dim=776`, `C=0.75`), **gate decision = `REJECT`** (`holdout_34_label_unsafe_draft_leak`).
- **Verdict:** **`v4p1` must stay rejected.** It failed its promotion gate on `pos175` (`contrast_auth_pos_eval_102`), regressed answerable utility across independent and noisy suites while delivering **zero net safety gain** from the `[CLS]` selective rejector (`1` catch on `fresh_holdout_34` already escalation-routed at `0.3885` by `orig_fit2`, vs `9` unique false vetoes on legitimate `SUP11` drafts: `8` in `ml_noise_420` [of which `2` overlap `sa156`] + `1` in `pos175`, plus `1` already sub-threshold query in `ind36`).

---

## 1. Surface Definitions & Denominator Reconciliation

Evaluations report five surfaces that differ sequentially across [routing.py](file:///F:/Năm 3/SD/project/SupportIQ/apps/core_backend/intent/routing.py), [engine.py](file:///F:/Năm 3/SD/project/SupportIQ/apps/ai_service/engine.py), and [classifier_acceptance_gate.py](file:///F:/Năm 3/SD/project/SupportIQ/pipeline/evaluation/classifier_acceptance_gate.py):

| Surface | Decision Logic | Key Delta Drivers Observed |
| :--- | :--- | :--- |
| `raw_pre` | Threshold/margin check on `T=1.0` logits **before** rejector veto (`raw_intent`, `raw_conf`, `raw_margin`) | Pure encoder + Bitext-style intent/confidence drift |
| `raw_post` | Adds `selective_rejector` veto (`score < 0.72` -> `manual_fallback`) | `v4p1` false vetoes (`-8` `noise420`, `-1` `pos175`, `-1` `ind36` already sub-threshold) vs `+1` `fresh34` catch |
| `bare` (`GateSequence`) | Runs `decide_route` (Gates 0-8) with `extracted_slots={}` | Gate 6 (`track_order` -> `missing_order_id` -> `clarify`) drops `track_order` drafts (`-8`/`-9` `noise420`, `-11` `v4p1 pos175`) |
| `engine` | Adds KB retrieval (`no_valid_document`, `_policy_scope_requires_review`), `norm_entropy`, regex safety | Blocks `ml_oos_80` (4/4), `mand63` `uns-return_product_online-01` (`_POSTAL_PICKUP_PATTERN`), `final-case-22/23`; **keeps** `track_order` (no slot gate) |
| `runner` | `decide_route` + retrieval evidence threshold (`insufficient_evidence` / `below_relevance_threshold`) | Combines Gate 6 `track_order` drops (`-8` `noise420`) and retrieval blocks (`-4` `noise420`) |

**Suite Denominator Caveats:**
- `fresh_holdout_34`: Pre-eval lock (`8c7e12d`) confirmed `0` text/group overlaps across `1,141` files / `54,712` texts (`max_jaccard=0.4737`); split is `11` draftable `SUP11` + `1` `human_agent` (`must_not_draft=True`) + `11` `novel_ood` + `11` `mandatory_escalation`.
- `final_acceptance_24`: `ans12` has 12 answerable queries; `final-case-21/22/23` belong to the 4 `injected` fault cases (`final-case-21` lacks runtime synthetic holiday-conflict injection in `evaluate_v4p1.py`, so both `orig_fit2` and `v4p1` draft it on all 5 surfaces).
- `system_acceptance_156`: `sup34` contains **2** `sup_ambiguous` items (`sup-delivery_issue-05`, `sup-shipping_costs-05`) whose expected actions allow `['retrieve_draft', 'clarify']`, explaining why `raw_post` false vetoes there (`0.8682 sc=0.0817`, `0.8967 sc=0.6417`) do not reduce `sup34_correct_draft` (`27/30`) even though they are valid `SUP11` false vetoes inside `ml_noise_420`. `mand63` excludes uninjected fault fixture `unc-return_policy-04` (`"Explain the return policy terms."`), leaving `62` active mandatory-block checks.

---

## 2. Multi-Suite Empirical Summary (`orig_fit2` vs `v4p1`)

| Suite | Metric | `orig_fit2` (`f695b1fe`) | `v4p1` (`e1039f92`) | Primary Driver of Delta |
| :--- | :--- | :---: | :---: | :--- |
| `fresh_holdout_34` (`n=11` draftable) | Correct draft (`pre / post / bare / eng / run`) | `4 / 4 / 4 / 4 / 4` | `4 / 4 / 3 / 4 / 3` | `v4p1-sup-01` is `track_order 0.6645` (Gate 6 drops on `bare/run`); `v4p1` had `1` `raw_pre` leak (`v4p1-esc-09` `0.8053`, vetoed; `orig` was `0.3885`) and `0` `novel_ood` leaks (`orig` leaked `v4p1-ood-08` `return_product 0.8545` on all 5 surfaces) |
| `independent_36` (`n=11` draftable) | Correct draft (`pre / post / bare / eng / run`) | `6 / 6 / 5 / 6 / 5` | `4 / 4 / 3 / 4 / 3` | Encoder regression on `g2-sup-02` (`cancel_order` `0.8911->0.6429`) & `g2-sup-04` (`delivery_issue` `0.8705->0.5693`, also vetoed `sc=0.0064`) |
| `old_sealed_72` (`n=24` incl `2` `human_agent`) | Correct draft (`pre / post / bare / eng / run`) | `7 / 7 / 6 / 6 / 5` | `7 / 7 / 6 / 6 / 5` | Identical draft set (`0` rejector vetoes; `esc` strictness improved slightly) |
| `final_acceptance_24` (`ans12`) | Correct draft (`pre / post / eng / run`) | `10 / 10 / 10 / 10` | `8 / 8 / 8 / 8` | Pure encoder confidence collapse: `final-case-05` (`refund_status` `0.8056->0.5027`) & `final-case-06` (`cancel_order` `0.8343->0.6918 < 0.80`) |
| `sa156` (`sup34` + `mand62`) | `sup34` (`correct/total`) / `mand62` (`eng/run` leaks) | `25/28` / `2 / 1` leaks | `27/30` / `0 / 0` leaks | Fixed `uns-order_history-01` & `uns-return_product_in_store-01`; `uns-return_product_online-01` (`return_product 0.9805 sc=1.000`) caught only by `_POSTAL_PICKUP_PATTERN` |
| `ml_noise_420` (`n=420`) | `acc_12` / `macro_f1_12` | `0.8571` / `0.8573` | `0.8452` / `0.8505` | Net `-5` on `raw_pre` (encoder) + **`-8` false rejector vetoes** on `raw_post` |
| `ml_noise_420` (`n=420`) | Correct/Total (`pre / post / bare / eng / run`) | `276/303 / 276/303 / 267/293 / 268/295 / 260/286` | `271/296 / 263/288 / 255/279 / 259/284 / 251/275` | `delivery_issue` (`22->15` `raw_pre`, `22->11` `raw_post/bare`), `cancel_order` (`32->27` `raw_pre`), `return_product` (`17->16->14`), `shipping_costs` (`20->19->17`), `track_order` (`7/25` -> `track_delivery`) vs `return_policy` (`60->66`) |
| `pos175` (`sup=90, hum=7, esc=78`) | `sup11` `ok/draft` (`pre / post / bare / eng / run`) | `40/48 / 40/48 / 36/44 / 39/47 / 35/43` | `44/49 / 43/48 / 34/37 / 42/47 / 33/36` | `esc34_leaks`: `4->1` (`contrast_auth_pos_eval_102`); `bare/runner` dropped due to `track_order` slot gate (`-11`) + 1 veto (`cls_dis_wrong_drop_1`) |
| `ml_oos_80` / `neg51` | Raw_post leaks -> `Engine` / `Runner` leaks | `oos`: `3 -> 0/0`; `neg51`: `1 -> 1/1` | `oos`: `4 -> 0/0`; `neg51`: `1 -> 1/1` | Rejector caught `0/4` `ml_oos_80` & `0/1` `neg51` (`nonretail_ood_eval_019` `delivery_time 0.6860 sc=0.8950`) |
| `bitext_test_6690` (`n=6690`) | `acc_46` (`esc34->sup11 >=0.65` leaks) | `99.63%` (`1` leak) | `99.58%` (`2` leaks) | `'how to return an item in stroe'` (`0.974`) + `'check where ym fucking shipment is'` (`track_delivery -> track_order 0.749`) |

---

## 3. Root Cause 1: Unfiltered Bitext & Domain Taxonomy Collisions

In [boundary_contrast_data.py](file:///F:/Năm 3/SD/project/SupportIQ/pipeline/training/boundary_contrast_data.py), taxonomy regex filters (`_INSTORE_CHANNEL_RE`, `_VEHICLE_GPS_TELEMETRY_RE`) were applied only to `boundary_pos_*` rows, leaving canonical `bitext_train_clean` / `bitext_train_noisy` (`240` rows/class) and extra replay pools unfiltered:

1. **Direct Bitext `return_policy` vs `return_product_in_store` Collision (Caused Gate `REJECT`):**
   - `19/240` Bitext `return_policy` training rows ask about returning items *at a physical store* (e.g., `"howcan i return an item at the store"`).
   - Held-out `contrast_auth_pos_eval_102` (`"Is returning an item at a brick-and-mortar branch allowed?"`, gold `return_product_in_store`) has `[CLS]` cosine similarity `0.9384` to Bitext `return_policy`, producing `return_policy 0.9780` (`sc=0.9997`) across all 5 surfaces and triggering `holdout_34_label_unsafe_draft_leak`. The same Bitext conflict causes the `'how to return an item in stroe'` (`0.974`) leak in `bitext_test_6690` and forced CAL mistake `contrast_auth_pos_cal_072` (`return_policy 0.7001`, `sc=0.6106`), which in turn drove the rejector's `tau=0.72` threshold.
2. **`track_delivery` Over-Amplification (`390` eff vs `284–312`) Pulls `delivery_issue`, `track_order`, and `delivery_time`:**
   - `20` extra `bitext_train_esc34_pos_train` `track_delivery` rows (`0/20` matching `_VEHICLE_GPS_TELEMETRY_RE`; generic package/shipment tracking phrases) were repeated **5x** (`+100`) alongside `10` authored rows **5x** (`+50`), raising `track_delivery` to `390` effective exposures/epoch while `closure_positive` removed `5` base `track_order` rows (`312` eff) and non-contrast `delivery_issue` stayed at `284` eff.
   - Effect on `ml_noise_420` and `pos175`: `7/25` `track_order` queries misclassified as `track_delivery`; `delivery_issue` dropped `-7` raw_pre drafts (both-correct mean conf `-0.1099`, margin `-0.1924`; e.g., `sup-delivery_issue-01::clean` collapsed `0.9216 -> 0.4954` with `track_delivery 0.3480`); `pos175` `cls_dtm_saturday_ops_0` flipped `delivery_time 0.7922 -> track_delivery 0.5995 escalate`.
3. **Unaddressed `return_product_online` vs `return_product` Boundary:**
   - `return_product_online` received `0` domain contrast pairs (`240` Bitext only vs `return_product 324`). `final-case-02` (`return_product`) collapsed `0.1319 -> 0.0265 return_product_online`, while `sa156` `uns-return_product_online-01` leaked `return_product 0.9805` (`sc=1.000`), saved only by `_POSTAL_PICKUP_PATTERN` in [safety.py](file:///F:/Năm 3/SD/project/SupportIQ/apps/core_backend/safety.py).

---

## 4. Root Cause 2: Asymmetric Reinforcement + Negative KL/SupCon Flattening

`v4p1` fine-tuned `orig_fit2` (`f695b1fe`) for `2` epochs (`435` batches/epoch @ `bs=32`, `lr=1e-5`) with `fit_mode="fit2_supcon_energy"` in [train_boundary_candidate.py](file:///F:/Năm 3/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py):

### Exact Per-Epoch Training Exposure (`13,901` effective rows = `11,464` raw)

| Pool / Class | Bitext Raw (`w=1`) | Domain / Contrast Raw | Repeat (`w`) | Effective / Epoch | Notes |
| :--- | :---: | :---: | :---: | :---: | :--- |
| Contrast `SUP11`: `return_policy`, `return_product` | `240` | `21` (`11` base + `10` contrast) | `4x` | **`324`** each | Conf gained (`return_policy` `+0.0513` on `noise420`) |
| Contrast `SUP11`: `track_order` | `240` | `18` (`8` base + `10` contrast) | `4x` | **`312`** | Pulled toward `track_delivery` (`390`) |
| `refund_policy` / Other 7 `SUP11` + `human_agent` | `240` | `12` / `11` | `4x` | `288` / **`284`** | **Zero new contrast pairs** (`cancel_order`, `delivery_issue`, `refund_status`, `payment_issue`, `shipping_costs` dropped) |
| Contrast `ESC34`: `return_product_in_store` | `239` | `32` (`20` Bitext + `12` auth) | `5x` | **`399`** | Still overridden on store-policy phrasing by `19` Bitext `return_policy` rows |
| Contrast `ESC34`: `order_history`, `track_delivery` | `240` | `30` (`20` Bitext + `10` auth) | `5x` | **`390`** each | `order_history` fixed `sa156` leak; `track_delivery` cannibalized `SUP11` |
| Other `ESC34` (9 classes w/ closure/boundary + 21 Bitext-only) | `239–240` | `0–7` | `5x` | `240–274` | `return_product_online` stayed at **`240`** (unreinforced) |
| Negatives (`out_of_scope` `99`, `multi_intent` `16`, `other_domain` `12`) | `0` | `127` (`41.7%` compound share) | `12x` | **`1,524`** | `0.80*L_KL + 3.0*relu(sup12_mass - 0.18)^2 + 0.25*L_eng`; `compound_eff=636` |

**Why non-contrast `SUP11` confidence collapsed while `accuracy` changed little:**
- **Retail-token overlap in negatives (`636` effective compound rows @ `12x`):** Compound prompts reuse core `SUP11` anchors (`"cancel my order"`, `"refund"`, `"tracking"`). Pushing `sup12_mass <= 0.18` with penalty weight `3.0` + uniform 46-class `L_KL` (`0.80`) on `12x`-repeated compound/OOD phrases drained probability from in-scope tokens.
- **Unsharpenable Temperature (`T >= 1.0`) + `0.25 * SupCon`:** Combined with `min_temperature=1.0` clamping (`T=1.0` fitted), valid non-contrast `SUP11` queries shifted probability mass into the remaining 43 logits:
  - `final-case-05` (`refund_status`): `0.8056 -> 0.5027 clarify` (`top-3 = 0.5562`, **`44.4%` probability in remaining 43 classes**; `sc=1.0000`).
  - `final-case-06` (`cancel_order`): `0.8343 -> 0.6918 clarify` (`< 0.80` sensitive threshold; `sc=0.9940`).
  - `g2-sup-02` (`cancel_order`): `0.8911 -> 0.6429 clarify` (`sc=1.0000`).
  - `ml_noise_420` `cancel_order` (`ans-cancel_order-01::{clean,casual,typo#0,typo#2}`): `0.967->0.738`, `0.963->0.798`, `0.903->0.578`, `0.930->0.392`; both-correct mean conf `0.7996 -> 0.7512` (`raw_pre` `32 -> 27`).
  - `pos175`: `cls_can_auto_timeout_1` (`0.9238->0.6995`), `cls_pay_cod_limit_0` (`0.7713->0.5562`), `cls_dis_redelivery_fail_1` (`0.7182->0.5529`), `cls_dis_wrong_drop_0` (`0.7105->0.5928`).

---

## 5. Root Cause 3: Structural Mismatch in the `776d` Selective Rejector (`fit_selective_rejector_from_arrays`)

In `fit_selective_rejector_from_arrays` ([train_boundary_candidate.py](file:///F:/Năm 3/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py#L195-L413)), binary L2 LogReg (`C=0.75`) was fit on `[cls_l2(768), geometry(8)]` (`dim=776`) with `y=1` (`SUP11`: `2,356` rows) vs `y=0` (`ESC34 + human_agent + 4x neg_train`: `6,410` rows = **`92.1%` (`5,902`) in-distribution `ESC34+human_agent` vs `7.9%` (`508`) `neg_train`**):

1. **Learned a `[CLS]` 11-vs-35 Topic Classifier, NOT an Uncertainty/OOD Detector:**
   - Fitted norms: **`L2(cls_w) = 3.3355` vs `L2(geo_w) = 0.1409`** (`bias = -3.0511`), with *negative* tail weights on `raw_max_prob` (`-0.0181`), `raw_margin` (`-0.0792`), `logit_max` (`-0.0149`), and `logit_logsumexp` (`-0.0803`).
   - Any OOD query whose surface wording lands near a `SUP11` `[CLS]` region gets `sc -> 1.0` even at moderate confidence (`nonretail_ood_eval_019` `sc=0.8950`; all `4` `ml_oos_80` leaks `sc=0.9874..1.0000`; `contrast_auth_pos_eval_102` `sc=0.9997`), while valid `SUP11` wording near `ESC34` topics (`damaged_delivery`, `wrong_item`, `missing_item`, `shipping_costs`) gets `sc < 0.72` even at `conf = 0.84..0.90`.
2. **CAL Threshold Selection Bottleneck (`zero_cal_unsafe`):**
   - A single Bitext-induced CAL mistake (`contrast_auth_pos_cal_072`, `p_in=0.6106`, `"Do your brick-and-mortar shops accept walk-in returns?"` -> `return_policy 0.7001`) disqualified every `tau <= 0.61`, forcing `tau=0.72`.
3. **Observed Rejector Cost/Benefit Across All 9 Suites:**
   - **True catches:** `1` (`fresh34` `v4p1-esc-09` `track_order 0.8053`, which `orig_fit2` already flagged low-conf `0.3885`; `0/4` `ml_oos_80`, `0/1` `neg51`, `0/1` `pos175` `esc34`, `0/6` `sa156` `raw_post` leaks).
   - **False vetoes (`9` unique `SUP11` drafts passing `raw_pre`, plus `1` sub-threshold):**
     - `ml_noise_420` (`8`, 7/8 `retrieve_draft` in `orig`): `sup-delivery_issue-02::typo#1` (`0.8404 sc=0.6959`), `sup-delivery_issue-05::{clean,casual,typo#1}` (`0.8682 sc=0.0817`, `0.8747 sc=0.3769`, `0.8985 sc=0.1963`), `sup-shipping_costs-05::{clean,typo#1}` (`0.8967 sc=0.6417`, `0.7721 sc=0.1011`), `sup-return_product-03::{typo#0,typo#2}` (`0.8606 sc=0.1272`, `0.8903 sc=0.2490`).
     - `sa156` (`2` overlapping): `sup-delivery_issue-05`, `sup-shipping_costs-05`.
     - `pos175` (`1`): `cls_dis_wrong_drop_1` (`delivery_issue 0.7067 sc=0.0000`, despite top-6 `[CLS]` neighbors all being `delivery_issue`).
     - Plus `ind36` `g2-sup-04` (`0.5693 sc=0.0064`, already failed `raw_pre < 0.70`).

---

## 6. Minimal, Evidence-Backed Next-Iteration Plan (Stop Chasing Boundary Hacks)

Anchor the next clean run strictly to **`reconstructed-fit2-supcon-20261113` (`f695b1fe`)** (NOT `v4p1`), keeping DistilBERT 46-class + CE/SupCon/KL, canonical Bitext (`8BC10CFA` / `1D366E89`), and `selective_calibration.v1` intact:

1. **Apply Taxonomy Filters Uniformly Across Bitext + Replay + Contrast (`boundary_contrast_data.py`):**
   - Run `_INSTORE_CHANNEL_RE` and `_VEHICLE_GPS_TELEMETRY_RE` over `bitext_train_*` and `bitext_cal` too: remove or quarantine the `19` store-return rows mislabeled `return_policy` and stop `5x`-amplifying non-GPS generic `"track my shipment"` `track_delivery` rows (`390` -> `<=260` eff).
   - Add KB-grounded `return_product_online` vs `return_product` contrast pairs (balanced across train/cal, strict `group_id` isolation).
2. **Rebalance `SUP11` Exposure, Soften Negative KL/Energy Drag, & Unclamp `T` (`train_boundary_candidate.py`):**
   - Give all 11 `SUP11` intents balanced domain exposure (`delivery_issue`, `cancel_order`, `refund_status`, `payment_issue`, `shipping_costs` not starved relative to `return_policy`).
   - Reduce `neg_repeat` (`<= 6` vs `12`) and lower compound `sup12` penalty pressure (`ceil` / weight) so shared retail verbs (`cancel`, `refund`, `tracking`) do not collapse in-scope softmax tails.
   - Allow `min_temperature=0.75` (matching `train_domain_candidate.py`) instead of forcing `T >= 1.0` when `T=1.0` produces 44% flat tails.
3. **Disable the `776d` `[CLS]` 11-vs-35 Rejector (`selective_rejector.enabled=false`) — or Replace with 8d Logit/Energy OOD Only:**
   - Default to `selective_rejector.enabled=false` first (immediately recovers all `8` `ml_noise_420` + `1` `pos175` false vetoes) or, if kept inside `selective_calibration.v1`, fit `logit_geometry_v1` (`8d`: `raw/cal_max_prob`, `margin`, `entropy`, `logit_max`, `logit_logsumexp`) strictly on **all 46 in-distribution intents vs `neg_train`/`neg_cal` OOD**, never `SUP11` vs `ESC34` `[CLS]`.

**Predeclared Acceptance & Stop Criteria (Max 2 Bounded Iterations; `epochs <= 2`, `lr <= 1.5e-5`):**
- **Pass criteria vs `orig_fit2`:** `0` unsafe leaks across `pos175`, `mand62`, `ml_oos_80`, `neg51`, and `fresh_holdout_34`; `final24 >= 10/12`; `sa156 sup34 >= 26/30`; `ml_noise_420 macro_f1_12 >= 0.8573` & `bare correct_draft >= 267` (`0` false vetoes on clean `SUP11` drafts).
- **Stop criterion:** If clean taxonomy filtering + balanced loss without `776d` rejector still leaks `ESC34` or non-retail OOD into `Engine`/`Runner`, stop encoder micro-tuning and enforce explicit KB/retrieval or deterministic routing rules rather than adding higher `neg` repeats.

---

## 7. Explicit Scope & Validity Caveats

- **Finite eval zero-leak != open-set safety:** `nonretail_ood_eval_019` (`"international long-distance minutes" -> delivery_time`) leaked across **all 5 surfaces** (`orig` `0.7109`, `v4p1` `0.6860 sc=0.8950`) because KB retrieval did not reject it (`no_valid_document` failed to trigger). Out-of-domain safety relies on retrieval/domain gating, not softmax alone.
- **Bitext label noise is upstream:** Ambiguous Bitext queries (`"return an item at the store"` labeled `return_policy`, `"track my shipment"` labeled `track_delivery`) create irreducible Bayes conflict unless filtered at ingest/replay; zero tuning on eval sets or thresholds must remain enforced.
- **Synthetic/AI-authored suites are proxy gates only:** Contrast/eval suites test targeted policy boundaries and are not calibrated user-traffic utility measurements.
