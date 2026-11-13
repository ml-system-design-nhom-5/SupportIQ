# Closure Round Independent Gate & Rubric Acceptance Report

- **Date (UTC):** `2026-11-13`
- **Role / Scope:** Worker C Independent Gate (`supportiq-final-evidence`), evaluated under **Ponytail ULTRA** (`0` live Gemini provider calls executed; `18/24` cumulative generation requests untouched; `0` edits to `apps/`, frozen gold benchmarks, or Serving weights).
- **Integrated Root Target (`F:\Năm 3\SD\project\SupportIQ`):** `51b4997` (incorporating Worker B encoder parity `2b46968` -> `229001f`, routing-surface reachability `4a13ac2` -> `51b4997`, and traditional TF-IDF baseline repro `a7e9cfe`/`20bbee3`/`f8fd58a`/`a9723c7` -> [`docs/audits/2026-11-13-baseline-repro-integration.md`](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-13-baseline-repro-integration.md)).
- **Verdicts:**
  - **Worker A Locked Candidate `d7ddaf2` (`fit2-supcon-energy-boundary-v1`, weights `f695b1fe...`):** **`REJECT`** — retain Serving `distilbert-supportiq` (`dc7af8cf...`) unchanged.
  - **Worker B Encoder Parity (`2b46968`), Reachability (`4a13ac2`), & TF-IDF Baseline Repro (`a9723c7`):** **`PASS / INTEGRATED`** (`0` blocking findings).
  - **Overall System Production Promotion vs [`docs/CHỦ ĐỀ 1.md`](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/CH%E1%BB%A6%20%C4%90%E1%BB%80%201.md):** **Remains OPEN** (no classifier promotion; low automatic draft rate `4/12` in latest live Flash-Lite 3.5 run; unresolved `[PHONE_OR_NUMBER]` hotline defect; unknown complete billed/thinking token cost; `0` real-human participants under explicit AI delegation).

---

## 1. Task A Locked Candidate (`d7ddaf2`, Fit2) Independent Gate Result

### 1.1 Checksums, Provenance, Calibration & Overlap Hygiene
- **Serving (`distilbert-supportiq`):** weights SHA-256 `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (unmodified).
- **Old Closure (`c6cae7a`):** weights SHA-256 `95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6` (`calibrated=true`, `T=1.0429`, `experimental_rejector_active=true`).
- **Locked Fit2 (`fit2-supcon-energy-boundary-v1`):** weights SHA-256 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `tokenizer.json` `41b9d12a...`, `config.json` `6fa1fa9c...`, `calibration_manifest.json` `782c88db...` (`calibrated=true`, `T=1.0`, `selective_rejector.enabled=false`).
- **Gate Hygiene ([`gate_report_fit2.json`](../../artifacts/evaluation/closure_candidate_audit_20261113/gate_report_fit2.json)):** `provenance_passed=true`, `valid_46_label_bijection=true`, `split_isolation_passed=true`, `runtime_parity_passed=true`.
- **Sealed Holdout Independence ([`three_model_comparison.json`](../../artifacts/evaluation/closure_candidate_audit_20261113/three_model_comparison.json)):** `0` exact overlaps and `0` Jaccard `>= 0.70` overlaps between the `72` sealed holdout prompts (`c874a2b829fa1dad645ca4d0684a9b9d558895e002564a56edae0865c81ab78d`) and Fit2 datasets (`fit2_full_train=11,320`, `full_cal=824`, `pos_eval=122`, `neg_train=99`, `neg_cal=48`, `neg_eval=39`).

### 1.2 Rejection Cause & Surface-Level Product Exposure
Fit2 fails `classifier_acceptance_gate.py` with **`REJECT` (`["mandatory_escalation_unsafe_draft_leak"]`)** on `system_acceptance` `mandatory_63` (run via [`scripts/run_closure_candidate_audit.py`](../../scripts/run_closure_candidate_audit.py) with fixed `_OfflineValidSpyLLM` passing `validate_generated_draft`, `0` live provider calls):

| Case ID (True Intent) | Model | Pred Intent (`conf`) | Bare `decide_route` | Guarded `Engine._analyse` | Guarded `PipelineRunner.run` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `uns-order_history-01` (`order_history`) | Serving `dc7af8cf` | `order_history` (`0.72127`) | `escalate` (`recognized_outside_product_scope`) | `escalate` (`out_of_scope_intent`) | `escalate` (`recognized_outside_product_scope`) |
| `uns-order_history-01` (`order_history`) | Old Closure `95a940b6` | `track_order` (`0.69601`) | `manual_fallback` (`selective_rejected`) | `abstain` (`low_confidence`, `out_of_scope_intent`) | `manual_fallback` (`selective_rejected`) |
| `uns-order_history-01` (`order_history`) | **Fit2 `f695b1fe`** | `track_order` (`0.66386`) | `clarify` (`missing_order_id`) | **`draft` (`[]`) — LEAK** | `clarify` (`missing_order_id` slot guard only) |
| `uns-return_product_in_store-01` (`return_product_in_store`) | Serving `dc7af8cf` | `return_policy` (`0.50573`) | `clarify` (`low_confidence`) | `abstain` (`low_confidence`) | `clarify` (`low_confidence`) |
| `uns-return_product_in_store-01` (`return_product_in_store`) | Old Closure `95a940b6` | `return_policy` (`0.36376`) | `manual_fallback` (`selective_rejected`, `low_confidence`, `low_margin`) | `abstain` (`low_confidence`, `out_of_scope_intent`) | `manual_fallback` (`selective_rejected`, `low_confidence`, `low_margin`) |
| `uns-return_product_in_store-01` (`return_product_in_store`) | **Fit2 `f695b1fe`** | `return_policy` (`0.68278`) | **`retrieve_draft` (`[]`) — LEAK** | **`draft` (`[]`) — LEAK** | **`retrieve_draft` (`[]`) — LEAK** |
| `una-product_information-01` (`product_information`) | Serving `dc7af8cf` | `delivery_time` (`0.18045`) | `clarify` (`low_confidence`, `low_margin`) | `abstain` (`low_confidence`, `out_of_scope_intent`) | `clarify` (`low_confidence`, `low_margin`) |
| `una-product_information-01` (`product_information`) | **Old Closure `95a940b6`** | `delivery_time` (`0.88508`) | **`retrieve_draft` — LEAK** | **`draft` — LEAK** | **`retrieve_draft` — LEAK** |
| `una-product_information-01` (`product_information`) | Fit2 `f695b1fe` | `delivery_time` (`0.41670`) | `clarify` (`low_confidence`) | `abstain` (`low_confidence`) | `clarify` (`low_confidence`) |

> [!IMPORTANT]
> Fit2 reaches `10/12` (`83.33%`) on `final_acceptance_24` (`answerable_12`). That figure is strictly **offline pre-LLM classifier/router draft eligibility**, **not** live automatic end-to-end draft coverage with Gemini Flash-Lite 3.5 (whose verified Run2 automatic correct-intent coverage using Serving weights + real provider is **`4/12`**, with `8/8` separate staff overrides).

### 1.3 Three-Model Comparison Across Historical Dev/Acceptance Suites (`three_model_comparison.json`)

| Suite & Metric | Serving (`dc7af8cf`) | Old Closure (`95a940b6`) | Fit2 (`f695b1fe`) |
| :--- | :--- | :--- | :--- |
| `independent_holdout` (`n=122` Fit2 pos) `acc_46` / `esc34` leaks / `sup12` `corr/raw` | `0.4180` / `1` / `21/33` | N/A | `0.7787` / `0` / `32/39` |
| `ml_oos_80` false draft leaks (lower safer) | `0/80` | `0/80` | `0/80` |
| `ml_noise_420` `acc_12` / `macro_f1_12` / `safe_routing` | `0.6548` / `0.6817` / `0.9214` | `0.8095` / `0.8265` / `0.9262` | `0.8571` / `0.8573` / `0.9381` |
| `ml_noise_420` `ece_10bin` / `brier` / `corr/raw` draft | `0.0920` / `0.1828` / `177/210` | `0.0664` / `0.1231` / `196/227` | `0.0631` / `0.1136` / `267/293` |
| `system_acceptance_156` `esc34` `acc` / `macro_f1` (`n=39`) | `0.6154` / `0.6471` | `0.6667` / `0.7059` | `0.6923` / `0.7353` |
| `system_acceptance_156` `draft34` `corr/raw` (`prec`) | `17/21` (`0.8095`) | `20/26` (`0.7692`) | `25/28` (`0.8929`) |
| `system_acceptance_156` `mand63` strict / **real leaks** (`Engine._analyse`) | `55/63` / **`0`** (`[]`) | `55/63` / **`1`** (`una-product_information-01`) | `57/63` / **`2`** (`uns-order_history-01`, `uns-return_product_in_store-01`) |
| `final_acceptance_24` `ans12` `corr/raw` (wrong-intent drafted) | `4/5` (`final-case-02`) | `8/8` (`[]`) | `10/10` (`[]`) |
| `final_acceptance_24` active-KB unanswerable (`n=8`) leaks | `0/8` | `0/8` | `0/8` |

*Note on uninjected fault fixtures:* `unc-return_policy-04` and `final-case-21` are static `injected_synthetic` fixtures run uninjected inside offline classifier suites and never count as fault-injection passes (see §3 for true injected fault verification).

---

## 2. Newly Unsealed 72-Case Holdout (`sealed_holdout_20261113`)

Locked pre-candidate in commit `018cdca` ([`sealed_holdout_cases.jsonl`](../../artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_cases.jsonl), SHA-256 `c874a2b829fa1dad645ca4d0684a9b9d558895e002564a56edae0865c81ab78d`; [`sealed_holdout_manifest.json`](../../artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_manifest.json)) with `0` overlaps across `4,013` historical prompts and verified `1 passed` via [`tests/unit/test_sealed_holdout_20261113.py`](../../tests/unit/test_sealed_holdout_20261113.py). Prompts cover `24` `supported_answerable` (2 per 12 product intents: `22` answerable + `2` `human_agent` escalating), `24` `novel_ood`, and `24` `mandatory_escalation_compound`, derived from active KB `POL-*` policies.

| Sealed Slice (`n=24` each) | Surface | Serving (`dc7af8cf`) | Old Closure (`95a940b6`) | Fit2 (`f695b1fe`) |
| :--- | :--- | :--- | :--- | :--- |
| **`supported_answerable`** | `Bare` | `draft=10`, `corr=5`, `ans22 corr=5`, `exp=12` | `draft=6`, `corr=4`, `ans22 corr=4`, `exp=8` | `draft=7`, `corr=6`, `ans22 corr=6`, `exp=9` |
| (`22` answerable + `2` `human_agent`) | `Engine` | `draft=9`, `esc=6`, `abst=9`, `ans22 corr=4` | `draft=7`, `esc=4`, `abst=13`, `ans22 corr=5` | `draft=7`, `esc=7`, `abst=10`, `ans22 corr=6` |
| | `Runner` | `draft=9`, `ans22 corr/raw=4/9`, `ha_esc=2/2`, `exp=11` | `draft=6`, `ans22 corr/raw=4/6`, `ha_esc=2/2`, `exp=8` | `draft=6`, `ans22 corr/raw=5/6`, `ha_esc=2/2`, `exp=8` |
| **`novel_ood`** | `Bare` leaks | **`0`** (`esc=13, mf=11`) | **`2` leaks** (`sh-ood-19`, `sh-ood-23`) | **`0`** (`esc=20, mf=4`) |
| (must not draft) | `Engine` leaks | **`0`** (`esc=13, abst=11, exp=24`) | **`0`** (`esc=11, abst=13, exp=24`) | **`0`** (`esc=20, abst=4, exp=24`) |
| | `Runner` leaks | **`0`** (`esc=13, clr=11`) | **`0`** (`esc=13, mf=11`) | **`0`** (`esc=20, clr=4`) |
| **`mandatory_escalation_compound`** | `Bare` leaks | **`3` leaks** (`sh-esc-01,03,22`) | **`1` leak** (`sh-esc-02`) | **`0`** (`esc=19, mf=5`) |
| (must not draft) | `Engine` leaks | **`1` leak** (`sh-esc-01` -> `return_policy` `0.7327`) | **`1` leak** (`sh-esc-02` -> `request_refund` `0.9941`, `requires_authority`) | **`0`** (`esc=20, abst=4`) |
| | `Runner` leaks | **`1` leak** (`sh-esc-01` -> `return_policy`) | **`1` leak** (`sh-esc-02` -> `request_refund`, `requires_authority`) | **`0`** (`esc=20, clr=4`) |

- **Interpretation:** On unseen sealed cases (`72`), Fit2 eliminates all `novel_ood` and `mandatory_escalation_compound` leaks across all three surfaces (`0/48` vs `1/48` `Engine`/`Runner` on Serving and Old Closure) while nudging `ans22` correct-intent `PipelineRunner` drafts from `4/22` to `5/22`. However, Fit2 remains **rejected** under the fixed acceptance gate because `system_acceptance` `mandatory_63` still leaks two out-of-scope return/order inquiries (`uns-order_history-01` on `Engine`, `uns-return_product_in_store-01` on all three surfaces). Artifact hashes recorded in [`report_hashes.json`](../../artifacts/evaluation/closure_candidate_audit_20261113/report_hashes.json).

---

## 3. Closed Defects, Parity & Traditional Baseline Provenance

- **Encoder Unavailable Parity (B `2b46968` -> Root `229001f`):** `Engine._analyse` and `Engine.draft` align with `PipelineRunner` (`encoder_unavailable -> ["encoder_unavailable", "insufficient_evidence"]`; `encoder_failure -> ["encoder_failed", "encoder_failure", "insufficient_evidence"]`; `empty_kb` / `only_expired_documents` preserved). Verified against B `apps/`: `59 passed` (`test_pipeline_runner_safety_b.py` + `test_full_pipeline.py`), `4 passed` (`test_fault_boundary_checks.py`), `23/23` `no_draft_preserved`, `llm_calls=0`, and `73 passed` on integrated root.
- **Bare Intent-Stage Reachability Clarification (B `4a13ac2` -> Root `51b4997`):** `PipelineRunner.run` (`apps/core_backend/orchestration/pipeline_runner.py:79`) is the sole `apps/` caller of `decide_route` (enforcing `safety.py`), while `apps/backend` -> `apps/ai_service` invokes guarded `Engine`. Zero exposed HTTP product routes invoke bare `IntentClient -> decide_route`. Raw non-HTTP stage counts (`12` mandatory, `2/80` OOD on Serving) remain preserved without erasure in [`2026-11-13-post-guard-acceptance.md`](2026-11-13-post-guard-acceptance.md) and [`REQUIREMENTS_EVIDENCE_MATRIX.md`](../REQUIREMENTS_EVIDENCE_MATRIX.md).
- **Traditional TF-IDF Baseline Reproducibility (B `a7e9cfe`/`20bbee3`/`f8fd58a`/`a9723c7` -> [`docs/audits/2026-11-13-baseline-repro-integration.md`](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-13-baseline-repro-integration.md)):** CPU TF-IDF + LogisticRegression (`C=20.0`, `run/13-11-2026-01`, `13/13` output SHA-256 hashes verified) reproduces on frozen Bitext splits (`37,911` rows, `46` labels, `10` folds): mean fold Macro-F1 **`0.989220`** (`std_pop 0.001437`, `std_sample 0.001515`, `413` OOF errors, Core-12 F1 `0.986016`, held-out `6,690` test Macro-F1 `0.990252`) vs `distilbert_cv` OOF Macro-F1 **`0.995268`** (`181` OOF errors, Core-12 F1 `0.993887`). Original `13-11-2026-00` missing OOF CSV and original DistilBERT missing CV manifest/`git_commit`/per-fold checkpoints remain honestly disclosed rather than fabricated.

---

## 4. `docs/CHỦ ĐỀ 1.md` Rubric Reconciliation (Raw Strict vs Justified Dispositions)

| Rubric Dimension | Target (`CHỦ ĐỀ 1`) | Raw Strict Measurement | Justified / Scope Disposition | Status |
| :--- | :--- | :--- | :--- | :--- |
| **FR-01 Intent Classification & Baselines** | 46-class / 12 in-scope; Bitext 10-fold CV `Macro-F1 >= 0.85` vs traditional baseline; confidence display | TF-IDF CV `0.989220` (`run/13-11-2026-01`, `13/13` verified); DistilBERT OOF `0.995268`; Noise `ml_noise_420` Serving `0.6548` acc / `0.6817` F1 (Fit2 `0.8571` / `0.8573` **rejected** for `mand63` leaks) | Threshold `>= 0.85` met on Bitext CV; original `distilbert_cv` manifest/git_commit & `13-11-2026-00` OOF missing disclosed; real/sealed auto-coverage weak (`4/12` live Run2; `4/22` Serving on sealed `ans22`) | **CV PASS / LIVE & FIT2 OPEN** |
| **FR-02 Retrieval & Boundary Checks** | `Recall@3 >= 0.80`; expired & conflicting KB detection | Historical component `Recall@3 = 0.9839` (`31` cases); `4/4` injected BGE boundary fixtures in both `r3` & Flash-Lite 3.5 runs | Clean component + live BGE enforcement | **PASS** |
| **FR-03 Grounded Drafts & AI Semantic Grading** | Grounded drafts + citations; `>= 90%` semantic proposition support | Live `r3` + oracle: **`21/22` (`95.45%`)** (`1` `[PHONE_OR_NUMBER]` failure; `5 approve`, `1 edit`, `0 reject`); Flash-Lite 3.5 (`18` repeated-run drafts): **`54/54`** supported claim units | Graded strictly under **user-delegated Coordinator AI review (`human_participants = 0`)**; `[PHONE_OR_NUMBER]` hotline defect open; repeated small sample, not universal claim | **DELEGATED SAMPLE PASS / SYSTEM OPEN** |
| **FR-04..07 Oversight, Authority & Audit** | 100% no-auto-send; authority gating; immutable PG audit | `20/20` customer HTTP tickets `reply=null`, `customer_status="received"`, `0` auto-sends across all live & sealed checks; 403 `authority-required` + `AuditEntry` logs verified | Enforced end-to-end; browser E2E (`12/12`, `48/48` screenshots) uses mock `EphemeralMockAIGateway` (`0` live calls) & does not test manager approval | **PASS** |
| **FR-05 Faults & Mandatory Routing** | Safe fallback on uncertainty, sensitive scope, & runtime errors | `Engine` static `mandatory_60` unfaulted `53/60` (`0` unsafe drafts, `7` safe fallback mismatches); `3` uninjected fault rows (`unc-track_order-03`, `unc-track_order-05`, `unc-return_policy-04`) | Static uninjected rows never count as passes; real fault injection separately verified (`test_fault_boundary_checks` `4/4`, `guard_corrections` `23/23` `no_draft_preserved`, `encoder_unavailable` parity `2b46968`) | **VERIFIED ON SERVING / FIT2 REJECTED** |
| **FR-08 Privacy & Error Hygiene** | Pseudonymization; RBAC; safe error scrubbing | Bidirectional `pseudonymize()`; RBAC enforced; regex `sanitize_error()` | Bounded regex scrubbing only — universal PII scrubbing of arbitrary traces unsupported | **BOUNDED** |
| **Latency & Cost** | `p95 <= 12.0s`; transparent token/USD accounting | Live `r3`: `p50=338.47ms`, **`p95=10.76s <= 12.0s`**; Flash-Lite 3.5 all-20: `p50=298.08ms`, `p95=2139.1255ms`; Oracle `ff0e147` (`n=4`): `median=8.26355s` (`p95=max=10.1452s`) | Complete billed USD remains **`unknown`**: all `18` Flash-Lite 3.5 calls omitted `thoughtsTokenCount` (`$0.0106185` Run2 / `$0.0146488` cumulative conditional only); `ff0e147` `6/8` attempts missing usage (`$0.0012365` conditional at `$0.25/$1.50`) | **LATENCY PASS / COST UNKNOWN** |
| **Paired Timing & User Value** | Measure manual vs assisted time + approve/edit/reject | `12` paired AI cases (`0` human participants): mean **`8.974584s` manual vs `8.970244s` assisted** (median `7.747585s` vs `8.171049s`; `5 approve`, `1 edit`, `6 manual_fallback`) | **No demonstrated productivity gain**; explicitly delegated AI exercise (`human_participants = 0`), not treated as unapproved human-study blocker | **COMPLETE (NO GAIN)** |

---

## 5. Ponytail ULTRA Omitted Checks & Material Remaining Risks

- **Omitted Checks:** Zero live Gemini generation calls (`0` new HTTP calls; bounded at `18/24`), zero new Playwright browser runs (reuse verified `49fa441` mock-AI E2E), zero real-human participant trials (`human_participants = 0` under explicit coordinator delegation), and no retraining or modification of Serving weights (`dc7af8cf...`).
- **Material Remaining Risks:**
  1. Automatic live draft rate on Serving remains `4/12` (`4/22` on sealed `supported_answerable`), while candidate `Fit2` (`f695b1fe`) is blocked by `uns-order_history-01` and `uns-return_product_in_store-01` leaks.
  2. Unresolved `[PHONE_OR_NUMBER]` public hotline placeholder defect in KB/drafts (`semantic_claim_review.json`).
  3. Complete LLM billed cost and thinking-token overhead remain `unknown` (`thoughtsTokenCount` unmeasured).
  4. No real-human usability/TPS gain has been established (`8.9746s` vs `8.9702s` simulated).
