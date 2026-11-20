# Task C Independent Classifier Acceptance Gate Report

- **Generated At:** `2026-11-13T01:56:48.581742+00:00`
- **Gate Decision:** **`REJECT`**
- **Failure Reasons:** `['34_label_regression_system_acceptance', 'mandatory_escalation_unsafe_draft_leak', 'mandatory_strict_action_regression', 'missing_group_isolated_holdout', 'missing_or_unverified_provenance', 'noise_safe_routing_regression', 'oos_draft_leak', 'wrong_intent_draft_regression']`
- **Suite Boundary Note:** system_acceptance_156 and final_acceptance_24 are explicitly labeled known_acceptance_regression_not_unseen_holdout.

## 1. Provenance & Split Isolation

- **Candidate Dir:** `F:\Năm 3\SD\project\SupportIQ\artifacts\models\finetuned\supportpilot-distilbert`
- **Valid 46-Label Bijection:** `True`
- **Provenance Passed:** `False` (`['missing_or_unverified_provenance']`)
- **Split Isolation & Gold Contamination Passed:** `False` (`['missing_group_isolated_holdout']`)

## 2. Serving vs Candidate Comparison

| Suite / Check | Serving (`distilbert-supportiq`) | Candidate | Notes |
| :--- | :--- | :--- | :--- |
| **ML OOD (N=80) Leaks** | `0/80` | `1/80` (`['oos-multi_intent-07']`) | Zero OOD leaks required |
| **ML Noise (N=420) 12-Label Acc / Macro-F1** | `0.6548` / `0.6817` | `0.6714` / `0.6961` | 12 supported labels in `ml_noise` |
| **System Acceptance 34-Label (N=39) Acc / Macro-F1** | `0.6154` / `0.6471` | `0.5897` / `0.5951` | All 34 escalated labels (`system_acceptance`) |
| **ML Noise ECE / Binary Brier** | `0.0920` / `0.1828` | `0.1418` / `0.1871` | Top-1 binary Brier |
| **Known Acceptance Regression (`system_acceptance` 34 `draft_expected`) Raw / Correct-Intent** | `21/34` / `17/34` | `26/34` / `23/34` | Regression suite, NOT unseen holdout |
| **Known Acceptance Regression (`system_acceptance` 63 Mandatory) Strict Match / Real Leaks** | `21/63` / `[]` | `20/63` / `['uns-return_product_in_store-01', 'uns-track_delivery-01']` | Strict `expected.actions` match |
| **Known Acceptance Regression (`final_acceptance` 12 Answerable) Raw / Correct-Intent / Wrong-Intent IDs** | `5/12` / `4/12` (`['final-case-02']`) | `8/12` / `6/12` (`['final-case-02', 'final-case-12']`) | Regression suite, NOT unseen holdout |
