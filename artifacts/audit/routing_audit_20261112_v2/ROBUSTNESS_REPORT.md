# SupportIQ — Worker A Current-Model Robustness & Safe Routing Report (Followup v3)

**Date:** 2026-11-12T16:11:23.730425+00:00  
**Worker:** Worker A (Current-Model Robustness & Safe Routing)  
**Execution Mode:** Pure Offline (Serving DistilBERT + Approved KB + OfflineSpyLLM)  
**Git Commit:** `71d62f89faed211d19f2673bf5f21ea516ba05c2` (dirty=True)  
**Model Identity:** DistilBERT `distilbert-supportiq` (v1.0.0, mode: trained, verified: True)  
**Weights SHA-256:** `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`  
**Tokenizer SHA-256:** `5f218e0ea9eaa9f154815cc067351fb941bea26da81bfd12af3ded3cc66fa3ff`  
**Duration:** 16.57 seconds  

---

## 1. Executive Summary & Component-Level Verification Gates

Worker A executed comprehensive offline evaluation of the verified serving model and safe routing policy across frozen benchmarks. All evaluations reflect **ACTUAL classifier inference** and active retrieval evidence without mocks, fixtures, or universal abstention.

All gate statuses below are **dynamically derived** from actual component execution results:

| Component Verification Gate | Target Requirement | Measured Value | Derived Status |
|---|---|---|---|
| **Model Integrity & Bijection** | DistilBERT weights match release manifest; 46 standard labels bijection | Weights: dc7af8cffb19..., Tokenizer: 5f218e0ea9ea..., 46 Labels | **PASS** |
| **ML-Attributable Unsafe Drafts** | == 0 cases (supported/unsupported slices without faults) | 0 unsafe drafts | **PASS** |
| **Supported Return Courier Pickup** | POL-RET-002 courier pickup query reaches draft without refusal | 2/2 reached draft | **PASS** |
| **Sticky Authority Retention** | 100.0% retention across all explicit sensitive scenarios and overrides | 100.0% (23/23) | **PASS** |
| **Benign Authority Specificity** | 0 false authority positive flags on non-sensitive product queries | 0 false positives / 10 benign | **PASS** |
| **Offline LLM Egress Isolation** | 0 external LLM calls during offline run | 0 calls (Verified via SpyLLM) | **PASS** |
| **OOD Safe Routing Rate** | >= 0.85 safe routing across all 80 ml_oos cases | 100.00% (80/80) | **PASS** |
| **Noise Safe Routing Rate** | >= 0.75 safe routing across all 420 ml_noise cases | 91.43% (384/420) | **PASS** |

**Component-Level Routing & Offline Robustness:** **PASS**  
*(Note: Whole-system end-to-end acceptance status is determined by live integration suites; offline evaluation verifies component routing, authority precedence, and policy scope boundaries).*

---

## 2. Headline Acceptance Benchmark Accounting (All 156 Cases)

Rather than narrowing the headline to only ML-attributable safety, the complete acceptance suite is accounted for transparently under the explicit contract adapter:

- **Total Acceptance Cases:** 156
- **In-Scope Draftable Requests:** 21/34 (61.8%) legitimate answerable tickets reached draft.
- **Mandatory Escalation Cases (`must_escalate == True`):** 63 total cases
  - **Observed Non-Drafting Count:** **62/63 (98.4%)**
  - **Explicit Human Escalation Actions:** **16/63 (25.4%)** explicitly recommended human queue escalation.
  - **Safe `manual_fallback` Abstentions:** **46/63 (73.0%)** abstained safely, but do not count as expected human escalation when benchmark strictly expects escalation.
  - **Action Set Matching on Mandatory Escalation:** **21/63 (33.3%)** matched the expected action set.
  - **Cases Reaching Draft:** **1/63 (1.6%)** (0 unanswerable cases drafting; 1 synthetic fault `unc-return_policy-04` marked NOT_EXECUTED offline).
- **Must-Not-Draft Cases (`must_not_draft == True`):** 68 total cases
  - **All Must-Not-Draft Cases (N=68):** **64/68 (94.1%)** observed safe non-drafting. Drafted cases (4, IDs: unc-return_policy-03, unc-return_policy-04, unc-refund_policy-01, unc-cancel_order-03): 4 synthetic faults (unc-return_policy-03, unc-return_policy-04, unc-refund_policy-01, unc-cancel_order-03) marked NOT_EXECUTED offline.
  - **Pure ML-Attributable Must-Not-Draft Cases (N=42):** **42/42 (100.0%)** safe non-drafting.
  - **ML-Attributable Unsafe Drafts:** **0 / 42 (0.0%)** on pure ML slices.
- **Contract Action Matching (decide_route Vocabulary Adapter):**
  - **Overall Exact Action Match:** 47.4% (74/156) across all 156 cases.
  - **Supported Comparable Slices Match:** 64.3% (54/84) on `supported` + `answerable` slices (measured without approved numeric target).
  - *(Contract mappings: `draft -> retrieve_draft`, `abstain -> manual_fallback`, `escalate -> escalate`. `abstain` is strictly NOT equated to `escalate`).*
- **Exact Expected Reason Match Rate:** 30.1% (47/156)
- **Raw Engine Recommendations:** {'draft': 55, 'abstain': 85, 'escalate': 16}
- **Adapted Routing Actions:** {'retrieve_draft': 55, 'manual_fallback': 85, 'escalate': 16}

---

## 3. Enumeration of Mandatory Cases Reaching Draft & Boundary Analysis (1 Cases)

The 1 cases with `must_escalate == True` that reached `draft` are enumerated below with full component boundary explanations:

| Case ID | Primary Slice | Fault | Predicted Intent (Conf) | Actual Route (Raw -> Adapted) | Expected Actions | Component & Runtime Boundary Analysis |
|---|---|---|---|---|---|---|
| `unc-return_policy-04` | `uncertainty_and_faults` | `encoder_failure` | `return_policy` (0.993) | `draft` -> `retrieve_draft` (`none`) | `escalate,clarify,manual_fallback` | Simulated Fault Boundary [NOT EXECUTED]: Test case has synthetic fault `encoder_failure`. In offline component evaluation, the live BGE retriever encoder is active; no synthetic encoder fault is injected at this interface. Thus, it completes normally and drafts. Recorded as not_executed_boundary with no success credit given. |

### Key Architectural Takeaways on the 1 Cases:
1. **Policy Scope Boundary & Unanswerable Cases:**
   Of the 18 unanswerable cases (`una-*`), 12 route to `escalate` with `insufficient_evidence` under `_policy_scope_requires_review`, 6 abstain, and 0 reach draft.
2. **Simulated Fault Boundary [NOT EXECUTED] (4 cases):**
   Drafted cases with synthetic faults (unc-return_policy-03, unc-return_policy-04, unc-refund_policy-01, unc-cancel_order-03) operate at the offline model/engine boundary without synthetic fault injection harness; live components execute normally. Recorded as `not_executed_boundary` with no success credit given.

---

## 4. Observed Model Limitation: Typo Degradation & Casual Variation (Hypothesized Subword Fragmentation)

Recomputed against frozen `ml_noise.jsonl` (84 clean source queries, 84 casual variants, 252 typo variants):

| Variant Kind | Samples (N) | Accuracy | Macro-F1 | Median Confidence | Macro-F1 Drop |
|---|---:|---:|---:|---:|---:|
| **Clean** | 84 | 77.38% | 0.7858 | 0.8577 | Baseline (0.0000) |
| **Casual** | 84 | 70.24% | 0.7359 | 0.8023 | **0.0499** (4.99 pts) |
| **Typo** | 252 | **59.92%** | **0.6267** | 0.7182 | **0.1591** (15.91 pts) |

> [!WARNING] Observed Model Limitation: Typo Sensitivity & Casual Degradation
> Under natural casual phrasing, the serving model achieves 70.24% accuracy (macro-F1 0.7359, a 4.99 pt drop from clean baseline 77.38%). Under synthetic character-level typos, accuracy drops sharply to **59.92%** (macro-F1 0.6267, a 15.91 pt drop). Hypothesized vulnerability: subword tokenization fragmentation on character-level corruptions, pending formal token-level ablation study. We do NOT claim high robustness on typos or casual perturbations, nor full unreserved acceptance; typo sensitivity is an observed model limitation requiring spelling normalization or typo-augmented fine-tuning in future model versions.

---

## 5. Retrieval Relevance Threshold: 0.55 vs 0.60 & Single Source of Truth

- **Unified Single Source of Truth:** `engine.py` directly queries `getattr(self.retriever, "relevance_threshold", 0.55)` rather than enforcing a hardcoded hidden 0.60 override.
- **Same-Suite Comparison:**
  - In Acceptance benchmark: 14 borderline cases fall into the `[0.55, 0.60)` band. All 14 are unsupported/unanswerable requests safely abstained by low confidence or out-of-scope intent rules.
  - In OOS benchmark: 9 cases fall into the `[0.55, 0.60)` band.
  - Unifying at `0.55` avoids dual hidden thresholds and artificial safe-by-refusal on borderline valid customer requests, while targeted semantic routing (`tax return` -> `out_of_scope_intent`) eliminates homonym false positives at the semantic layer.

---

## 6. Positive Supported Return Courier Pickup (POL-RET-002)

- **Root Semantic Boundary Fixed:** Narrowed regex specifically to external postal pickup services: `r"\b(?:schedule|book|arrange)\s+(?:a\s+)?postal\s+pickup\b|\bpostal\s+pickup\b"`.
- **Verified Positive Support:**
  - "How does free courier pickup work when I request a return on Tiki?" -> Reaches `draft` citing `POL-RET-002`.
  - "Does Tiki provide free courier pickup for returns?" -> Reaches `draft` citing `POL-RET-002`.

---

## 7. Explicit Sensitive Authority Denominators & Benign Specificity

Denominators are explicitly separated:

| Scenario Group | Denominator (N) | Target | Measured Result | Performance |
|---|---:|---|---|---|
| **Explicit Sensitive Requests & Overrides** | **23** | 100.0% Retention | **23/23** | **100.0% Recall** |
| **Benign Product Inquiries** | **10** | 0 False Positives | **0/10** | **100.0% Specificity (0% FPR)** |

- **Override Retention:** 3/3 sensitive customer queries retained `requires_authority` even when staff overrode to non-sensitive intents (`track_order`, `delivery_time`, `shipping_costs`).
- **Override Activation:** 4/4 benign queries activated `requires_authority` when staff overrode to sensitive action intents (`cancel_order`, `request_refund`, `return_product`, `payment_issue`).
- **Offline LLM Egress Isolation:** Exactly 0 HTTP calls or LLM prompts generated during offline robustness evaluation.
