# SupportIQ Automated Evaluation & Regression Report

> **Generated At:** `2026-11-05T18:57:45.187997+00:00`  
> **Evaluation Target:** [docs/ARCHITECTURE.md](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md)  
> **Regression Status:** `NO REGRESSION (STABLE)`  

---

## 1. Metrics vs. Architectural Requirements

| Metric | Target | Previous | Current | Delta | Status | Regression |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| `intent_accuracy` | >= 0.85 | 0.9679 | **0.9679** | +0.0000 | **PASS** | STABLE |
| `intent_macro_f1` | >= 0.85 | 0.9736 | **0.9736** | +0.0000 | **PASS** | STABLE |
| `intent_ece` | <= 0.1 | 0.1063 | **0.1063** | +0.0000 | **OBSERVE** | STABLE |
| `intent_brier` | <= 0.15 | 0.0169 | **0.0169** | +0.0000 | **PASS** | STABLE |
| `intent_ood_detection` | >= 0.9 | 1.0000 | **1.0000** | +0.0000 | **PASS** | STABLE |
| `intent_far` | <= 0.05 | 0.0000 | **0.0000** | +0.0000 | **PASS** | STABLE |
| `intent_frr` | <= 0.05 | 0.0175 | **0.0175** | +0.0000 | **PASS** | STABLE |
| `rag_recall_at_1` | >= 0.7 | 0.7941 | **0.7941** | +0.0000 | **PASS** | STABLE |
| `rag_recall_at_3` | >= 0.8 | 0.9706 | **0.9706** | +0.0000 | **PASS** | STABLE |
| `rag_recall_at_5` | >= 0.85 | 0.9706 | **0.9706** | +0.0000 | **PASS** | STABLE |
| `rag_precision_at_3` | >= 0.3 | 0.3235 | **0.3235** | +0.0000 | **PASS** | STABLE |
| `rag_mrr` | >= 0.75 | 0.8824 | **0.8824** | +0.0000 | **PASS** | STABLE |
| `rag_ndcg_at_3` | >= 0.8 | 0.9055 | **0.9055** | +0.0000 | **PASS** | STABLE |
| `grounding_claim_grounding_rate` | >= 0.9 | 1.0000 | **1.0000** | +0.0000 | **PASS** | STABLE |
| `grounding_citation_correctness` | >= 1.0 | 1.0000 | **1.0000** | +0.0000 | **PASS** | STABLE |
| `grounding_hallucination_rate` | <= 0.02 | 0.0000 | **0.0000** | +0.0000 | **PASS** | STABLE |
| `grounding_abstention_rate` | >= 0.95 | 1.0000 | **1.0000** | +0.0000 | **PASS** | STABLE |

---

## 2. Failure Diagnosis & Remediation Recommendations

### `intent_ece` (OBSERVE)
- **Current Value:** `0.1063` (Target: `<= 0.1`)
- **Diagnosis:** Calibration ECE (0.1063) exceeds 0.1000. Softmax probabilities are overconfident on peak classes.
- **Recommended Fix:** Apply temperature scaling (T=1.12) to model logits or isotonic regression calibration on validation split.

---

## 3. Evaluation Loop Execution Summary
- **Automated Loop:** `Execute -> Measure -> Evaluate -> Diagnose -> Recommend -> Regression Check`
- **Historical Snapshot:** `artifacts/evaluation/regression/history/evaluation_20261105_185745Z.json`
- **Production Safeguard:** Evaluation runner is strictly read-only on production models and golden test sets.
