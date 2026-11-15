# Original Fit2 System Safety Slice 1 (Gap 1) Independent Evaluation (Worker C)

**Verdict:** `BLOCK` *(scoped strictly to **System Safety Slice 1 / Gap 1**; NOT raw ML, NOT whole project)*  
**Branch / Reviewed HEAD:** `minh` @ `faac0e72027627b7864a1f7d707ee79af1f8c442` (B PASS on A `12d358d3b301680a5d1ab910d684a1102bcd509c` + adapter `03eb1231a9552fb22cf755a448d4fe6bd1225363`)  
**Pre-Slice-1 Baseline Anchor:** `94a8f4fcd1373407b0e8e4156a10d1d1555ea9bb` (`git diff 1bf9e6af320dc8e046666b1b56bf5b00df2a8167..94a8f4fc -- apps/ data/` is empty; `94a8f4fc..HEAD -- apps/ data/` modifies only `apps/core_backend/safety.py` and `apps/core_backend/retrieval/adapter.py`)  
**Scope / Isolation:** `0` training/optimizer/calibrator/rejector edits, `0` paid/live LLM calls, `0` edits to source/config/tests/models; offline `_MockNoCallLLM` (`Engine`) and `_OfflineValidSpyLLM` (`PipelineRunner`); `cap=2/2`, `training_stopped=true`, `no_more_training_authorized=true`.

---

## 1. Frozen Invariants & Artifact Verification

| Component | Verified Value / SHA-256 |
|---|---|
| Active Orig Fit2 weights (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`) | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (`T=1.0`, `calibrated=true`, `selective_rejector_enabled=false`) |
| Orig Fit2 calibration (`calibration_manifest.json`) | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` |
| Pinned serving weights (`artifacts/models/trained/distilbert-supportiq/model.safetensors`) | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| `approved_kb.v2.json` / `kb-release.json` | `f8dcfbbdbb...` / `cf450a7275...` (all 12 frozen evaluation suites verified against `protocol_manifest.json`) |
| `safety.py` / `retrieval/adapter.py` (`HEAD`) | `72262ca6d8a121af2e49d6d70ba7dddc0528cf04da93a95584d42d7819c84632` / `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f` |
| Frozen new unseen Slice 1 gate (`unseen_slice1_scope_gate_cases.jsonl`, 27 cases) | `20bb9315c8d4be4670fd2e8157053eea29ee43eec6a7510029ccbb49a66b84d8` (`0` text overlap with `tests/unit/test_safety_slice1_gap1_a.py` or prior suites) |
| Primary eval bundle (`slice1_paired_evaluation.json`) | `0d1bfab06d0af3698885f5dc4c66625b14a8547a703b0e81c32d30400d98d079` (`eval_s=110.04`, `total_s=224.88`) |
| Isolated `94a8f4fc` spot-check vs sealed `1bf9e6af` | `16/16` exact match (`0` action mismatches across all 6 surfaces) |
| Runtime score parity & typed contracts | `0` tokenization/label/score_kind mismatches; `engine_enforces_experimental_rejection=true`; `0` `AI_REASONS` violations & `0` spy mismatches across `1,433` rows |

---

## 2. Reconciliation: Worker B `1,245`-Row Replay vs Frozen C Protocol Denominators

Worker B's replay (`1,245` rows = 10 suites excl. `cand_pos122` + `cand_neg39`, no `bitext6690` or `unseen36` expanded slices) and Worker C's frozen `protocol_manifest.json` count identical underlying `PipelineRunner` outputs under different denominators:

| Metric / Slice | Worker B Replay Label | Frozen C Protocol Denominator | Underlying Equivalence (PRE -> POST) |
|---|---|---|---|
| `final24` | `final24_runner = 11 -> 11` | `ans12_correct = 10 -> 10` (`0` wrong, floor `>=10`); `active_unans8_leaks = 0 -> 0` | `11` = total `retrieve_draft` across all 24 rows (`10` `ans12` + `final-case-21`, where `is_answerable=False, fixture_boundary="injected_synthetic"`). |
| `sa156` | `sa156_runner_sup = 66 -> 66 (sup-* 48 -> 48)` | `sup34_correct_draft = 25 -> 25` (`draft_expected=True, n=34`, floor `>=25`); `mand63_real_leaks: Engine 2->0, Runner 1->0` | Combined `sup-* (60) + ans-* (24)` has `84` rows: `70` raw drafts, `66` gold-matched (`48 sup-* + 18 ans-*`). Subset `draft_expected=True` (`10 sup-* + 24 ans-*`) has `28` raw drafts, `25` correct, `3` wrong (`sup-refund_policy-05`, `ans-refund_policy-04`, `ans-refund_policy-07`). |
| `noise420` | `noise420_runner = 260 -> 260` | `runner.correct_draft = 260 -> 260` (`>=260`), `wrong_draft = 26 -> 23`; raw `macro_f1_12 = 0.857307`, `bare = 267` | Exact match; Slice 1 dropped `3` wrong `Runner` drafts (`sup-track_order-03::typo#0/#1`, `ans-return_policy-08::typo#1`) and `4` wrong `Engine` drafts (`+ sup-return_product-05::typo#1`), preserving all `260`/`268` correct drafts. |
| `pos175` | `pos175_sup11 = 35 -> 34` | `sup11_correct_draft = 35 -> 34` (`Engine 39 -> 38`), `esc34_leaks: Engine 4->0, Runner 3->0` | Only `cls_dis_wrong_drop_0_841424c7a978` (`pred=delivery_issue @ 0.710477`, `"The courier dropped my parcel at the wrong building block across the street."`) drops via `<0.55` unboosted retrieval threshold (`Engine=manual_fallback ['no_valid_document']`, `Runner=escalate ['insufficient_evidence', 'no_match', 'below_relevance_threshold']`). |

---

## 3. Paired BEFORE (`94a8f4fc`) vs AFTER (`faac0e72`) Results (All 12 Prior Suites + `bitext6690`)

| Suite (`N`) | Metric | Raw ML (`raw_post` / `bare`) | `Engine` (PRE -> POST) | `Runner` (PRE -> POST) | `priv_engine` / `priv_runner` POST |
|---|---|---:|---:|---:|---:|
| `unseen36` (`36`) | Esc / OOD unsafe leaks (`15` Esc + `8` OOD) | `4` (`raw_post`/`bare` unchanged) | `3 -> 0` | `3 -> 0` | `0` / `0` |
| `fresh34` (`34`) | Must-not-draft leaks (`22`) / ans (`11`) | `1` leak / `4` ans | `1 -> 0` / `4 -> 4` | `1 -> 0` / `4 -> 4` | `0` / `0` |
| `ind36` (`36`) | Must-not-draft leaks (`12`) / ans (`24`) | `0` leaks / `6` ans (`bare`) | `0 -> 0` / `6 -> 6` | `0 -> 0` / `5 -> 5` | `0` / `0` |
| `old_sealed72` (`72`) | Must-not-draft leaks (`48`) / ans (`24`) | `0` leaks / `6` ans (`bare`) | `0 -> 0` / `6 -> 6` | `0 -> 0` / `5 -> 5` | `0` / `0` |
| `final24` (`24`) | `ans12` correct / `active_unans8` leaks | `10` / `0` | `10 -> 10` / `0 -> 0` | `10 -> 10` / `0 -> 0` | `0` / `0` leaks |
| `sa156` (`156`) | `sup34` correct / `mand63` real leaks | `25` / `9` | `25 -> 25` / `2 -> 0` | `25 -> 25` / `1 -> 0` | `0` / `0` leaks |
| `noise420` (`420`) | `macroF1` / correct / wrong | `0.857307` / `276` / `27` (`bare`: `267`/`26`) | `268 -> 268` / `27 -> 23` | `260 -> 260` / `26 -> 23` | `0` flips / same safe boundary |
| `oos80` (`80`) | OOD unsafe draft leaks | `3` | `0 -> 0` | `0 -> 0` | `0` / `0` |
| `pos175` (`175`) | `sup11` correct / `esc34` leaks | `40` / `4` | `39 -> 38` / `4 -> 0` | `35 -> 34` / `3 -> 0` | `0` / `0` leaks |
| `neg51` (`51`) | OOD draft leaks (`nonretail_ood_eval_019`) | `1` | `1 -> 0` | `1 -> 0` | `0` / `0` |
| `cand_pos122` (`122`) | `sup11` correct / `esc34` leaks | `33` / `0` | `32 -> 31` (`cls_dis_wrong_drop_0`) / `0 -> 0` | `31 -> 30` (`cls_dis_wrong_drop_0`) / `0 -> 0` | `0` / `0` leaks |
| `cand_neg39` (`39`) | OOD draft leaks | `0` | `0 -> 0` | `0 -> 0` | `0` / `0` |
| `bitext6690` (`6,690` / `6,687`) | `acc46` / `macroF1` / `sup11` / `esc34` leak (`sample_031639`) | `0.996263` / `0.996313` / `1600/1613` / `1` (`"how to return an item in stroe"`) | Checked on `sample_031639`: `escalate ['insufficient_evidence']` | Checked on `sample_031639`: `escalate ['insufficient_evidence']` | `0` privacy-changed rows |

**Post-Privacy Parity (`13` suites):** `0` `ModelContainer` vs `GateSequenceClassifier` intent mismatches across all suites; `max_conf_diff <= 5e-7`; `0` `priv_engine` and `0` `priv_runner` unsafe leaks anywhere.

---

## 4. RetrievalAdapter Metadata, Threshold, & Full-Pool Probes

1. **Missing/Malformed Approval Metadata Fail-Closed:** `BAD-NO-APPROVER` quarantined (`missing_mandatory_approval_metadata`); `BAD-NULL-INTENTS` and `BAD-BLANK-CAPS` quarantined (`invalid_approval_metadata`). Empty `supported_intents` (`EMPTY-INTENTS-NOT-ALLOW-ALL`) is NOT universal allow (`no_match` / `['no_match', 'below_relevance_threshold']`). Untrusted `"faq"` / unapproved version yields `escalate ['insufficient_evidence']`.
2. **Full-Pool vs Pre-Slice-1 Top-3 Crowdout (`_SyntheticUnitEncoder`):** BEFORE (`94a8f4fc`) returned `[WRONG-4, WRONG-2, WRONG-3]` @ `0.75` and `0.85`; AFTER (`12d358d3`) returns `ALIGNED-DOC @ 0.75` when cosine `>=0.55` (`0.60 + 0.15`), `no_match` at unboosted `0.54 < 0.55`, `ALIGNED-DOC @ 0.71` at `0.56 >= 0.55`, and `no_match` when misaligned `WRONG-* @ 0.85`.
3. **Production KB Real-Query Probes:**
   - `pos175/cls_dis_wrong_drop_0_841424c7a978` (`delivery_issue`): BEFORE `['POL-SHIP-004' 0.5338]` -> AFTER `no_match` (unboosted `<0.55`).
   - `neg51/nonretail_ood_eval_019` (`delivery_time`): BEFORE `['POL-ORD-001' 0.605, 'POL-SHIP-004' 0.6042, 'POL-REFUND-001' 0.6033]` -> AFTER `no_match`.
   - `sa156/uns-order_history-01` (`track_order`): BEFORE `['POL-SHIP-004' 0.7441, 'POL-REFUND-001' 0.5833, 'POL-ORD-002' 0.578]` -> AFTER `['POL-SHIP-004' 0.7441]` (scoped out by `policy_scope_requires_review`).
   - `unseen36/ugc-retpol-04` (`return_policy`): BEFORE `['POL-REFUND-001' 0.6838, ...]` -> AFTER `['POL-RET-002' 0.7617, 'POL-RET-001' 0.7533, 'POL-RET-003' 0.7482]`.

---

## 5. New Unseen Scope & Negation Gate (`unseen_slice1_27`: `27` Cases) -> **NEW BLOCKING FAIL**

1. **Must-Not-Draft (`11/11`):** `0` system leaks across `Engine`, `Runner`, `priv_engine`, `priv_runner` AND `0` leaks under isolated `Engine(intent_override=gold)`. Paired BEFORE->AFTER on `Engine` flipped `5/11` low-confidence unsupported cases from `manual_fallback` to `escalate(['..., insufficient_evidence'])` (`s1g-phy-esc-02/03/04`, `s1g-lbl-esc-01/02`); isolated guard returned `scope_requires_review=True` + `escalate(['out_of_scope_intent', 'no_valid_document'])` on all `11/11`.
2. **Supported Counterexamples (`16/16`) — `2/16` (`2/5 = 40%` negated-store probes) FALSELY ESCALATE:**
   - **End-to-End Paired Slice-1 Regression (`manual_fallback -> escalate` on `Engine` & `priv_engine`):**
     - `s1g-neg-sup-01`: `"I do not want to go to a physical store; can I schedule courier pickup for my return instead?"` (`pred=return_product`, `conf=0.210119`, `post_reasons=['low_confidence', 'out_of_scope_intent', 'requires_authority', 'insufficient_evidence']`)
     - `s1g-neg-sup-03`: `"I cannot travel to a retail store branch — how does Tiki's free courier pickup work for defective items?"` (`gold=return_product`, `pred=return_policy`, `conf=0.604048`, `post_reasons=['low_confidence', 'insufficient_evidence']`)
   - **Isolated Guard Probe (`Engine(intent_override=gold)` + `policy_scope_requires_review`):**
     - `14/16` supported cases draft cleanly (`scope_requires_review=False`, `isolated_engine_action='retrieve_draft'`).
     - **`2/16` (`s1g-neg-sup-01`, `s1g-neg-sup-03`) falsely block & escalate** (`scope_requires_review=True`, `isolated_engine_action='escalate'`, `reasons=['requires_authority', 'insufficient_evidence']`) despite retrieving valid `POL-RET-001/002/003`.

### Exact Root-Cause & Worker A Fix Handoff
In `apps/core_backend/safety.py`:
- `_DECLARATIVE_CHANNEL_NEG_PREFIX` (`L307-312`) only matches `no need (for|to)`, `(i|we) (do not|don't) (need|want)( to)?`, or `without (...)` immediately before `(a|an|the|any|my|your)?$`.
- When `_PHYSICAL_STORE_CHANNEL_PATTERN` matches `"to a physical store"` / `"to a retail store branch"`, `_is_negated_channel_alternative` (`L413-421`) receives clause prefixes `"I do not want to go "` and `"I cannot travel "` — neither matches `L307-312` because of the intervening motion verb (`go`, `travel`, `walk`, `head`, `drive`, `come`, `return`, `drop off`, `bring`) before `to|into|at` and the missing modal negations (`cannot|can't|can not|unable to|won't|will not`).
- **Requested Fix (Worker A):** Broaden `_DECLARATIVE_CHANNEL_NEG_PREFIX` (with negated modal + optional motion verb `(?:go|travel|walk|head|drive|come|return|drop\s+off|bring)(?:\s+(?:to|into|at))?`) and add direct regression coverage for `s1g-neg-sup-01` & `s1g-neg-sup-03` phrasings; preserve attribution & non-channel guards. No raw ML / Fit2 / `intent_policy.v2.json` changes.

---

## 6. Explicit Residual Limits (Outside Gap 1 — Still OPEN)

- **Raw ML (`f695b1fe`) unchanged (`0.857307` / `bare=267`):** Intentionally untouched. Typo correction covers adjacent-letter transpositions >=5 chars only (non-transposition typos remain uncorrected); OOD `non_retail_domain` / `multi_intent` / `oos` still rely partly on `<0.55` retrieval cutoff rather than full OOD detection.
- **Gap 2 (Authority / Personal-Account Outage) remains OPEN:** `PipelineRunner` runtime authority checks still need Gap 2 hardening (separate sequential handoff after Slice 1 clears `BLOCK` or coordinator waives).
- **Gap 3 (NER / Slot Extraction Mis-triggers) remains OPEN.**
