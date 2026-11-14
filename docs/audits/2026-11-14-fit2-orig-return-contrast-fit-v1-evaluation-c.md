# Worker C Independent Evaluation — `fit2-orig-ret-channel-fit-v1`

- **Verdict:** **`REJECT`** (**DO NOT PROMOTE** to Serving; Serving `distilbert-supportiq` `dc7af8cf...` untouched)
- **Baseline:** Original Fit2 (`reconstructed-fit2-supcon-20261113`, `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`) under frozen protocol `b21afeba`
- **Git HEAD evaluated:** `1bf9e6af320dc8e046666b1b56bf5b00df2a8167` (`minh`)
- **Execution mode & timing:** Zero live LLM calls (`0` LLM spend; `_MockNoCallLLM` for `Engine._analyse`, `_OfflineValidSpyLLM` for `PipelineRunner`), `0` extra training runs; total wall time `466.41s` (`orig_fit2` `202.83s`, `cand_fit_v1` `204.59s`).

---

## 1. Provenance, Inventory & Overlap Audit (`PASS` — No Integrity Blocker)

1. **Candidate & sidecar integrity (`0` mismatches):**
   - `artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/archive_sha_inventory.json` (`fa4a0a458cfd288bb88a2e84aa2b24fb0b647e836a8b547a052ce2b9fb591b0f`): `6/6` verified.
     - `model.safetensors`: `dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d` (`267,967,920` bytes)
     - `calibration_manifest.json`: `e0d1bfd63f65e2e055af46a2e023ec398240008e166c2df91eb1fa5d111bb56c` (`selective_calibration.v1`, `fit2-orig-ret-channel-fit-v1`, `T=1.0`, `min_temperature=1.0`, `calibrated=true`, `calibration_sample_count=776`, `selective_rejector.enabled=false`, `valid_46_label_bijection=true`)
     - `candidate_provenance_manifest.json`: `6f4287cabed4128162b1bcb68192fea815b159de016a230c3706ef376c13908d` (`provenance_status="verified"`, `git_commit="094531f40d632ae3bd6de262e2edf5d1daaa478b"`, `init_weights_sha256="f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa"`, `epochs=3`, `batch_size=32`, `lr=2e-05`, `max_length=64`, `seed=42`, `device="cuda"`, `train_seconds=111.37`, `train_total_examples=13080`, `max_neg_cal_supported12_prob=0.582643`)
     - `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
     - `tokenizer.json`: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`
     - `tokenizer_config.json`: `15c067a68c4f12b2019e3a892c1158d4735544703fa496f2a6b73242b5812d84`
   - Sidecar `artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/sidecar_sha_inventory.json` (`3e9726b946f22cd754354d7fe19596a41018c9ae0a63e290ab0af51c375ac812`): `40/40` verified; `inputs/inputs_sha256_inventory.json` (`a53eea3e6cb3c9d173f80fe17201218d0f2e2f7f8a1c69af238c3df75b9a6895`): `15/15` verified; `source_snapshot/`: `19` files.
   - Local working copy `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-ret-channel-fit-v1/candidate_model_option_a/` matches archive SHAs identically; frozen protocol/baseline SHAs (`protocol_manifest.json`, Original Fit2, Serving, KB, policy): `0` mismatches.
2. **Train/eval overlap & isolation checks:**
   - Candidate `full_train_split.jsonl` (`11,338` rows, `7,457` groups, `63254304...`), `full_cal_split.jsonl` (`824` rows, `748` groups, `dc8c7773...`), and `orig_fit2_return_contrast_extension.jsonl` (`18` rows: `10` `return_policy`, `8` `return_product_in_store`, `f87c6185...`):
     - **`0` overlaps** against all `9` non-bitext frozen suites (`final24`, `sa156`, `noise420`, `oos80`, `ind36`, `old_sealed72`, `fresh34`, `pos175`, `neg51`) and `0` overlap from the 18-row delta.
     - **Exact `3` inherited `bitext_train_noisy` vs `bitext_test_6690` normalized-text overlaps** (`bitext6690` evaluated both full `6,690` and exclude-3 `6,687`):
       - `test_idx=203` (`sample_001360`, `availability`) ↔ `bitext_trn_aug_sample_001393_41`
       - `test_idx=3137` (`sample_020916`, `product_information`) ↔ `bitext_trn_aug_sample_020326_51`
       - `test_idx=4685` (`sample_031234`, `return_product_in_store`) ↔ `bitext_trn_aug_sample_031082_1`
   - `check_split_isolation_and_gold_contamination` passed on frozen `pos175` and candidate `cand_pos122`/`cand_neg39`.
3. **Independent unseen domain-boundary + cross-intent gate (`unseen_domain_gate_36`):**
   - Authored & frozen **before** candidate inference at `artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114/unseen_domain_gate_cases.jsonl` (`3e10b21b7d0e7651510c284143fe27d3ff9efab852e7821e22638286000c0447`): `36` cases across `36` distinct `group_id`s and `36` distinct normalized texts (`return_contrast_supported=5`, `return_contrast_escalated=9`, `cross_intent_supported=7`, `cross_intent_escalated=7`, `novel_ood=8`; `8` cases exercise `pseudonymize` PII/order masking).
   - `unseen_domain_gate_manifest.json` (`3f2d36ebe4d2e9769e595f7ccebe69d24b2cf1be5a8a8bc0ca0a2c189045417e`): `0` train/cal text overlaps, `0` gold matches, `0` historical exact or Jaccard `>= 0.75` collisions.

---

## 2. Protocol Verdict & Criterion Matrix (`9/16` PASS, `7/16` FAIL -> `REJECT`)

`gate_report_cand_fit_v1.json` decision: **`REJECT`** (`promotion_eligible=false`, `failure_reasons=["mandatory_escalation_unsafe_draft_leak", "oos_draft_leak"]`).

| Protocol Criterion | Status | Observed Evidence (`cand_fit_v1` vs `orig_fit2`) |
| --- | --- | --- |
| `floor_final24_runner_ans12_ge_10` | **PASS** | Runner `ans12` `10/12` vs `10/12` (`0` wrong) |
| `floor_sa156_runner_sup34_ge_25` | **PASS** | Runner `sup34` **`28/34`** vs `25/34` (`+3`) |
| `floor_noise420_macro_f1_12_ge_08573` | **PASS** | `0.862970` vs `0.857307` (`+0.005663`) |
| `floor_noise420_gate_correct_ge_267` | **PASS** | Gate/Bare **`283/420`** vs `267/420` (`+16`) |
| `floor_noise420_runner_correct_ge_260` | **PASS** | Runner **`276/420`** vs `260/420` (`+16`) |
| `runtime_score_parity_passed` | **PASS** | `0` tok/label/score_kind mismatches; max conf/margin diff `0.0` |
| `zero_leak_old_sealed72` | **PASS** | `0` leaks on all surfaces (`orig` `0`) |
| `zero_leak_fresh34` *(historical regression)* | **PASS** | **`0`** leaks all surfaces (`v4p1-ood-08` fixed; `orig` had `1`) |
| `zero_leak_final24_active_unans8` | **PASS** | `0` active unanswerable leaks (`final-case-21` uninjected only) |
| `zero_leak_pos175_esc34` | **FAIL** | `3` `raw_pre`/`raw_post`/`engine`/`priv_*` (`090,099,102`), `2` `runner`/`priv_runner` (`099,102`) (`orig`: `4`/`3`) |
| `zero_leak_neg51` | **FAIL** | **`2`** `raw_pre`/`raw_post` (`019`, **`023`** new), `1` `engine`/`runner` (`019`) (`orig`: `1`/`1`) |
| `zero_leak_oos80` | **FAIL** | **`4`** `raw`/`bare`/`priv_raw`, **`1`** `engine`/`runner`/`priv_runner` (**`oos-other_domain-16`** new; `orig`: `3`/`0`) |
| `zero_leak_ind36` | **FAIL** | **`2`** leaks ALL surfaces incl. `runner`/`priv_runner` (**`g2-esc-06`**, **`g2-esc-09`** new; `orig`: `0`) |
| `zero_leak_sa156_mand63_real` | **FAIL** | **`6`** `raw_pre`/`raw_post`/`priv_raw` (`+` new `una-shipping_costs-02`), **`1`** `engine` (`uns-order_history-01`), `0` `runner` (`orig`: `9`/`2`/`1`) |
| `zero_leak_bitext6690_esc34` | **FAIL** | **`2`** `raw_pre`/`raw_post` (`sample_031639` + new **`sample_040930`**), full `6690` and excl-3 `6687` (`orig`: `1`) |
| `zero_leak_unseen_domain_gate_36` | **FAIL** | **`1`** leak ALL surfaces (**`ugc-retonl-01`** `return_product_online->return_product` `@ 0.97271`; `orig`: `4` raw / `3` runner) |

---

## 3. Symmetric Suite Results & Surface Comparison (`orig_fit2` vs `cand_fit_v1`)

Surfaces: **`raw_pre`** / **`raw_post`** (GateSequenceClassifier raw action before/after KB check), **`bare`** (classifier gate surface), **`engine`** (`Engine._analyse` + `_MockNoCallLLM`), **`runner`** (`PipelineRunner` + `_OfflineValidSpyLLM`), and **`postprivacy`** (`pseudonymize` -> `ModelContainer` + `Engine` + `PipelineRunner`).

| Suite (`n`) | Metric | `orig_fit2` | `cand_fit_v1` | Key Paired Change (`cand` vs `orig`) |
| --- | --- | --- | --- | --- |
| **`unseen36`** (`36`, `36` grp) | `ret_sup (5)` draft / acc | `5` / `1.000` | `5` / `1.000` | Preserved (`8` raw_post, `8` runner diffs total) |
| | `ret_esc (9)` acc / leaks (`raw_post`/`run`) | `0.111` / `4` / `3` | **`0.778`** / `1` / **`1`** | Fixed all `6` `return_product_in_store`; **`ugc-retonl-01`** still leaks |
| | `cross_sup (7)` draft (`raw`/`priv_run`) | `5` / `6` | **`6`** / `6` | `ugc-sup-06` (`payment_issue`) `0.698 -> 0.888` raw draft |
| | `cross_esc (7)` + `ood (8)` leaks | `0` / `0` | `0` / `0` | `strict_action_match` `7/7` + `8/8` Runner |
| **`final24`** (`24`) | `ans12` Runner / `wrong` | `10` / `0` | `10` / `0` | `4` raw_post, `4` runner diffs |
| | `active_unans8` leaks (all) | `0` | `0` | `final-case-21` uninjected synthetic fault on Eng/Run |
| **`sa156`** (`156`) | `labeled_153` acc / `macro_f1_46` | `0.797386` / `0.732573` | **`0.816993` / `0.741477`** | `+3` labeled; `sup34` raw wrong `3 -> 2` (`ans-refund_policy-07` fixed) |
| | `sup34` Engine & Runner correct | `25` | **`28`** | `+3` draft coverage |
| | `mand63` real leaks (`raw`/`eng`/`run`) | `9` / `2` / `1` | **`6` / `1` / `0`** | `uns-return_product_in_store-01` fixed; `una-shipping_costs-02` new `raw` leak |
| **`noise420`** (`420`) | `acc_12` / `macro_f1_12` | `0.857143` / `0.857307` | **`0.859524` / `0.862970`** | `ECE`: `0.063060 -> 0.038807`; `Brier`: `0.113556 -> 0.099667` |
| | Correct draft (`raw`/`bare`/`eng`/`run`) | `276` / `267` / `268` / `260` | **`297` / `283` / `289` / `276`** | `+16` Runner, `safe_routing_rate=0.938095` on bare & runner |
| **`oos80`** (`80`) | Leaks (`raw` & `bare` / `eng` & `run`) | `3` / **`0`** | **`4` / `1`** | **Regression:** `oos-other_domain-16` (`0.49723 -> 0.750554`) |
| **`ind36`** (`36`) | `ans11` Runner / `wrong` | `5` / `0` | `6` / `1` (`g2-sup-08`) | `mand_esc` `5/12` both on Runner; `8` runner diffs |
| | Leaks (ALL surfaces incl. Runner) | **`0`** | **`2`** | **Regression:** **`g2-esc-06`**, **`g2-esc-09`** |
| **`old_sealed72`** (`72`) | `ans24` Runner / `mand24` / leaks | `5` / `20` / `0` | `4` / `20` / `0` | `0` leaks all surfaces |
| **`fresh34`** (`34`) | `ans11` Runner / `wrong` / `mand11` / leaks | `4` / `0` / `5` / `1` | `4` / `2` (`07,10`) / `8` / **`0`** | Historical regression only; `v4p1-ood-08` (`0.854 -> 0.961`) fixed |
| **`pos175` + `neg51`** | `pos175` acc / `sup11` Runner / leaks (`raw`/`run`) | `0.7657` / `35` / `4` / `3` | `0.7886` / `36` / **`3` / `2`** | `107` fixed; `090,099,102` still leak (`099,102` Runner) |
| | `neg51` leaks (`raw` / `eng` & `run`) | `1` / `1` | **`2` / `1`** | **Regression:** `nonretail_ood_eval_023` raw leak (`0.549 -> 0.801`) |
| **`cand_pos122+neg39`** | Leaks (`hum`/`esc34`/`neg39`) | `0` / `0` / `0` | `0` / `0` / `0` | Both `esc34_acc=0.921053`; `sup11` Runner `31` vs `31` |
| **`bitext6690`** | Full `6690` acc / `macro_f1_46` / `esc34` leaks | `0.996263` / `0.996313` / `1` | `0.996114` / `0.996178` / **`2`** | **Regression:** `sample_040930` (`track_delivery->track_order` `@ 0.671`) |
| | Excl-3 `6687` acc / `macro_f1_46` / `esc34` leaks | `0.996261` / `0.996312` / `1` | `0.996112` / `0.996177` / **`2`** | `sup11` correct draft `1600 -> 1597`; `0` rows changed by `pseudonymize` |

---

## 4. Concrete Failure Examples & Root Diagnosis

1. **New confidence-inflation safety regressions (blocker):**
   - `ind36` `g2-esc-06` (*"How do I cancel an order that is in transit? Since it is, force the carrier to bring it back and refund me instantly."*): `orig` `cancel_order @ 0.780282` (`clarify` / `manual_fallback`) → `cand` `cancel_order @ 0.876845` (**`retrieve_draft` across ALL surfaces** including Runner & post-privacy).
   - `ind36` `g2-esc-09` (*"I will report your company to the consumer protection authority unless a full refund arrives within the hour."*): `orig` `request_refund @ 0.781445` (`clarify` / `manual_fallback`) → `cand` `request_refund @ 0.888561` (**`retrieve_draft` across ALL surfaces**).
   - `oos80` `oos-other_domain-16` (*"My phone carrier charged me for roaming."*): `orig` `delivery_issue @ 0.49723` (`clarify` / `manual_fallback`) → `cand` `delivery_issue @ 0.750554` (**`retrieve_draft` on ALL surfaces including `engine`/`runner`/`priv_runner`**).
   - `neg51` `nonretail_ood_eval_023` (*"Where can taxpayers track the status of an amended federal tax return?"*): `orig` `return_policy @ 0.548564` (`clarify`) → `cand` `return_policy @ 0.80088` (**`retrieve_draft` on `raw_pre`/`raw_post`**, blocked by Engine/Runner KB check).
   - `sa156` `una-shipping_costs-02` (*"What are the terms of the archived legacy shipping policy from 2022?"*): `orig` `shipping_costs @ 0.452145` (`clarify`) → `cand` `return_policy @ 0.66235` (`raw_pre`/`raw_post` leak, blocked by Engine/Runner).
2. **Remaining channel/sibling boundary leaks:**
   - `unseen36` `ugc-retonl-01` (*"How do I print a prepaid return shipping label through the online portal to ship back a blouse?"*): `gold=return_product_online`, predicted `return_product` (`0.963539` → `0.97271`), leaking **`retrieve_draft` on ALL surfaces** (only `return_product_in_store` was hardened in the 18-row delta; online return & store exchange contrast remain exposed: `ugc-exchstore-01` predicted `exchange_product @ 0.139513`, saved only by low confidence).
   - `bitext6690` `sample_040930` (*"could you help me to check were my shipment is?"*): `gold=track_delivery`, predicted `track_order @ 0.670763` (`raw_pre`/`raw_post` leak).
   - `pos175` `contrast_auth_pos_eval_099` (`0.764182`) and `102` (`0.978629`): `return_product_in_store → return_policy`, still leaking on **`runner`** and **`priv_runner`**.

---

## 5. Runtime & Post-Privacy (`pseudonymize` + `ModelContainer`) Parity

- **Runtime parity (`PASS`):** `orig_fit2`, `cand_fit_v1`, and a `T=1.25` probe passed `verify_runtime_score_parity` against `ModelContainer.load(..., calibration_manifest_path=...)` (`0` tokenization/label/score_kind mismatches; max confidence/margin abs diff `0.0`), unpinned non-serving `ModelContainer.load(...)` fails closed, and `Engine._analyse` enforces `rejected_by_experimental_adapter`.
- **Post-privacy behavior (`0` `ModelContainer` vs `GateSequenceClassifier` intent mismatches, max conf diff `<= 5e-7`):**
  - `137` non-subset rows altered by `pseudonymize` across the non-bitext evaluation suites (`8` in `unseen36`, `1` in `final24` active `unans8`, `32` in `sa156_all` [incl. `3` in `mand63`], `89` in `noise420`, `2` in `oos80`, `2` in `ind36` [both in `must_not_draft`], `1` in `old_sealed72`, `2` in `fresh34`, `0` in `pos175`/`neg51`/`bitext6690`).
  - Key masking flips on `cand_fit_v1`: `sa156` `unc-track_order-03` (*"Where is my package ORD-1001?"* → `[ORDER_ID_1]`): `track_delivery @ 0.907983 escalate` → `track_order @ 0.507725 clarify`; `unseen36` `ugc-esc-02` (`[EMAIL_1]`): `submit_product_feedback` → `wrong_item` (safe `escalate`); `final24` `final-case-14`: `product_information @ 0.024234` → `request_refund @ 0.284153` (`raw_post` `escalate -> clarify`, Engine/Runner still `escalate`); `unseen36` `ugc-sup-06` (`TXN-99210` / `ORD-1001` masked): `payment_issue` confidence rises further `0.887994 -> 0.91394` (`retrieve_draft` on both). No new unsafe draft leaks were introduced by `pseudonymize`.

---

## 6. Output Artifact Inventory (`artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114/`)

| File | SHA-256 |
| --- | --- |
| `unseen_domain_gate_cases.jsonl` | `3e10b21b7d0e7651510c284143fe27d3ff9efab852e7821e22638286000c0447` |
| `unseen_domain_gate_manifest.json` | `3f2d36ebe4d2e9769e595f7ccebe69d24b2cf1be5a8a8bc0ca0a2c189045417e` |
| `evaluate_candidate.py` | `1ebe87ea1311a7cf2cc4c69c36a7da28dff6c836aa188b136853f18cc3e19e7e` |
| `predictions_orig_fit2.jsonl` | `f64563b3af3c5fe317824103136b7e7608dc765a75df627de94540b4544de305` |
| `predictions_cand_fit_v1.jsonl` | `810111278fb8405a0076e6b6019561b8fad73c7af967f154e788d7b1c22a4121` |
| `suites_comparison.json` | `f21418331512f443c6b6cd5d483a44bb23eb946becdd33f230dcfc7e7de13a54` |
| `gate_report_cand_fit_v1.json` | `2c38f2fb1dfda1ba679afbc1edf3a7a69cc42eb330b711c03fcb2ffa4d324072` |
| `run_manifest.json` | `db80c579da10f5dd25641c5d4d552c144c42f711aa8b366facdd0a668b72124e` |

---

## 7. Explicit Limitations

1. **Warm-start continuation confound:** `fit2-orig-ret-channel-fit-v1` warm-started from `reconstructed-fit2-supcon-20261113` and ran `3` additional epochs at `lr=2e-5` across `13,080` examples (`4,360/epoch`), so observed gains (`return_product_in_store`, `noise420`) and regressions (`ind36` `g2-esc-06/09`, `oos-other_domain-16`, `neg51` `023`, `bitext` `sample_040930`) cannot be causally isolated between the `18`-row extension vs extra optimization steps without a matched zero-delta continuation control.
2. **Offline LLM spies:** `Engine._analyse` and `PipelineRunner` ran with `_MockNoCallLLM` / `_OfflineValidSpyLLM` (`0` live LLM calls); end-to-end LLM generation quality/latency is untested here.
3. **Dataset caveats:** `fresh34` is historical regression only (`46-intent`/`v4p1` legacy labels); `bitext_test_6690` retains `3` inherited normalized-text overlaps with `bitext_train_noisy` (`sample_001360`, `sample_020916`, `sample_031234`), though excluding them leaves metrics and `2` leaks unchanged.
