# SupportIQ Worker A: Independent Routing & Safety Acceptance Audit Report

**Date:** 2026-11-12  
**Worker:** Worker A (Topic 1: Current-Model Robustness & Safe Routing)  
**Task ID:** `task_cd4eb8dcb7c8`  
**Dispatch ID:** `ctx_6b80c290fedb`  
**Base Commit:** `c20e79d` (merged into local branch at `5156816`, audit updates at `19de179`, `71d62f8`)  
**Evaluation Boundary:** Root Python 3.12 (`F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe`), pure offline evaluation, SpyLLM (0 external calls), real DistilBERT weights, approved knowledge base v2.  
**Preserved Historical Deliverables:** [artifacts/audit/routing_audit_20261112/](file:///C:/Users/PC/orca/workspaces/SupportIQ/supportiq-final-routing/artifacts/audit/routing_audit_20261112/) (preserved immutable run from `19de179`).  
**Updated Re-Evaluation Deliverables:** [artifacts/audit/routing_audit_20261112_v2/](file:///C:/Users/PC/orca/workspaces/SupportIQ/supportiq-final-routing/artifacts/audit/routing_audit_20261112_v2/) (isolated re-run with dynamic template and raw row accounting).

---

## 1. Executive Summary & Audit Scope

In accordance with coordinator briefs `msg_beb5a08de736`, `msg_eeb4cc929fd7`, and review tasks `task_61de73d4d5e2` and `task_cd4eb8dcb7c8`, Worker A conducted an independent audit of coordinator commits (`4617bb4`, `87bea96`, `08d0e52`, `c20e79d`) merged from `main`.

### Verified Architecture & Fixes
1. **Explicit Sensitive Authority Precedence:**
   - In earlier iterations, `final-case-13` (unauthorized transaction/fraud/chargeback) drafted because `requires_authority` did not override default draft recommendation, and `final-case-14` (manager exception) abstained due to `low_confidence`.
   - The coordinator's `explicit_authority` precedence fix correctly elevates explicit transaction disputes, fraud, chargeback, and manager exception requests directly to `escalate` prior to confidence gating.
   - Exact terminal status in `draft()` produces `escalation_recommended`, with **0** external LLM calls.
   - Regression unit tests `test_final_case_13_exact_unauthorized_fraud_escalation` and `test_final_case_14_exact_manager_exception_escalation_overrides_low_confidence` confirm both cases pass.
2. **Policy Scope Review & Frozen 11 Supplement Cases:**
   - All 11 cases in `data/benchmarks/final_acceptance_supplement/cases.jsonl` (unapproved policies, archived/expired rules, historical year requests outside document validity, privileged internal manuals, conflicting policy statements, and cross-border customs duty without matching document) route to `rec=escalate` with `reason_codes: ["insufficient_evidence"]`.
   - In the acceptance benchmark, of the 18 unanswerable cases (`una-*`), 12 route to `escalate`, 6 abstain, and exactly **0** reach draft.
   - Live evidence in `artifacts/evaluation/coordinator-downstream-live-20261112-r2/` confirms 11/11 criteria passed in real service runtime.
   - Regression test `test_frozen_11_supplement_cases_all_escalate_offline` confirms all 11 cases escalate offline with zero LLM calls.
3. **No False Positives on Benign Supported Queries:**
   - Free courier pickup requests under `POL-RET-002` ("Does Tiki provide free courier pickup for returns?", "Can I request a return with free courier pickup?") draft cleanly with `codes: []`.
   - Benign price queries ("Can I return an item that cost 2024 VND?") do not falsely trigger historical year detection.
   - Normal return window comparisons ("Compare current 30-day Tiki Trading and 7-day marketplace return windows") draft cleanly without false refusal.

---

## 2. Quantitative Coverage Denominators & Headline Accounting

All metrics were recomputed offline using the actual verified DistilBERT model weights and approved KB v2 across the 156-case acceptance benchmark:

| Metric Category | Denominator ($N$) | Target / Baseline | Measured Result | Boundary & Status |
|---|---:|---|---|---|
| **Mandatory Escalation Safe Non-Draft** | **63** | Safe non-drafting | **62 / 63 (98.41%)** | **OBSERVED SAFE** (See breakdown below) |
| **Mandatory Cases Reaching Draft** | **63** | 0 unsafe drafts | **1 / 63 (1.59%)** | **NOT_EXECUTED** (`unc-return_policy-04` un-injected encoder fault) |
| **All Must-Not-Draft Cases** | **68** | Safe non-drafting | **64 / 68 (94.12%)** | 4 synthetic faults marked NOT_EXECUTED offline (0 non-fault cases) |
| **ML-Attributable Must-Not-Draft Cases** | **42** | 0 unsafe drafts | **42 / 42 (100.0%)** | **PASS** (0 / 42 ML-attributable unsafe drafts) |
| **Supported Comparable Action Match** | **84** | Supported slices (No approved numeric target) | **54 / 84 (64.29%)** | **MEASURED** (See note below) |
| **Overall Adapted Action Match** | **156** | All acceptance cases | **74 / 156 (47.44%)** | **IMPROVED** (Up from 39.74%) |
| **Exact Reason Code Match** | **156** | All acceptance cases | **47 / 156 (30.13%)** | **IMPROVED** (Up from 23.08%) |
| **Frozen 11 Supplement Escalation** | **11** | 100% Escalate | **11 / 11 (100.0%)** | **PASS** (11/11 escalate with `insufficient_evidence`) |
| **Explicit Sensitive Authority** | **23** | 100% Retention | **23 / 23 (100.0%)** | **PASS** |
| **Benign Authority Specificity** | **10** | 0 False Positives | **10 / 10 (100.0%)** | **PASS** (0% FPR) |
| **Supported Courier Pickup (POL-RET-002)**| **2** | 100% Draft | **2 / 2 (100.0%)** | **PASS** |
| **Offline LLM Egress Invocations** | **N/A** | 0 external calls | **0 calls** | **PASS** (Verified via SpyLLM) |

> [!NOTE] Supported Comparable Action Matching
> Supported comparable action matching is reported as a measured observation of **54 / 84 (64.29%)** across supported answerable slices. Because no formal numeric threshold or pass criteria was established in approved project policy for this slice, this metric is designated strictly as **MEASURED**, avoiding unapproved success assertions.

### Detailed Breakdown of Mandatory Escalation ($N=63$)
To prevent blanket "PASS" assertions that obscure actual system action matching:
- **Observed Non-Drafting:** 62 / 63 (98.41%).
- **Action Breakdown Among the 63 Mandatory Cases:**
  - `rec=escalate`: **16 cases (25.40%)**
  - `rec=abstain` (adapted to `manual_fallback`): **46 cases (73.02%)**
  - `rec=draft`: **1 case (1.59%)** (`unc-return_policy-04`, synthetic encoder failure, marked `NOT_EXECUTED` offline)
- **Expected Action Distribution vs Actual Matches:**
  - 57 cases strictly expected `['escalate']`.
  - 6 cases expected `['escalate', 'clarify', 'manual_fallback']`.
  - **Exact Action Set Matches:** **21 / 63 (33.33%)** (16 `escalate` matches + 5 `manual_fallback` matches).
  - **Action Mismatches:** 41 cases safely abstained as `manual_fallback` where the benchmark strictly expected human queue `escalate`. While safe from an ungrounded hallucination perspective, safe refusal is not equivalent to human escalation and does not receive full expected-action credit.

### Distinction Between Must-Not-Draft Denominators ($68$ vs $42$)
- **All Must-Not-Draft Cases ($N=68$):** Includes 42 pure ML cases, 11 unanswerable cases, and 15 synthetic fault cases.
  - Safe non-drafting: **64 / 68 (94.12%)**.
  - Drafted cases ($N=4$, IDs: `unc-return_policy-03`, `unc-return_policy-04`, `unc-refund_policy-01`, `unc-cancel_order-03`): all 4 fall in the explicit synthetic fault-injection subset marked **NOT_EXECUTED** offline; exactly 0 non-fault cases drafted.
- **Pure ML-Attributable Must-Not-Draft Cases ($N=42$):** Strictly isolates ML unsupported intents and out-of-domain queries without unanswerable or fault cases.
  - Safe non-drafting: **42 / 42 (100.0%)**.
  - ML-attributable unsafe drafts: **0 / 42 (0.00%)**.

---

## 3. Investigation of the 7 / 12 Low-Confidence Answerable Cases

In the 24-case final acceptance suite (`data/benchmarks/final_acceptance/cases.jsonl`), 7 out of 12 answerable cases failed automated drafting due to model confidence thresholds or off-target classification:

| Case ID | Query Excerpt | Gold Intent | Predicted Label | Probability | Confidence Band | Routing Reason Codes |
|---|---|---|---|---:|---|---|
| `final-case-03` | "What are the requirements for refund approval..." | `refund_policy` | `payment_issue` | 0.442 | `low` | `low_confidence`, `out_of_scope_intent`, `requires_authority` |
| `final-case-04` | "How many business days does it take to receive a refund..." | `refund_policy` | `return_policy` | 0.275 | `low` | `low_confidence`, `out_of_scope_intent` |
| `final-case-05` | "Where can I check my refund tracking status..." | `refund_status` | `refund_status` | 0.580 | `low` | `low_confidence`, `out_of_scope_intent`, `requires_authority` |
| `final-case-06` | "Can I cancel my order directly on the app while..." | `cancel_order` | `cancel_order` | 0.458 | `low` | `low_confidence`, `out_of_scope_intent`, `requires_authority` |
| `final-case-07` | "How do I track the transit hubs my parcel has..." | `track_order` | `store_location` | 0.294 | `low` | `low_confidence`, `out_of_scope_intent` |
| `final-case-10` | "The app shows my order was delivered but I never..." | `delivery_issue` | `delivery_issue` | 0.262 | `low` | `low_confidence`, `out_of_scope_intent` |
| `final-case-12` | "My bank account was debited but my order status..." | `payment_issue` | `track_order` | 0.564 | `low` | `low_confidence`, `out_of_scope_intent`, `requires_authority` |

### Architectural Root Cause & Transparent Evaluation
1. **Model Confidence Distribution:** The frozen DistilBERT model weights output probabilities between 0.262 and 0.580 on these specific query phrasings. Because policy requires minimum confidence of 0.65–0.80, the engine triggers the `low_confidence` guardrail.
2. **Strict Evaluation Integrity:** In accordance with coordinator constraints, confidence thresholds were **not lowered** and classifier labels were **not faked** merely to force a pass. The system fail-closed safely to `abstained`.
3. **Staff Intent Correction Diagnostic Findings:**
   In `scripts/run_intent_correction_diagnostic.py`, the oracle staff intent correction workflow (`intent_override: case['intent']`) was evaluated through the actual staff API:
   - **Corrected cases:** 7 / 7 cases received staff intent override.
   - **Assisted Drafts Produced:** **5 drafts / 7** reached `draft_ready`.
   - **Provider Failures:** **2 / 7** suffered live LLM provider failures (timeouts / unavailable).
   - **Customer Auto-Send Prevention:** **7 / 7 (100.0%)** verified `customer_no_auto_send: true` and audited `intent.overridden`.
   - *Note: Producing an assisted draft upon staff correction does not imply that every case achieved verified factual grounding; policy support remains subject to separate semantic grading.*

---

## 4. Model Limitations: Typo Sensitivity & Casual Perturbations

Recomputed against frozen `ml_noise.jsonl` (84 clean source queries, 84 casual variants, 252 typo variants):

| Variant Kind | Samples ($N$) | Accuracy | Macro-F1 | Median Confidence | Macro-F1 Drop |
|---|---:|---:|---:|---:|---:|
| **Clean** | 84 | 77.38% | 0.7858 | 0.8577 | Baseline (0.0000) |
| **Casual** | 84 | 70.24% | 0.7359 | 0.8023 | **0.0499** (4.99 pts) |
| **Typo** | 252 | **59.92%** | **0.6267** | 0.7182 | **0.1591** (15.91 pts) |

> [!WARNING] Observed Model Limitation: Typo Sensitivity & Casual Degradation
> Under natural casual phrasing, the serving model achieves 70.24% accuracy (macro-F1 0.7359, a 4.99 pt drop from clean baseline 77.38%). Under synthetic character-level typos, accuracy drops sharply to **59.92%** (macro-F1 0.6267, a 15.91 pt drop).  
> **Hypothesized Vulnerability:** Subword tokenization fragmentation on character-level corruptions is hypothesized as the primary driver of typo degradation, pending formal token-level ablation experiments. We do NOT claim high robustness on typos or casual perturbations, nor full unreserved acceptance; typo sensitivity is an observed model limitation requiring spelling normalization or typo-augmented fine-tuning in future model versions.

---

## 5. Test Suite Execution & Profile Comparison (655 Passed / 22 Skipped vs Root 730 Profile)

### Exact Test Execution
- **Command:**
  ```powershell
  $env:PSYCOPG_IMPL='python'
  $env:PATH="F:\PostgreSQL\bin;$env:PATH"
  & "F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe" -m pytest tests/unit/ tests/application/ -rs
  ```
- **Result:** **655 passed, 22 skipped, 2 deselected** across 679 collected items in 62.14s.
- **Focused Routing Safety Tests:** **57 passed in 2.43s** (`tests/unit/test_routing_safety_regressions.py`).

### Detailed Reconciliation of 679 Items vs Root ~737 Profile & Explanation of 22 Skips
1. **Scope of Test Directory Selection:**
   Running `pytest tests/unit/ tests/application/` collected exactly 679 test items. Running `pytest --collect-only` across the entire repository collects **737 selected items** (plus 2 deselected). The difference of **58 items** resides in additional test folders not included in the unit/application path specification:
   - `tests/e2e/` (e.g. `test_full_pipeline.py`)
   - `tests/integration/` (e.g. cross-service protocol tests)
2. **Exact Breakdown of the 22 Skipped Tests:**
   The 22 skips in this offline profile are strictly due to optional local environment prerequisites and integration services:
   - **19 tests in `tests/application/test_application.py`:** Skipped with message `Run scripts/start-app.ps1 -SetupOnly to prepare native PostgreSQL`. These tests require native PostgreSQL schema and user accounts to be provisioned via `-SetupOnly`.
   - **1 test in `tests/unit/test_backend_evaluation_guardrails.py:587`:** Skipped with `database_url_owner not configured in local environment`.
   - **1 test in `tests/unit/test_privacy_pii.py:122`:** Skipped with `Optional spaCy library and 'en_core_web_sm' model are not installed in the environment`.
   - **1 test in `tests/unit/test_review_eight_fixes.py:82`:** Skipped with `Draft v3 benchmark suite not generated`.
3. **Root 730 Profile:**
   The root ~730 profile represents execution across all folders (`tests/unit/`, `tests/application/`, `tests/e2e/`, `tests/integration/`) in an active runtime environment where PostgreSQL has been prepared with `-SetupOnly`, optional live services are running, and auxiliary benchmark suites are present.

---

## 6. Reproducible Evaluation Instructions & Verified Asset Configuration

To independently reproduce all results reported here:

```powershell
# 1. Configure runtime environment
$env:PSYCOPG_IMPL='python'
$env:PATH="F:\PostgreSQL\bin;$env:PATH"

# 2. Run offline robustness & routing evaluation runner (isolated v2 directory)
& "F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe" scripts/run_offline_robustness.py --output-dir artifacts/audit/routing_audit_20261112_v2

# 3. Run unit & application regression test suite
& "F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe" -m pytest tests/unit/test_routing_safety_regressions.py -v
```

### Verified Asset Configuration & Exact 64-Character SHA-256 Hashes
All hashes verified directly from disk via SHA-256 calculation:

| Asset Name | Relative File Path | Exact SHA-256 Hash (64 Hex Characters) |
|---|---|---|
| **DistilBERT Model** | `artifacts/models/trained/distilbert-supportiq/model.safetensors` | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| **DistilBERT Tokenizer** | `artifacts/models/trained/distilbert-supportiq/tokenizer.json` | `5f218e0ea9eaa9f154815cc067351fb941bea26da81bfd12af3ded3cc66fa3ff` |
| **Approved Knowledge Base** | `data/knowledge/approved_kb.v2.json` | `aaa924c4b48dcd53a14269045b278b66f6e5e8ae9d1b614cd59b757102b78594` |
| **Intent Policy v2** | `apps/core_backend/config/policies/intent_policy.v2.json` | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| **AI Service Engine** | `apps/ai_service/engine.py` | `be086c71e1bb88867f516f170be76057a3cd09c7dda6b566c2b2b947a83a3d13` |
| **Core Routing** | `apps/core_backend/intent/routing.py` | `4abb1bdb26cee0f788373ccf1db20369dd3275e19e170080cd40f1e1a8ca64e7` |
| **Retrieval Adapter** | `apps/core_backend/retrieval/adapter.py` | `2c1dee436530a3708dbdc0b75152b1e92092dc4ba7e3800d282a6fc35be422b1` |
