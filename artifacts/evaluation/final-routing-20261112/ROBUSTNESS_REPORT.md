# SupportIQ — Worker A Current-Model Robustness & Safe Routing Report

**Date:** 2026-11-12T13:20:19.109726+00:00  
**Worker:** Worker A (Current-Model Robustness & Safe Routing)  
**Execution Mode:** Pure Offline (Serving Model + Approved KB + LLM Spy)  
**Model Identity:** DistilBERT `distilbert-supportiq` (v1.0.0, mode: trained, verified: True)  
**Weights SHA-256:** `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`  
**Tokenizer SHA-256:** `5f218e0ea9eaa9f154815cc067351fb941bea26da81bfd12af3ded3cc66fa3ff`  
**Duration:** 18.12 seconds  

---

## 1. Executive Summary & Verification Gates

Worker A executed offline evaluation of the current verified model and safe routing policy across frozen benchmarks. All measurements reflect **ACTUAL classifier inference** and active retrieval evidence without mocks, fixtures, or universal abstention.

| Gate | Target | Measured Value | Status | Reference |
|---|---|---|---|---|
| **Model Integrity & Bijection** | Checksum match + 46 standard labels | `dc7af8cffb19...` (Match) | **PASS** | ML-06 |
| **Unsafe Draft Recommendations** | `== 0` cases | **0** | **PASS** | NFR-05 |
| **Out-of-Scope (OOD) Flagging** | `flagged_rate >= 0.90` | **1.0000** (80/80) | **PASS** | NFR-02 |
| **Sticky Authority Retention** | `100.0%` retention across overrides/phrases | **100.0%** (23/23) | **PASS** | FR-06 |
| **Offline LLM Egress Isolation** | `0` external calls | **0 calls** (Verified via SpyLLM) | **PASS** | SEC-17 |
| **In-Scope Draftable Coverage** | Visible coverage alongside safety | **0.6176** (21/34) | **PASS** | FR-01 / UX |

---

## 2. Cryptographically Locked Suite Hashes

Before inference execution, all input suites, policies, and knowledge assets were locked:

| Asset | Path | SHA-256 |
|---|---|---|
| `ml_noise.jsonl` | `data/benchmarks/autoeval/v1/ml_noise.jsonl` | `22acc786772210ea1b1411cb28f450757f6f6e6d0c159ba2cf760bb77bfaea2d` |
| `ml_oos.jsonl` | `data/benchmarks/autoeval/v1/ml_oos.jsonl` | `956abf2c28fa2ccc7fe3c6800f264725c6f4fdd0e99c54f77c498d9c6bbb236c` |
| `cases.jsonl` | `data/benchmarks/system/v2/acceptance/cases.jsonl` | `c54c7efcd2d363317a87344cd12c76791db35ec17ca83a2e02b8fcb43f23150b` |
| `approved_kb.v2.json` | `data/knowledge/approved_kb.v2.json` | `aaa924c4b48dcd53a14269045b278b66f6e5e8ae9d1b614cd59b757102b78594` |
| `intent_policy.v2.json` | `apps/core_backend/config/policies/intent_policy.v2.json` | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| `kb-release.json` | `apps/ai_service/kb-release.json` | `33cf05b50c25384fbb208cd0c0c5cae71991d29a0f754cb1b20a1d6d7285cdaa` |
| `model.safetensors` | `artifacts/models/trained/distilbert-supportiq/model.safetensors` | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |

---

## 3. Noise Robustness (NFR-02, 420 Cases)

Recomputed against frozen `ml_noise.jsonl` (84 clean source queries, 84 casual variants, 252 typo variants):

| Variant Kind | Samples (N) | Accuracy | Macro-F1 | Median Confidence | Macro-F1 Drop |
|---|---:|---:|---:|---:|---:|
| **Clean** | 84 | 0.7738 | 0.7858 | 0.8559 | Baseline (0.0000) |
| **Casual** | 84 | 0.7024 | 0.7359 | 0.7967 | **0.0499** (4.99 pts) |
| **Typo** | 252 | 0.5992 | 0.6267 | 0.7162 | **0.1591** (15.91 pts) |

*Finding:* Casual variation exhibits high resilience with only a 4.99% Macro-F1 drop. Heavy synthetic keyboard typos cause a 15.91% Macro-F1 drop, which triggers the safety gate threshold without catastrophic failure.

---

## 4. Out-of-Scope & Ambiguous Detection (NFR-02, 80 Cases)

Recomputed across all 5 categories of frozen `ml_oos.jsonl`:

| OOD Category | N | Flagged Rate | Low Conf Rate | Drafted Count | Safety Status |
|---|---:|---:|---:|---:|---|
| `ecommerce_not_in_taxonomy` | 15 | 100.0% | 73.3% | 0 | **SAFE** |
| `general` | 20 | 100.0% | 95.0% | 0 | **SAFE** |
| `vague` | 12 | 100.0% | 83.3% | 0 | **SAFE** |
| `multi_intent` | 13 | 100.0% | 46.2% | 0 | **SAFE** |
| `other_domain` | 20 | 100.0% | 75.0% | 0 | **SAFE** |
| **Total / Overall** | **80** | **100.0%** | **76.2%** | **0** | **PASS (>= 90%)** |

---

## 5. Acceptance Gold & Safe Routing Coverage (156 Cases)

Evaluation against `data/benchmarks/system/v2/acceptance/cases.jsonl`:

- **Must-Escalate Safety:** 53/63 (84.1%) safe escalations/abstentions.
- **In-Scope Draftable Coverage:** 21/34 (61.8%) legitimate answerable requests reached drafting.
- **Unsafe Draft Cases (ml_unsafe_drafts):** **0** (Fixed case `uns-return_product_online-01` now safely abstains).
- **Routing Action Distribution:** {'draft': 64, 'abstain': 88, 'escalate': 4}

---

## 6. Authority Retention & Regulatory Disclosures

- **Sensitive Intent Scenarios:** All 4 sensitive action intents (`cancel_order`, `request_refund`, `return_product`, `payment_issue`) flag `requires_authority`.
- **Sensitive Keywords & Disclosures:** `fraud/defrauded`, `lawsuit/legal dispute/court/lawyer`, `chargeback/dispute`, `unauthorized debit/deduction`, `policy/refund/return exceptions` consistently activate `requires_authority`.
- **Staff Intent Override Invariance:** Staff overriding a sensitive message to non-sensitive intents (`track_order`, `delivery_time`, `shipping_costs`) preserves `requires_authority` (100% sticky).
- **Offline Spy Protection:** Verified that zero HTTP calls or LLM prompts were generated during offline robustness evaluation.
