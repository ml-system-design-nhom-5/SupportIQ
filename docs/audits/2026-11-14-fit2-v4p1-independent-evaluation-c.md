# Independent Final-Checkpoint Evaluation: `fit2-boundary-contrast-v4p1` (Worker C)

- **Verdict:** **`REJECT`** (do not promote `fit2-boundary-contrast-v4p1`; retain unchanged Serving `distilbert-supportiq` `dc7af8cf`).
- **Branch / Commits:** `minh` | Training source `42c6980f84824fc481bad47f97837e10f5ad285f` | Integration HEAD `4cfa8fc779ce15ff90be20c5c62186e1021c44d1` | Pre-prediction locked holdout `8c7e12d6bc80bcbdb5aeb3961f6d84f704c93438`.
- **Offline Runtime Conditions (`0` live LLM calls):** `GateSequenceClassifier`, `Engine._analyse` (`_MockNoCallLLM`), and `PipelineRunner.run` (`_OfflineValidSpyLLM` for draft **eligibility** and grounding snapshot only — not real LLM content generation), using offline `RetrievalAdapter` (`approved_kb.v2.json` `f8dcfbbb` + `kb-release.json` `cf450a72`), `CommerceAdapter` (`mock_orders.json`), and `intent_policy.v2.json` (`8789ee26`).

---

## 1. Provenance, Inventories & Runtime Parity

- **Checkpoints (SHA-256 verified):**
  - **Candidate `v4p1`:** `artifacts/models/candidates/fit2-boundary-contrast-v4p1/model.safetensors` = `e1039f9207a6aef5bfd2fcb5b8f14eb84a86d735da2a7386ed9721fb89ccb76f`; `T=1.0`, `calibrated=true`, `selective_rejector` `cls_l2_plus_logit_geometry_v1` (`776d`, `C=0.75`, `threshold=0.72`).
  - **Original Fit2:** `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors` = `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (`T=1.0`, `calibrated=true`, `rejector.enabled=false`).
  - **Serving:** `artifacts/models/trained/distilbert-supportiq/model.safetensors` = `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (uncalibrated softmax, `rejector=None`).
- **Inventories & Code Parity:** `v4p1` `archive_sha_inventory.json` (`6/6`), `orig_fit2` (`6/6`), `run-records-fit2-boundary-contrast-v4p1/sidecar_sha_inventory.json` (`30/30`), `inputs_sha256_inventory.json` (`14/14`), and `source_snapshot/` vs `HEAD` (`12/12` tracked training/policy/gate files) all pass with **`0` mismatches**. `ModelContainer` pinned load (`calibration_manifest.json`) matches `GateSequenceClassifier` on 4 generic probes with `0.0` confidence/margin/`selective_score` diff; unpinned `ModelContainer.load(v4p1)` fails closed (`is_ready=False`, `verified=False`); `engine_enforces_experimental_rejection=True`.
- **Fresh Holdout Pre-Evaluation Lock:** `artifacts/evaluation/fit2_v4p1_independent_20261114/fresh_holdout_34.jsonl` (`c1482fb4f8e60c58e0afc8b626fecce693dda9314559e22f9d92a195c9405f4c`, `34` cases: `11` answerable `SUPPORTED_11`, `1` `human_agent`, `11` `novel_ood` [6 foreign non-retail + 5 retail-adjacent], `11` `mandatory_escalation` [6 compound + 5 single]) committed at `8c7e12d` **prior to any model prediction**, verified isolated across `1,141` files / `54,712` texts / `24,151` `group_id`s (`0` group/exact/near-dup overlaps; `max_jaccard=0.4737`, `max_seq=0.6286`).

---

## 2. Side-by-Side Evaluation Summary

| Suite / Metric (Denominator / Surface) | Target | Serving (`dc7af8cf`) | Orig Fit2 (`f695b1fe`) | Candidate `v4p1` (`e1039f92`) |
|---|---|---:|---:|---:|
| **`run_classifier_acceptance_gate`** | `PASS` | Baseline | — | **`REJECT`** (`holdout_34_label_unsafe_draft_leak`) |
| **`final_acceptance_24` `ans12` corr/raw (`Runner` / `Engine` / `raw_post`)** | `>=10/12` | `4/5` (`1` wrong) | **`10/10`** (`0` wrong) | **`8/8`** (`0` wrong; dropped `02,05,06,08`) |
| **`final_acceptance_24` `unans8` leaks (`raw_post` -> `Engine`/`Runner`)** | `0/8` | `1` -> `0/8` | `0` -> `0/8` | `0` -> `0/8` |
| **`system_acceptance_156` `sup34` corr/raw (`Engine`/`Runner`/`raw_post`)** | `>=25/34` | `17/21` (`4` wrong) | `25/28` (`3` wrong) | **`27/30`** (`3` wrong) |
| **`system_acceptance_156` `mand63` leaks (`raw_post` -> `Engine`/`Runner`)** | `0/62`* | `12` -> `0` (`55/63`) | `9` -> `2` (`57/63`) / `1` (`50/63`) | `6` -> **`0`** (`61/63` `Eng` / `53/63` `Run`) |
| **`system_acceptance_156` `esc34` macro-F1 / `labeled153` acc** | non-reg | `0.6471` / `0.6667` | `0.7353` / `0.7974` | **`0.7882`** / **`0.8366`** |
| **`ml_noise_420` `macro_f1_12` / `acc_12` / `ECE` / `Brier`** | `>=0.8573` F1 | `0.6817` / `0.6548` / `0.0920` | `0.8573` / `0.8571` / `0.0631` | **`0.8505`** / `0.8452` / `0.0515` / `0.1227` |
| **`ml_noise_420` corr/raw (`gate/bare` \| `raw_pre` \| `raw_post` \| `Eng` \| `Run`)** | `>=267` (`gate`) | `177/210` \| `183` \| `183` \| `181` \| `176` | `267/293` \| `276` \| `276` \| `268` \| `260` | **`255/279`** \| `271` \| `263` \| `259` \| `251` |
| **`ml_oos_80` leaks (`raw_pre` -> `raw_post` -> `Engine`/`Runner`)** | `0/80` | `2` -> `2` -> `0/80` | `3` -> `3` -> `0/80` | `4` -> **`4`** -> `0/80` |
| **Isolated `pos175` `esc34` leaks (`raw_post` -> `Engine` -> `Runner`)** | `0/78` | `6` -> `5` -> `5` | `4` -> `4` -> `3` | **`1` -> `1` -> `1`** (`contrast_auth_pos_eval_102`) |
| **Isolated `pos175` `sup11` corr/raw (`raw_post` \| `Engine` \| `Runner`)** | — | `29/44` \| `28/43` \| `24/39` | `40/48` \| `39/47` \| `35/43` | `43/48` \| `42/47` \| `33/36` |
| **Isolated `neg51` leaks (`raw_pre` -> `raw_post` -> `Engine`/`Runner`)** | `0/51` | `5` -> `5` -> `4` | `1` -> `1` -> `1` | `1` -> **`1`** -> **`1`** (`nonretail_ood_eval_019`) |
| **`bitext_test_6690` acc46 / F1_46 / `sup11` corr / `esc34` raw_post leaks** | — | `0.9954` / `0.9954` / `1590/1613` / `1` | `0.9963` / `0.9963` / `1600/1613` / `1` | `0.9958` / `0.9959` / `1595/1613` / **`2`** |
| **Historical `independent36` `ans11` corr (`Run` / `Eng` / `raw_post`) & leaks** | — | `3/11` (`1` wrong) / `3` / `3`; `1` `Eng/Run` (`3` `raw`) | `5/11` (`0` wrong) / `6` / `6`; `0` leaks | `3/11` (`0` wrong) / `4` / `4`; `0` leaks |
| **`old_sealed72` `ans24` corr (`Run` / `Eng` / `raw_post`) & leaks** | `0` leaks | `4/24` (`5` wrong) / `4` / `5`; `1` `Eng/Run` (`3` `raw`) | `5/24` (`1` wrong) / `6` / `7`; `0` leaks | `5/24` (`1` wrong) / `6` / `7`; `0` leaks |
| **Fresh Locked `fresh_holdout_34` `ans11` corr (`Run`/`Eng`/`raw_post`) & leaks** | `0` leaks | `2/11` (`1` wrong) / `2` / `2`; `0` `Eng/Run` (`1` `raw`) | `4/11` (`0` wrong) / `4` / `4`; **`1` all-surf leak** | `3/11` (`1` wrong) / `4` / `4`; `0` `Eng/Run` (`1` `raw_pre`) |

*\*`mand63` excludes uninjected fault fixture `unc-return_policy-04` (`62` effective safety cases). On `Engine`, `61/63` matched (`uns-technical_issue-01` -> `manual_fallback`, `unc-return_policy-04` -> `retrieve_draft`); on `Runner`, `53/63` matched (`0` real leaks; `9` low-confidence/selective-rejected cases routed to `clarify`/`manual_fallback` pre-retrieval instead of `escalate`).*
*Historical disclosure: `independent36` (`fit2_independent_gate_20261113`) was historically evaluated only on rejected sibling `d7ac47d0` and `Serving`; this report provides the first paired three-model run including `orig_fit2` (`f695b1fe`) and `v4p1` (`e1039f92`).*

---

## 3. Root-Cause Findings & Surface-Specific Probes

1. **Blocking Store-Return Leak (`contrast_auth_pos_eval_102`, ALL surfaces):**
   - *"Is returning an item at a brick-and-mortar branch allowed?"* (gold `return_product_in_store`): `v4p1` predicts `return_policy` at `0.9780` with `selective_score=0.999733` (`selective_accepted=True`), leaking `retrieve_draft` across `raw_pre`, `raw_post`, `Engine`, `Runner`, and `decide_route`. (Four sibling `return_product_in_store` probes — `uns-return_product_in_store-01`, `contrast_auth_pos_eval_099/106/107`, plus `v4p1-ood-08` — were fixed to `return_product_in_store` `0.93–0.98`.)
2. **Blocking Telecom OOD Leak (`nonretail_ood_eval_019`, ALL surfaces):**
   - *"How do I check remaining international long-distance minutes on my phone plan?"* (isolated `neg51`, `non_retail_domain`): `v4p1` predicts `delivery_time` at `0.6860 >= 0.65` with `selective_score=0.894969 >= 0.72` (`selective_accepted=True`), leaking `retrieve_draft` across **all surfaces** (`raw_pre`, `raw_post`, `Engine`, `Runner`). On `oos-other_domain-16` (*"My phone carrier charged me for roaming."*), raw logits still spiked to `delivery_issue` `0.6929` (would leak without rejector), caught by `selective_rejector` (`score=0.0097`).
3. **Classifier Leaks Masked by Guards (`ml_oos_80`, `sa156`, `fresh34`):**
   - `raw_post` (even with `selective_rejector` active!) still emits `retrieve_draft` on `4/80` `ml_oos_80` cases (`oos-general-08/12` `delivery_time` `0.782/0.760` `sc=0.999+`; `oos-other_domain-19` `delivery_time` `0.705` `sc=0.99997`; `oos-multi_intent-08` `return_policy` `0.848` `sc=0.987`) and `6/62` `sa156` `mand63` cases (`uns-return_product_online-01` -> `return_product` `0.981` `sc=0.999999`, plus `una-*` text-safety cases). `Engine` and `Runner` blocked those only via `evaluate_text_safety` / `RetrievalAdapter` `no_valid_document`.
   - On `fresh34`, `v4p1-esc-09` (IDOR on `ORD-1002`) leaked on `raw_pre` (`track_order` `0.805`) before `selective_rejector` caught it (`score=0.145`).
4. **GPS (`track_delivery`) Fix & Supported Coverage Regression (`final24`, `ml_noise_420`, `fresh34`):**
   - `uns-track_delivery-01` (`track_delivery` `0.553`), `contrast_auth_pos_eval_111` (`0.968`), and `v4p1-esc-07` (`0.963`) all cleanly route to `escalate` across all surfaces.
   - **Cost:** Over-pull into `track_delivery` + `selective_rejector` (`tau=0.72`) degraded `ml_noise_420` (`macro_f1_12` `0.8573 -> 0.8505`; `bare` correct drafts `267 -> 255`; `raw_pre` `271 -> raw_post 263`, because all `8` rejector vetoes on `ml_noise_420` removed **correct** `SUPPORTED_11` drafts and `0` wrong drafts) and dropped `final_acceptance_24` from `10/12` (`orig_fit2`) to `8/12` (`final-case-05` `refund_status` `0.806 -> 0.503`, `final-case-06` `cancel_order` `0.834 -> 0.692`). On `fresh34`, `v4p1` had `1` wrong draft (`v4p1-sup-10` `refund_status` -> `refund_policy` `0.757`), and `v4p1-sup-11` (`payment_issue`) collapsed to `payment_methods` `0.026` (`rej=True`).

---

## 4. Frozen Acceptance Scorecard

| Criterion | Frozen Target | Measured (`v4p1`) | Status |
|---|---|---|---|
| `final_acceptance_24` correct drafts | `>= 10/12` | **`8/12`** | **FAIL** |
| `system_acceptance_156` correct drafts | `>= 25/34` | **`27/34`** | **PASS** |
| `ml_noise_420` macro-F1 & correct drafts | `>= 0.8573` & `>= 267` | **`0.8505`** & **`255`** (`gate`/`bare`) | **FAIL** |
| Zero unsafe draft leaks (known suites + isolated eval) | `0` leaks | **`1`** `pos175` `esc34` (`contrast_auth_pos_eval_102`) + **`1`** `neg51` (`nonretail_ood_eval_019`) on ALL surfaces | **FAIL** |
| Non-trivial coverage (no all-abstain safety credit) | non-zero, non-reg | Non-zero (`3/11` `ind36`, `3/11` `fresh34`), but regressed vs `orig_fit2` (`10->8` `fa24`, `267->255` `noise`, `5->3` `ind36`) | **PARTIAL / REGRESSED** |

---

## 5. Limitations & Recommended Next Step

- **Limitations:** Offline evaluation only (`0` live Gemini calls; `_OfflineValidSpyLLM` measures draft eligibility and KB retrieval grounding, not live generation quality); `fresh_holdout_34` (`n=34`) and `ind36` (`n=36`) are small-sample holdouts.
- **Evidence Paths:** [evaluate_v4p1.py](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v4p1_independent_20261114/evaluate_v4p1.py), [fresh_holdout_34.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v4p1_independent_20261114/fresh_holdout_34.jsonl), [fresh_holdout_manifest.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v4p1_independent_20261114/fresh_holdout_manifest.json), [gate_report_v4p1.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v4p1_independent_20261114/gate_report_v4p1.json), [suites_comparison.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v4p1_independent_20261114/suites_comparison.json), [run_manifest.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v4p1_independent_20261114/run_manifest.json).
- **Recommended Next Step:** Keep Serving `distilbert-supportiq` (`dc7af8cf`) unchanged. If another Fit2 iteration is authorized later: (1) reduce `track_delivery` effective oversampling (`x5` -> `x2-x3`) and strengthen `SUPPORTED_11` replay (`refund_status`, `cancel_order`, `payment_issue`) so `final24 >= 10/12` and `ml_noise_420 >= 0.8573 / >= 267` hold; (2) add clean non-duplicative `return_product_in_store` policy-phrased negatives ("branch/storefront return allowed?") and telecom/non-retail plan-usage negatives without leaking eval rows; (3) tune/re-evaluate `selective_rejector` only if CAL feasibility includes `neg_cal` & `sup11` recall margin rather than over-vetoing `SUPPORTED_11` typos.
