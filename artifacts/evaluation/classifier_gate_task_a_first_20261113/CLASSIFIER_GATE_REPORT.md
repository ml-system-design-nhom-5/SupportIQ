# Task C Independent Classifier Acceptance Gate Report

- **Generated At:** `2026-11-13T02:17:30.078800+00:00`
- **Gate Decision:** **`REJECT`**
- **Failure Reasons:** `['34_label_regression_system_acceptance', 'missing_provenance_field:base_model', 'missing_provenance_field:dataset_hashes', 'missing_provenance_field:git_commit', 'missing_provenance_field:training_lineage', 'oos_draft_leak']`
- **Suite Boundary Note:** system_acceptance_156 and final_acceptance_24 are explicitly labeled known_acceptance_regression_not_unseen_holdout.

## 1. Provenance & Split Isolation

- **Candidate Dir:** `C:\Users\PC\orca\workspaces\SupportIQ\supportiq-final-routing\artifacts\evaluation\task_a_20261113\candidate_model`
- **Valid 46-Label Bijection:** `True`
- **Provenance Passed:** `False` (`['missing_provenance_field:training_lineage', 'missing_provenance_field:dataset_hashes', 'missing_provenance_field:base_model', 'missing_provenance_field:git_commit']`)
- **Split Isolation & Gold Contamination Passed:** `True` (`[]`)

## 2. Serving vs Candidate Comparison

| Suite / Check | Serving (`distilbert-supportiq`) | Candidate | Notes |
| :--- | :--- | :--- | :--- |
| **ML OOD (N=80) Leaks** | `0/80` | `2/80` (`['oos-multi_intent-02', 'oos-multi_intent-07']`) | Zero OOD leaks required |
| **ML Noise (N=420) 12-Label Acc / Macro-F1** | `0.6548` / `0.6817` | `0.8071` / `0.8186` | 12 supported labels in `ml_noise` |
| **System Acceptance 34-Label (N=39) Acc / Macro-F1** | `0.6154` / `0.6471` | `0.5897` / `0.6225` | All 34 escalated labels (`system_acceptance`) |
| **ML Noise ECE / Binary Brier** | `0.0920` / `0.1828` | `0.0528` / `0.1260` | Top-1 binary Brier |
| **Known Acceptance Regression (`system_acceptance` 34 `draft_expected`) Raw / Correct-Intent** | `21/34` / `17/34` | `30/34` / `28/34` | Regression suite, NOT unseen holdout |
| **Known Acceptance Regression (`system_acceptance` 63 Mandatory) Strict Match / Real Leaks** | `21/63` / `[]` | `22/63` / `[]` | Strict `expected.actions` match |
| **Known Acceptance Regression (`final_acceptance` 12 Answerable) Raw / Correct-Intent / Wrong-Intent IDs** | `5/12` / `4/12` (`['final-case-02']`) | `8/12` / `8/12` (`[]`) | Regression suite, NOT unseen holdout |
