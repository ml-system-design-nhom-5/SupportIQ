# Task C Independent Classifier Acceptance Gate Report

- **Generated At:** `2026-11-13T08:05:51.273808+00:00`
- **Gate Decision:** **`REJECT`**
- **Failure Reasons:** `['mandatory_escalation_unsafe_draft_leak']`
- **Suite Boundary Note:** system_acceptance_156 and final_acceptance_24 are explicitly labeled known_acceptance_regression_not_unseen_holdout.

## 1. Provenance & Split Isolation

- **Candidate Dir:** `C:\Users\PC\orca\workspaces\SupportIQ\supportiq-final-routing\artifacts\evaluation\task_a_closure_20261113\candidate_model`
- **Valid 46-Label Bijection:** `True`
- **Provenance Passed:** `True` (`[]`)
- **Split Isolation & Gold Contamination Passed:** `True` (`[]`)
- **Calibration Manifest Audit:** `True` / valid=`True` (`T=1.0429`, `rejector=True`)
- **Runtime Parity Audit Passed:** `True`

## 2. Serving vs Candidate Comparison

- **Candidate Score Path:** `{'score_kind': 'calibrated_probability', 'temperature': 1.0429, 'calibrated': True, 'experimental_rejector_active': True}`

| Suite / Check | Serving (`distilbert-supportiq`) | Candidate | Notes |
| :--- | :--- | :--- | :--- |
| **ML OOD (N=80) Leaks** | `0/80` | `0/80` (`[]`) | Zero OOD leaks required |
| **ML Noise (N=420) 12-Label Acc / Macro-F1** | `0.6548` / `0.6817` | `0.8095` / `0.8265` | 12 supported labels in `ml_noise` |
| **System Acceptance 34-Label (N=39) Acc / Macro-F1** | `0.6154` / `0.6471` | `0.6667` / `0.7059` | All 34 escalated labels (`system_acceptance`) |
| **ML Noise ECE / Binary Brier** | `0.0920` / `0.1828` | `0.0664` / `0.1231` | Top-1 binary Brier |
| **Known Acceptance Regression (`system_acceptance` 34 `draft_expected`) Raw / Correct-Intent / Prec / Abst** | `21/34` / `17/34` / `0.809524` / `0.382353` | `26/34` / `20/34` / `0.769231` / `0.235294` | Regression suite, NOT unseen holdout |
| **Known Acceptance Regression (`system_acceptance` 63 Mandatory) Strict Match / Real Leaks / Uninjected Faults** | `21/63` / `[]` / `1` | `22/63` / `['una-product_information-01']` / `1` | Strict `expected.actions`; uninjected faults separated |
| **Known Acceptance Regression (`final_acceptance` 12 Answerable) Raw / Correct-Intent / Prec / Wrong-Intent** | `5/12` / `4/12` / `0.8` (`['final-case-02']`) | `8/12` / `8/12` / `1.0` (`[]`) | Regression suite, NOT unseen holdout |
