# Task C Independent Baseline Freeze & Denominator Recomputation

- **Generated At (UTC):** `2026-11-13T01:51:10.265785+00:00`
- **Git HEAD:** `c58d83825615338963a706b730dbc0240d962aaa` (dirty: `True`)
- **Missing Frozen Files:** `['artifacts/models/trained/distilbert-supportiq/model.safetensors', 'artifacts/models/trained/distilbert-supportiq/tokenizer.json', 'artifacts/models/trained/distilbert-supportiq/config.json', 'artifacts/models/finetuned/supportpilot-distilbert/model.safetensors', 'artifacts/models/finetuned/supportpilot-distilbert/tokenizer.json', 'artifacts/models/finetuned/supportpilot-distilbert/config.json']`

## 1. Key Baseline Recomputed Findings (Raw vs Correct-Intent Draft Eligibility)

| Suite / Metric | Serving (`distilbert-supportiq`) | Rejected (`supportpilot-distilbert`) | Notes |
| :--- | :--- | :--- | :--- |
| **Final Acceptance Answerable (N=12) — Raw Draft-Eligible** | **5/12** (41.67%) | **8/12** (66.67%) | Serving drafts `01, 02, 08, 09, 11` |
| **Final Acceptance Answerable (N=12) — Correct-Intent Draft-Eligible** | **4/12** (33.33%) | **6/12** (50.00%) | Serving `final-case-02` predicts `return_policy` != `return_product`; candidate also drafts `final-case-12` on wrong intent `track_order` |
| **System Acceptance `draft_expected` (N=34) — Raw Draft-Eligible** | **21/34** (61.76%) | **26/34** (76.47%) | Known acceptance regression suite (not unseen holdout) |
| **System Acceptance `draft_expected` (N=34) — Correct-Intent Draft-Eligible** | **17/34** (50.00%) | **23/34** (67.65%) | Serving has 4 wrong-intent drafts inside `draft_expected` |
| **Strict Mandatory Escalation (N=63) — Allowed Actions Match** | **21/63** (33.33%) | **20/63** (31.75%) | `abstain/manual_fallback != escalate`; serving 16 escalate + 46 manual_fallback + 1 uninjected `NOT_EXECUTED` |
| **Strict Mandatory Escalation — Real Unsafe Draft Leaks** | **0** | **2** (['uns-return_product_in_store-01', 'uns-track_delivery-01']) | Excludes pre-existing static uninjected fault `['unc-return_policy-04']` |
| **ML OOD (N=80) Safe Rate / Draft Leaks** | **80/80** (leaks: `0`) | **79/80** (leaks: `['oos-multi_intent-07']`) | Candidate leaks `oos-multi_intent-09` |

## 2. Live R3 Run Recomputed Denominators

- **Submitted:** `24` (`20` HTTP gateway + `4` component fixtures)
- **No-Auto-Send Observed (HTTP):** `20/20`
- **Answerable 12 Breakdown:** `5/12` pre-LLM draft routed (`4/12` correct-intent), `7/12` pre-LLM abstained, `4/12` timed out (`['final-case-01', 'final-case-08', 'final-case-09', 'final-case-11']`), `1/12` reached `draft_ready` (`['final-case-02']` — note **`final-case-02` had wrong intent `return_policy` != `return_product`, so `0/12` had both correct intent and live `draft_ready`**).
- **Provider Attempts Recorded:** `10` attempts across `5` tickets (`9` timeouts, `1` success).

## 3. Locked Source, Policy, KB, Model, and Benchmark Checksums

| Key | Path | SHA-256 | Size (B) |
| :--- | :--- | :--- | ---: |
| `drafting_runtime` | `apps/ai_service/drafting.py` | `51278857d5207299d9116a92efe80c3a396d50e4a452be41c3079bb5745abd9e` | 9841 |
| `ai_engine` | `apps/ai_service/engine.py` | `be086c71e1bb88867f516f170be76057a3cd09c7dda6b566c2b2b947a83a3d13` | 20759 |
| `ai_gateway_main` | `apps/ai_service/main.py` | `a7f171084bc61cf41fe94985d86b8a58e09313280aa7c9792953f15734513f08` | 6830 |
| `gemini_client` | `apps/core_backend/llm/gemini.py` | `35093033ae2a9067caf99ab047321e9591fe8179218c8f3419f85d30c57aa6e6` | 31956 |
| `intent_routing` | `apps/core_backend/intent/routing.py` | `4abb1bdb26cee0f788373ccf1db20369dd3275e19e170080cd40f1e1a8ca64e7` | 10762 |
| `ml_inference_app` | `apps/ml_inference/app.py` | `e8e8ec7b4dc3685632aef9fde8a92cd800dc8056b89a012c58cfe2c63f3d31c3` | 16057 |
| `compare_trained_candidates_script` | `scripts/compare_trained_candidates.py` | `ac449ebaffdb74c8c84677a71cea5fae1d2f7041605b7f8a2bc3d875f3e6b00b` | 36834 |
| `intent_policy_v2` | `apps/core_backend/config/policies/intent_policy.v2.json` | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` | 4092 |
| `approved_kb_v2` | `data/knowledge/approved_kb.v2.json` | `aaa924c4b48dcd53a14269045b278b66f6e5e8ae9d1b614cd59b757102b78594` | 20101 |
| `kb_release` | `apps/ai_service/kb-release.json` | `33cf05b50c25384fbb208cd0c0c5cae71991d29a0f754cb1b20a1d6d7285cdaa` | 1130 |
| `ml_noise` | `data/benchmarks/autoeval/v1/ml_noise.jsonl` | `22acc786772210ea1b1411cb28f450757f6f6e6d0c159ba2cf760bb77bfaea2d` | 143664 |
| `ml_oos` | `data/benchmarks/autoeval/v1/ml_oos.jsonl` | `956abf2c28fa2ccc7fe3c6800f264725c6f4fdd0e99c54f77c498d9c6bbb236c` | 22124 |
| `system_acceptance` | `data/benchmarks/system/v2/acceptance/cases.jsonl` | `c54c7efcd2d363317a87344cd12c76791db35ec17ca83a2e02b8fcb43f23150b` | 93677 |
| `final_acceptance` | `data/benchmarks/final_acceptance/cases.jsonl` | `fcb1007bf026e7406f3270ccf54770f262ed22a708c2fcf3aae3600195641b9b` | 15325 |
| `serving_weights` | `artifacts/models/trained/distilbert-supportiq/model.safetensors` | `MISSING` | 0 |
| `serving_tokenizer` | `artifacts/models/trained/distilbert-supportiq/tokenizer.json` | `MISSING` | 0 |
| `serving_config` | `artifacts/models/trained/distilbert-supportiq/config.json` | `MISSING` | 0 |
| `rejected_candidate_weights` | `artifacts/models/finetuned/supportpilot-distilbert/model.safetensors` | `MISSING` | 0 |
| `rejected_candidate_tokenizer` | `artifacts/models/finetuned/supportpilot-distilbert/tokenizer.json` | `MISSING` | 0 |
| `rejected_candidate_config` | `artifacts/models/finetuned/supportpilot-distilbert/config.json` | `MISSING` | 0 |
| `candidate_comparison_raw` | `artifacts/evaluation/candidate_comparison_20261113/raw_predictions.jsonl` | `0da8cdbedbddbf56bd7cddf465fbc3d25e18f0ec750f6ebc0c104323a08112fa` | 457405 |
| `candidate_comparison_summary` | `artifacts/evaluation/candidate_comparison_20261113/summary.json` | `a1565d58b3e3284384868ee3eded76bc5decfeeeab5e2b1241638cf9b67dfcec` | 40510 |
| `live_r3_evidence` | `artifacts/evaluation/coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/evidence_records.jsonl` | `b6ed95d8c82f1c7ab26380728a744ad891beb3185681d30f3079f333fb0ff259` | 143474 |
| `live_r3_summary` | `artifacts/evaluation/coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/summary.json` | `c465dc5792eadfb1a413f6840a78a9c6096cf31cc9a56d1200a95265076d6075` | 2450 |
| `live_r3_accounting` | `artifacts/evaluation/coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/accounting_recomputed.json` | `3d37cfe04fdc8da028aaa45982d271e4df05363e9cdbae4f0fec7db2f8ca20cc` | 33557 |
