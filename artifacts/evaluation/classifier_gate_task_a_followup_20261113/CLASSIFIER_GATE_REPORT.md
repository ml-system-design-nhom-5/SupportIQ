# Task C Independent Classifier Acceptance Gate Report

- **Generated At:** `2026-11-13T02:23:33.637242+00:00`
- **Gate Decision:** **`REJECT`**
- **Failure Reasons:** `['missing_provenance_field:base_model', 'missing_provenance_field:dataset_hashes', 'missing_provenance_field:git_commit', 'missing_provenance_field:training_lineage', 'oos_draft_leak']`
- **Suite Boundary Note:** system_acceptance_156 and final_acceptance_24 are explicitly labeled known_acceptance_regression_not_unseen_holdout.

## 1. Provenance & Split Isolation

- **Candidate Dir:** `C:\Users\PC\orca\workspaces\SupportIQ\supportiq-final-routing\artifacts\evaluation\task_a_followup_20261113\candidate_model`
- **Valid 46-Label Bijection:** `True`
- **Provenance Passed:** `False` (`['missing_provenance_field:training_lineage', 'missing_provenance_field:dataset_hashes', 'missing_provenance_field:base_model', 'missing_provenance_field:git_commit']`)
- **Split Isolation & Gold Contamination Passed:** `True` (`[]`)

## 2. Serving vs Candidate Comparison

| Suite / Check | Serving (`distilbert-supportiq`) | Candidate | Notes |
| :--- | :--- | :--- | :--- |
| **ML OOD (N=80) Leaks** | `0/80` | `1/80` (`['oos-multi_intent-02']`) | Zero OOD leaks required |
| **ML Noise (N=420) 12-Label Acc / Macro-F1** | `0.6548` / `0.6817` | `0.7929` / `0.8012` | 12 supported labels in `ml_noise` |
| **System Acceptance 34-Label (N=39) Acc / Macro-F1** | `0.6154` / `0.6471` | `0.6154` / `0.6520` | All 34 escalated labels (`system_acceptance`) |
| **ML Noise ECE / Binary Brier** | `0.0920` / `0.1828` | `0.1118` / `0.1691` | Top-1 binary Brier |
| **Known Acceptance Regression (`system_acceptance` 34 `draft_expected`) Raw / Correct-Intent** | `21/34` / `17/34` | `17/34` / `15/34` | Regression suite, NOT unseen holdout |
| **Known Acceptance Regression (`system_acceptance` 63 Mandatory) Strict Match / Real Leaks** | `21/63` / `[]` | `22/63` / `[]` | Strict `expected.actions` match |
| **Known Acceptance Regression (`final_acceptance` 12 Answerable) Raw / Correct-Intent / Wrong-Intent IDs** | `5/12` / `4/12` (`['final-case-02']`) | `5/12` / `5/12` (`[]`) | Regression suite, NOT unseen holdout |

## 3. Follow-Up Supplement (`32e9781`): `domain_negatives`, SHA-256 Lineage & Tradeoff

Full JSON: [`followup_supplement.json`](followup_supplement.json)

- **Physical SHA-256 Verification (`matches_manifest: True` all):**
  - Candidate weights (`model.safetensors`): `b9e500b2997d54e62ffed9a805f84996b4633f103c2b9b7504e6fee8880aed4e`
  - Tokenizer (`tokenizer.json`): `5f218e0ea9eaa9f154815cc067351fb941bea26da81bfd12af3ded3cc66fa3ff`
  - `domain_templates.jsonl`: `3667c0d704f9ca85b71b45b42c919d412405098b471ca5f9c24449ebe9b049a5`
  - `domain_negatives.jsonl`: `fdaae87da2cdd2d6413365d9cdb798ae1ceb41ac4377dce50f8f424d0555672e`
- **Note on Gate Provenance Schema:** Worker A's `candidate_provenance_manifest.json` records `lineage`, `authored_datasets`, `models`, and `promotion_gate` (`promotion_approved: false`) cleanly, while `classifier_acceptance_gate.py` strictly checks legacy top-level keys (`training_lineage`, `dataset_hashes`, `base_model`, `git_commit`). Both Worker A's own promotion gate (`promotion_approved: false`) and Task C's independent gate (**`REJECT`**) reject promotion.
- **Independent `domain_negatives.jsonl` Isolation & Eval (`90` rows):** `train=36` (12 groups), `calibration=27` (9 groups), `eval=27` (9 groups) passed split isolation & gold contamination (`passed: True`, `0` exact/Jaccard matches vs `1,009` gold prompts); held-out negative eval: **`27/27 (1.0)` safe (`0` false drafts)** for both Serving and Follow-Up.
- **Independent `domain_templates.jsonl` Held-Out Eval (`72` rows):** Serving `0.4722` acc (`23/72` raw / `18/72` correct-intent draftable) vs Follow-Up **`0.8056` acc** (`24/72` raw / `22/72` correct-intent draftable).
- **Safety Improvement vs Coverage-Confidence Tradeoff:** Uniform-KL negative regularization (`T=1.0`, `neg_loss_weight=0.75`) eliminated `4cb07f4`'s `34_label_regression_system_acceptance` (`0.6154` / `0.6520` >= Serving `0.6154` / `0.6471`) and reduced `ml_oos_80` leaks (`2/80 -> 1/80` `['oos-multi_intent-02']`), while tightening answerable draft coverage (`system_acceptance` `30/34 -> 17/34` raw, `28/34 -> 15/34` correct-intent; `final_acceptance` `8/12 -> 5/12`). Worker A also reports `1` unanswerable leak (`final-case-21`, pre-existing static expired-KB case) and Bitext `46`-label holdout (`n=6,690`, not re-run in Task C): `0.9946` all-46 / `0.9955` other-34 accuracy. Serving assets (`distilbert-supportiq`) remain **unmodified**.

