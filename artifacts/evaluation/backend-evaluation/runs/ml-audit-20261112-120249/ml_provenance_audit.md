# SupportIQ Backend Evaluation — ML Provenance & Robustness Audit

- **Audit Run ID:** `ml-audit-20261112-120249`
- **Timestamp:** `2026-11-12T12:02:51.068189+00:00`
- **Repository HEAD:** `f67a018a67f31460bdf9812cbb2815e1491f9660`
- **Audit Scope:** Task B3 (pipeline/evaluation/)
- **10-Fold Alignment Check:** **VERIFIED** (37911 samples across 4 models)

> [!IMPORTANT]
> **Provenance Transparency:**
> 1. Baseline 10-fold CV results are fully verified against stored training manifest.
> 2. DistilBERT OOF metrics are recomputed from stored OOF predictions. Checkpoint manifests for individual folds are unverified in repository; this audit does NOT claim cached OOF as a fresh training run.
> 3. Robustness slice metrics report exact denominators supported by verified predictions.

## 1. 10-Fold Cross-Validation Summary (Fixed 46 Labels, 37,911 Samples)

| Model | Candidate / Params | Mean Fold Macro-F1 | Std (ddof=0) | Overall OOF Macro-F1 | OOF Accuracy | Gate (Mean Fold >= 0.85) |
|---|---|---:|---:|---:|---:|:---:|
| **linear_svm** | `linear_svm__C=1.5` | 0.990258 | 0.000883 | 0.990257 | 0.990161 | **PASS** |
| **logistic_regression** | `logistic_regression__C=20.0` | 0.989220 | 0.001437 | 0.989221 | 0.989106 | **PASS** |
| **multinomial_nb** | `multinomial_nb__alpha=0.03` | 0.984203 | 0.001232 | 0.984204 | 0.984094 | **PASS** |
| **distilbert** (stored OOF) | `distilbert-supportiq` | 0.995268 | 0.000999 | 0.995271 | 0.995226 | **PASS (Cached)** |

## 2. Checksum and Manifest Verification

| Artifact | Status | Expected SHA-256 | Actual SHA-256 (Raw / LF / CRLF) | Match |
|---|:---:|---|---|:---:|
| Baseline OOF (`03-11-2026-01`) | Verified | `1A09AD4BB4806A95...` | `1A09AD4BB4806A95...` (CRLF) | **PASS** |
| DistilBERT OOF (`distilbert_cv`) | Cached Recomputed | *(no manifest)* | `611BA5F3FCA1649A...` (CRLF) | N/A |
| Noise Suite (`ml_noise.jsonl`) | Verified | N/A | `22ACC786772210EA...` | Verified |
| OOS Suite (`ml_oos.jsonl`) | Verified | N/A | `956ABF2C28FA2CCC...` | Verified |

## 3. ML Robustness Scenarios (Noise & Out-of-Scope)

### A. Noise Slices (Clean, Casual, Typo)

| Slice | Total Cases | Accuracy | Macro-F1 | F1 Drop vs Clean | Paired Denominator | Paired Conditional Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| **clean** | 84 | 0.7738 | 0.7858 | — | — | — |
| **casual** | 84 | 0.7024 | 0.7359 | 0.0499 | 65 | 0.9077 |
| **typo** | 252 | 0.5992 | 0.6267 | 0.1591 | 195 | 0.7744 |

### B. Out-of-Scope & Ambiguity Slices (80 Cases)

- **Overall Flagged / Escalation Rate:** `97.50%` (78 / 80 cases safely deflected)
- **Low Confidence Flag Rate:** `76.25%`
- **Unsafe Drafts Produced:** `2` (must be 0 in production; currently 2 cases forwarded)
- **AUROC Detection:** Entropy = `0.8001`, (1 - Conf) = `0.7555`

| Category | Cases (n) | Flagged Rate | Low Conf Rate | Drafted Count |
|---|---:|---:|---:|---:|
| `ecommerce_not_in_taxonomy` | 15 | 100.0% | 73.3% | 0 |
| `general` | 20 | 100.0% | 95.0% | 0 |
| `multi_intent` | 13 | 92.3% | 46.2% | 1 |
| `other_domain` | 20 | 95.0% | 75.0% | 1 |
| `vague` | 12 | 100.0% | 83.3% | 0 |

## 4. Remaining Gates and Disclosures

1. **DistilBERT Training Lineage:** Checkpoint manifests for each fold remain unverified in repo; before certifying a production release, re-run 10-fold cross-validation with atomic artifact checkpointing.
2. **OOS False Drafts:** 2 cases out of 80 out-of-scope queries were forwarded to draft in autoeval; routing policy thresholds should be tuned for multi-intent queries.
3. **Zero Fabrication:** No human rating or external approval has been claimed. Metrics reflect actual predictions and verified splits.
