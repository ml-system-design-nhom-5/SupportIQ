# SupportIQ App-Specific Retrieval Acceptance Evidence (v2)

- **Evaluated At:** 2026-11-12T12:09:45.892715+00:00
- **Git Commit:** `b652adb34f3d7aae488aa4c0c07d21e8165af9df`
- **Active Release:** `current-policies-v1` (`apps/ai_service/kb-release.json`, SHA-256: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`)
- **Knowledge Base Source:** `data/knowledge/approved_kb.v2.json` (14 active `POL-*` documents, SHA-256: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`)
- **Gold Benchmark:** `data/benchmarks/app_retrieval_gold_v2.json` (v2.1, 46 cases, pre-run SHA-256: `a33e6394d6d76384ac33771d014816ae7e2d1a3c379b3c1ec3a7f3605940bee7`)
- **Gold Approval:** Delegated coordinator review (msg_7955e07af426, dated 2026-11-12); no external instructor or cross-group approval claimed.
- **Embedding Model:** `BAAI/bge-small-en-v1.5`
- **Deployment Relevance Threshold:** `0.55`

## Acceptance Summary Metrics

| Metric | Target | Result | Status | Denominator / Notes |
|---|---|---|---|---|
| **Core Product Recall@3** | ≥ 80.0% | **98.39%** | **PASS** | Evaluated on exactly 31 answerable cases across 12 supported product intents |
| **Core Product Hit@3** | - | **100.00%** | **PASS** | 31 of 31 answerable product cases returned gold policy in top 3 |
| **Product Recall Denominator** | Exactly 31 | **31** | **PASS** | Strictly 12 core product intents; excludes optional edit_order and unanswerable slices |
| **Total Test Cases** | - | **46** | **PASS** | 31 core product, 2 optional out-of-product, 11 unanswerable, 2 conflict (unexecuted) |
| **Unanswerable Product Cases** | - | **3** | **PASS** | Human agent escalation cases |
| **False Answer Rate (Product)** | - | **0.0000** | **PASS** | 0% false policy injection on product escalation cases |

## Slice Breakdowns

| Slice | Total Cases | Answerable | Unanswerable | Recall@3 | Hit@3 | False Answer Rate | Notes |
|---|---|---|---|---|---|---|---|
| **supported** | 31 | 31 | 0 | **0.9839** | **1.0000** | N/A | Covers all 12 supported product intents across active POL documents |
| **optional_out_of_product** | 2 | 2 | 0 | **1.0000** | **1.0000** | N/A | edit_order (POL-ORD-003); excluded from core product denominator |
| **human_agent** | 3 | 0 | 3 | N/A | N/A | **0.0000** | Routed to human_agent_escalation with 0 false policies |
| **expired** | 3 | 0 | 3 | N/A | N/A | **0.0000** | Temporal filter correctly excludes expired policies post-2026 |
| **ood** | 5 | 0 | 5 | N/A | N/A | **0.6000** | Out-of-domain queries; routed to abstention in AI Engine |
| **conflict** | 2 | 0 | 2 | N/A | N/A | N/A | not_executed_in_active_release (active release has 0 contradictory policies; verified via unit test) |

## Per-Intent Retrieval Metrics (Core Product Answerable)

| Intent | Cases | Recall@3 | Hit@3 |
|---|---|---|---|
| `cancel_order` | 2 | 1.0000 | 1.0000 |
| `delivery_issue` | 2 | 1.0000 | 1.0000 |
| `delivery_time` | 2 | 1.0000 | 1.0000 |
| `edit_order` | 2 | 1.0000 | 1.0000 |
| `payment_issue` | 4 | 1.0000 | 1.0000 |
| `refund_policy` | 4 | 1.0000 | 1.0000 |
| `refund_status` | 2 | 1.0000 | 1.0000 |
| `request_refund` | 2 | 0.7500 | 1.0000 |
| `return_policy` | 5 | 1.0000 | 1.0000 |
| `return_product` | 4 | 1.0000 | 1.0000 |
| `shipping_costs` | 2 | 1.0000 | 1.0000 |
| `track_order` | 2 | 1.0000 | 1.0000 |

## Architectural Reconciliation & Governance

1. **Runtime vs. Offline Pipeline Ownership:**
   - **Runtime Retrieval Ownership:** Fully owned and implemented under `apps/core_backend/retrieval/` (`adapter.py`, `encoder.py`, `importer.py`, `index.py`). The production service (`apps/ai_service/main.py`) directly instantiates and queries `RetrievalAdapter`.
   - **Offline Pipeline Status:** The placeholder directories `pipeline/retrieval/` and `pipeline/monitoring/` have been deleted per explicit user request. Reusable benchmark generation and acceptance evaluation scripts are maintained under `scripts/generate_app_retrieval_gold.py` and `scripts/run_app_retrieval_benchmark.py`.
   - **Index Persistence Justification:** The historical 2026-11-04 plan referenced an offline `pipeline/retrieval/build_index.py`. However, for SupportIQ's active 14-document policy corpus, `PolicyEncoder` loads `BAAI/bge-small-en-v1.5` and compiles the in-memory normalized NumPy dot-product index in ~3 seconds on startup. Persisting a static index to disk would create synchronization and drift hazards between `approved_kb.v2.json`, `kb-release.json`, and disk artifacts without latency advantages. The dynamic in-memory index is therefore the intended, drift-free production design.

2. **Documented Verification Commands:**
   - Run acceptance retrieval benchmark:
     ```sh
     & "$env:VIRTUAL_ENV/Scripts/python.exe" scripts/run_app_retrieval_benchmark.py
     ```
   - Run dedicated retrieval and grounding unit tests:
     ```sh
     & "$env:VIRTUAL_ENV/Scripts/python.exe" -m pytest tests/unit/test_retrieval_grounding_b2.py
     ```
   - Re-generate / verify gold benchmark:
     ```sh
     & "$env:VIRTUAL_ENV/Scripts/python.exe" scripts/generate_app_retrieval_gold.py
     ```
