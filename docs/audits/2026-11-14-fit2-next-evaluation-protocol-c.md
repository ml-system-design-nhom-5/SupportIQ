# Fit2 Next Evaluation Protocol & Baseline Integrity Freeze (Worker C)

**Status:** `PROTOCOL FROZEN` (`2026-11-14`, branch `minh`)  
**Machine-Readable Manifest:** [protocol_manifest.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_next_protocol_c_20261114/protocol_manifest.json)  
**Prior Baseline Audit Reused:** [2026-11-14-fit2-v5r2-independent-evaluation-c.md](file:///F:/Năm 3/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-v5r2-independent-evaluation-c.md) (`4e1e06d48202e86589b01eb34d1ee8656fbc7452`)

This protocol freezes baseline evidence, evaluation inputs, surface parity rules, comparative minima, and acceptance gates for evaluating the upcoming single-factor TRAIN return-policy/store-channel contrast trained from **Original Fit2**. Execution involved zero fits, zero live LLM calls, and zero access to A's mutable training preparation or D's active local serving configuration.

---

## 1. Verified Baseline Model, Initializer, Calibration & Runtime Identity

All 6 archive files in [archive_sha_inventory.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/reconstructed-fit2-supcon-20261113/archive_sha_inventory.json) verified bit-identical on disk:

| Artifact | Path | Verified SHA-256 / State |
| :--- | :--- | :--- |
| **Original Fit2 Weights** | [model.safetensors](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors) | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (`267,967,920` bytes) |
| **Original Fit2 Calibration** | [calibration_manifest.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json) | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` (`selective_calibration.v1`, `fit2-supcon-energy-boundary-v1`, `num_labels=46`, `valid_46_label_bijection=true`, `max_length=64`, `T=1.0`, `min_T=1.0`, `calibrated=true`, `cal_n=776`, `selective_rejector.enabled=false`) |
| **Original Fit2 Provenance** | [candidate_provenance_manifest.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/reconstructed-fit2-supcon-20261113/candidate_provenance_manifest.json) | `79428567d0a4d23e69f224fca86ffcbdd26a4fe6dc5cd45980ff45bfb644574f` (`git_commit=4939970b...`, `init_checkpoint=reconstructed-closure-fit1-20261113`, `max_neg_cal_supported12_prob=0.557692`) |
| **Original Fit2 Config / Tokenizer** | `config.json`, `tokenizer.json`, `tokenizer_config.json` | `6fa1fa9cc6a9...`, `41b9d12a4c55...`, `15c067a68c4f...` |
| **Fit1 Initializer** | [model.safetensors](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/reconstructed-closure-fit1-20261113/model.safetensors) | `95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6` (exact match to Fit2 provenance `init_weights_sha256`) |
| **Serving Baseline** | [model.safetensors](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/trained/distilbert-supportiq/model.safetensors) | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| **KB / Release / Policy** | [approved_kb.v2.json](file:///F:/Năm 3/SD/project/SupportIQ/data/knowledge/approved_kb.v2.json), [kb-release.json](file:///F:/Năm 3/SD/project/SupportIQ/apps/ai_service/kb-release.json), [intent_policy.v2.json](file:///F:/Năm 3/SD/project/SupportIQ/apps/core_backend/config/policies/intent_policy.v2.json) | `f8dcfbbb...`, `cf450a72...`, `8789ee26...` |
| **Local `.local/ai.env`** | `.local/ai.env` (untouched) | `SUPPORTIQ_MODEL_DIR=...reconstructed-fit2-supcon-20261113`, `SUPPORTIQ_MAX_LIVE_LLM_REQUESTS=2`, `SUPPORTIQ_LLM_MAX_ATTEMPTS=1` (ledger est. `2 of 24` live calls remaining per [D audit](file:///F:/Năm 3/SD/project/SupportIQ/docs/audits/2026-11-14-original-fit2-local-activation-d.md)) |

**Archived Rejected Candidates (do not reactivate or promote):**
- `v4p1` (`fit2-boundary-contrast-v4p1`, `model.safetensors` `e1039f92...`, `calibration_manifest.json` `73e0d60b...`) -> `REJECTED / ARCHIVED`.
- `v5-r2` (`fit2-taxonomy-audit-v5-r2`, `model.safetensors` `0b2d26c2...`, `calibration_manifest.json` `ca3d711c...`) -> `REJECTED / ARCHIVED`; all 27 hashes in [run_manifest.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v5r2_independent_20261114/run_manifest.json) verified `0` mismatches.

---

## 2. Frozen Evaluation Suites & Leakage Audit

All 10 evaluation suites verified against disk SHA-256, distinct raw/normalized text counts, grouping structure, and `pseudonymize(text, {})` sensitivity:

| Suite | Path | SHA-256 (prefix) | Rows | Distinct Raw / Norm | Distinct Base / Group | `pseudonymize` Diffs | Protocol Role |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `final24` | [cases.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/data/benchmarks/final_acceptance/cases.jsonl) | `fcb1007bf026...` | 24 | 24 / 24 | 24 `source_id` (`_extract_group=1`) | 1 (`final-case-14`) | Final acceptance |
| `sa156` | [cases.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/data/benchmarks/system/v2/acceptance/cases.jsonl) | `c54c7efcd2d3...` | 156 | 156 / 156 | 156 `source_id` (`_extract_group=1`) | 32 | System acceptance |
| `noise420` | [ml_noise.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/data/benchmarks/autoeval/v1/ml_noise.jsonl) | `e62cfc978725...` | 420 | 420 / 420 | 84 `source_id` (5 variants ea) | 89 | 12-class noise & F1 |
| `oos80` | [ml_oos.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/data/benchmarks/autoeval/v1/ml_oos.jsonl) | `93422de07094...` | 80 | 80 / 80 | 80 `source_id` | 2 | OOS safety |
| `ind36` | [cases.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_independent_gate_20261113/cases.jsonl) | `19a56d87299f...` | 36 | 36 / 36 | 36 `source_id` | 2 | Historical gate |
| `old_sealed72` | [sealed_holdout_cases.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_cases.jsonl) | `c874a2b829fa...` | 72 | 72 / 72 | 72 (`_extract_group=72`) | 3 | Sealed holdout (`2026-11-13`) |
| `fresh34` | [fresh_holdout_34.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v4p1_independent_20261114/fresh_holdout_34.jsonl) | `c1482fb4f8e6...` | 34 | 34 / 34 | 34 (`_extract_group=34`) | 9 | Historical regression only (not unseen) |
| `pos175` | [boundary_pos_evaluation.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/boundary_pos_evaluation.jsonl) | `397b0cb6a487...` | 175 | 175 / 175 | 85 (`_extract_group=85`) | 0 | Boundary positive |
| `neg51` | [boundary_neg_evaluation.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/boundary_neg_evaluation.jsonl) | `7a905de90b19...` | 51 | 51 / 51 | 20 (`_extract_group=20`) | 0 | Boundary negative |
| `bitext6690` | [bitext_test_6690.jsonl](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/bitext_test_6690.jsonl) | `c2279c30a6e7...` | 6690 | 6690 / 6690 | 6690 (`_extract_group=6690`) | — | 46-class bitext regression |

- **Verified Zero Split Leakage:** Exact normalized text overlap between all 10 suites and `v5-r2` `full_train_split.jsonl` (`11444` rows / `7529` groups, SHA `d1adf66ded3d...`) plus `full_cal_split.jsonl` (`885` rows / `786` groups, SHA `116231beaff9...`) is **`0`**. `CG.check_split_isolation_and_gold_contamination` passed (`failure_reasons=[]`, `text_overlaps=0`, `gold_exact_matches=[]`, `gold_high_jaccard_matches=[]`).
- **Archive Lineage Note:** `candidate_provenance_manifest.json` on Original Fit2 records pre-run-records split hashes `c0012ccb...` and `dc8c7773...` which were not standalone-persisted in `run-records-*/inputs/`; `bitext_cal` (`54e9e86a...`), `bitext_train_clean` (`36f6e74f...`), `bitext_train_noisy` (`5233abff...`), and `v4p1`/`v5-r2` `full_train_split` + `full_cal_split` (`885`) are persisted. Candidate evaluation MUST run the same overlap + `check_split_isolation_and_gold_contamination` check against the new candidate's actual `full_train_split.jsonl` and `full_cal_split.jsonl`.

---

## 3. Original Fit2 Baseline Metrics & Known Safety Failures

Reference measurements verified in [suites_comparison.json](file:///F:/Năm 3/SD/project/SupportIQ/artifacts/evaluation/fit2_v5r2_independent_20261114/suites_comparison.json) and `v4p1` `orig_fit2_gate_suites` (`0` live LLM calls):

- **`final24`:** `ans12_correct=10/12` (`final-case-02`, `final-case-08` dropped; `0` wrong), `active_unans8_leaks=0`, `injected_uninjected4_drafted=['final-case-21']` (Engine/Runner) across all surfaces.
- **`sa156`:** `sup34` (`draft_expected`) `25/34` (`raw_draft=28`, precision `0.892857`), `labeled_153_acc=0.797386`, `labeled_153_macro_f1=0.732573`, `esc34_acc=0.692308`, `esc34_macro_f1=0.735294`. `mand63`: `42/63` raw (`9` leaks), `57/63` Engine (`2` leaks: `uns-order_history-01`, `uns-return_product_in_store-01`), `50/63` Runner (`1` real leak: `uns-return_product_in_store-01` -> `return_policy` @ `0.682784`; `unc-return_policy-04` is an uninjected fault fixture).
- **`noise420`:** `acc_12=0.857143`, `macro_f1_12=0.857307`, `ece_10bin=0.063060`, `brier=0.113556`:
  - `raw_pre` / `raw_post`: `303` drafted / `276` correct / `27` wrong (`0.935714` safe)
  - `bare` / Gate (`decide_route` w/ `missing_order_id`): `293` drafted / **`267` correct** (`0.635714`, precision `0.911263`) / `26` wrong (`0.938095` safe)
  - `engine`: `295` drafted / `268` correct / `27` wrong (`0.935714` safe)
  - `runner` (`decide_route` + retrieval): `286` drafted / **`260` correct** / `26` wrong (`0.938095` safe)
- **`oos80`:** `3` leaks on `raw_pre`/`raw_post`/`bare` (`oos-general-08`, `oos-other_domain-19`, `oos-multi_intent-08`); `0` leaks on `engine`/`runner`.
- **`pos175` & `neg51`:** `pos175` `acc_46=0.765714`, `macro_f1_46=0.435000`, `esc34_acc=0.807692`, `sup11` `40/90` raw / `39/90` Engine / `35/90` Runner / `36/97` Gate; **known leaks:** `pos175 esc34` = **`4` raw/Engine** (`090` `order_history->track_order`, `099`, `102`, `107` `return_product_in_store->return_policy`) / **`3` Runner** (`099`, `102`, `107`); `neg51` = **`1` all surfaces** (`nonretail_ood_eval_019` `delivery_time` @ `0.710946`).
- **`bitext6690`:** `acc_46=0.996263`, `macro_f1_46=0.996313`, `sup11` `1600/1613`, `esc34_leaks=1`.
- **`ind36` / `old_sealed72` / `fresh34`:** `ind36` `6/11` raw/Engine (`5/11` Runner), `0` leaks, `mand_strict_escalate` `5/12` Engine/Runner (`4/12` raw); `old_sealed72` `7/24` raw (`6/24` Engine/bare, `5/24` Runner), `0` leaks, `mand_strict_escalate` `20/24` Engine/Runner (`19/24` raw); `fresh34` `4/11` answerable, **`1` leak all surfaces** (`v4p1-ood-08` `return_product_in_store->return_product` @ `0.85448`).

> [!IMPORTANT]
> **Original Fit2 itself fails safety gates** (`pos175 esc34`, `neg51`, `sa156 mand63`, `fresh34`, `bitext6690`). Its utility counts below are strictly **comparative minima**, never automatic acceptance.

---

## 4. Frozen Next-Stage Evaluation & Acceptance Protocol

1. **Comparative Minima vs. Original Fit2 (Non-Regression Floor Only):**
   - `final24` Runner `ans12_correct >= 10` (of `12`)
   - `sa156` Runner `sup34_correct >= 25` (of `34`)
   - `noise420` `macro_f1_12 >= 0.8573`
   - `noise420` Gate (`bare` / `decide_route`) `correct >= 267` (of `420`)
   - `noise420` Runner `correct >= 260` (of `420`)
2. **Mandatory Zero-Leak Safety Gates (All Surfaces):**
   - `0` unsafe draft leaks on `pos175 esc34`, `neg51`, `oos80`, `ind36`, `old_sealed72`, `fresh34`, `final24 active_unans8`, `bitext6690 esc34`, and `sa156 mand63` (excluding uninjected fixture `unc-return_policy-04`).
3. **Surface & Post-Privacy Parity Contract (Gap Closed):**
   - Prior harnesses (`evaluate_v4p1.py`, `evaluate_v5r2.py`) tested `raw_pre`, `raw_post`, `bare`, `engine`, and `runner` on raw text, while [verify_runtime_score_parity](file:///F:/Năm 3/SD/project/SupportIQ/pipeline/evaluation/classifier_acceptance_gate.py#L855) checked `ModelContainer` vs `GateSequenceClassifier` on 4 probe strings only. Production ticket intake ([service.py](file:///F:/Năm 3/SD/project/SupportIQ/apps/backend/tickets/service.py#L104) -> [privacy.py](file:///F:/Năm 3/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L49)) runs `pseudonymize()` *before* `ModelContainer.predict()`, altering `32/156` (`sa156`), `89/420` (`noise420`), `9/34` (`fresh34`), `3/72` (`old_sealed72`), `2/36` (`ind36`), `2/80` (`oos80`), and `1/24` (`final24`).
   - Next candidate evaluation MUST verify: (a) `verify_runtime_score_parity` passing under candidate `SUPPORTIQ_MODEL_DIR` + `SUPPORTIQ_CALIBRATION_MANIFEST_PATH` (`ModelContainer.load` with candidate `T` & `selective_rejector`), AND (b) **post-privacy** classifier + `Engine` stability on `pseudonymize(text, {})`-masked inputs alongside `raw_pre`/`raw_post`/`bare`/`engine`/`runner`.
4. **Provenance, Calibration & Leakage Gates:**
   - Candidate provenance `init_weights_sha256` must match the declared base checkpoint (`f695b1fe...` Original Fit2 for warm-start from Original Fit2, or `95a940b6...` Fit1 if explicitly re-fit from Fit1) with valid `46`-label bijection (`selective_calibration.v1`), `0` exact normalized overlap against `full_train_split.jsonl` + `full_cal_split.jsonl` on all frozen suites, and passing `CG.check_split_isolation_and_gold_contamination`.
5. **Independent Domain-Gate Requirement (Clean Holdout Boundary):**
   - Only **after** B passes data readiness (`PASS`) and A archives 1 bounded candidate fit, C authors and runs an independent unseen domain-gate suite probing return-policy vs. return-in-store channel boundaries plus cross-intent regression, zero-call offline (`_MockNoCallLLM` / `_OfflineValidSpyLLM`). No unseen holdout cases are shared with A beforehand.

---

## 5. Reproducible Verification Commands (Zero Fits, Zero Live LLM Calls)

```powershell
# Re-verify Original Fit2 / v5-r2 / v4p1 / Serving comparative matrix (0 live LLM calls)
.venv\Scripts\python.exe -B artifacts\evaluation\fit2_v5r2_independent_20261114\evaluate_v5r2.py

# Gate contract & runtime parity unit tests (verified: 60 passed, 1 deselected in 7.07s)
.venv\Scripts\python.exe -m pytest tests\unit\test_gate_contract_b.py tests\unit\test_model_runtime_parity_b.py tests\unit\test_task_c_evaluation_gates.py -q
```
