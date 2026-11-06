# SupportIQ Phase 8 Benchmark Execution Report

**Execution Timestamp:** `2026-11-05T18:57:44.372213+00:00`  
**Benchmark Dataset:** `cases.jsonl` (156 cases, SHA-256: `C54C7EFCD2D36331...`)  
**Knowledge Base:** `approved_kb.v2.json` (17 documents, SHA-256: `AAA924C4B48DCD53...`)  
**Embedding Model:** `BAAI/bge-small-en-v1.5`  

## 1. Gap-to-Target Compliance Matrix

| ID | Metric | Target (ARCHITECTURE.md) | Historical | Measured (Current) | Gap | Status |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| NFR-01 | ML Intent Macro-F1 | ≥ 0.85 (85.0%) | 0.8520 (85.2%) | 0.9736 (97.4%) | +0.1236 | **PASS** |
| NFR-01 | ML Intent Accuracy | ≥ 0.85 (85.0%) | 0.8654 (86.5%) | 0.9679 (96.8%) | +0.1179 | **PASS** |
| NFR-01 | Expected Calibration Error (ECE) | ≤ 0.10 (10.0%) | 0.1420 (14.2%) | 0.1063 (10.6%) | +0.0063 | **FAIL** |
| NFR-01 | Brier Score | ≤ 0.15 | 0.1850 | 0.0169 | -0.1331 | **PASS** |
| NFR-02 | ML Robustness & OOD Detection | ≥ 0.90 (90.0%) | 0.6154 (61.5%) | 1.0000 (100.0%) | +0.1000 | **PASS** |
| NFR-03 | RAG Recall@3 | ≥ 0.80 (80.0%) | 0.4118 (41.2% mock) | 0.9706 (97.1%) | +0.1706 | **PASS** |
| NFR-03 | RAG Recall@1 | ≥ 0.70 (70.0%) | 0.2941 (29.4%) | 0.7941 (79.4%) | +0.0941 | **PASS** |
| NFR-03 | RAG Precision@3 | ≥ 0.30 (30.0%) | 0.1373 (13.7%) | 0.3235 (32.4%) | +0.0235 | **PASS** |
| NFR-03 | RAG Mean Reciprocal Rank (MRR) | ≥ 0.75 | 0.3529 | 0.8824 | +0.1324 | **PASS** |
| NFR-03 | RAG nDCG@3 | ≥ 0.80 | 0.3842 | 0.9055 | +0.1055 | **PASS** |
| NFR-03 | Invalid/Expired Warning Detection | = 100.0% | 100.0% | 100.0% | 0.0% | **PASS** |
| NFR-04 | Claim-Level Grounding Rate | ≥ 90.0% | N/A (unverified) | 100.0% | +10.0% | **PASS** |
| NFR-04 | Verifiable Citation Rate | = 100.0% | 100.0% | 100.0% | 0.0% | **PASS** |
| NFR-04 | Unsubstantiated Affirmation Rate | = 0.0% | 0.0% | 0.0% | 0.0% | **PASS** |
| NFR-08 | Retrieval Latency p50 | ≤ 100 ms | 12.4 ms (mock) | 21.6 ms | -78.4 ms | **PASS** |
| NFR-08 | Retrieval Latency p95 | ≤ 300 ms | 45.0 ms (mock) | 25.0 ms | -275.0 ms | **PASS** |

## 2. ML Intent Classification Performance

- **Accuracy:** `0.9679`
- **Macro-Precision:** `0.9721`
- **Macro-Recall:** `0.9758`
- **Macro-F1:** `0.9736`
- **Weighted-F1:** `0.9683`
- **Expected Calibration Error (ECE - 10 bins):** `0.1063`
- **Brier Score:** `0.0169`
- **OOD Detection Rate:** `1.0000`
- **False Acceptance Rate (FAR):** `0.0000`
- **False Rejection Rate (FRR):** `0.0175`
- **Escalation Rate:** `0.4038`
- **Abstention Rate:** `0.2821`

### Per-Slice Robustness Breakdown

| Slice / Category | Sample Count | Accuracy | Abstention Rate | Escalation Rate |
|:---|:---:|:---:|:---:|:---:|
| `answerable` | 24 | 0.9583 | 0.0417 | 0.0000 |
| `fault_injected` | 8 | 1.0000 | 0.0000 | 0.3750 |
| `supported` | 60 | 0.9833 | 0.0167 | 0.0833 |
| `tag:add_product` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:availability` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:availability_in_store` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:availability_online` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:cancel_order` | 11 | 1.0000 | 0.0000 | 0.0000 |
| `tag:change_account` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:change_order` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:close_account` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:core_intent` | 60 | 0.9833 | 0.0167 | 0.0833 |
| `tag:customer_service` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:damaged_delivery` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:delivery_issue` | 5 | 1.0000 | 0.0000 | 0.0000 |
| `tag:delivery_time` | 5 | 1.0000 | 0.0000 | 0.0000 |
| `tag:escalated_intent` | 34 | 1.0000 | 1.0000 | 1.0000 |
| `tag:exchange_product` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:exchange_product_in_store` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:fault` | 8 | 1.0000 | 0.0000 | 0.3750 |
| `tag:human_agent` | 5 | 1.0000 | 0.0000 | 1.0000 |
| `tag:insufficient_evidence` | 14 | 1.0000 | 0.0000 | 1.0000 |
| `tag:knowledge_base` | 24 | 0.9583 | 0.0417 | 0.0000 |
| `tag:missing_item` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:ood` | 3 | 0.0000 | 1.0000 | 1.0000 |
| `tag:open_account` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:order_history` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:pay` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:payment_issue` | 5 | 1.0000 | 0.0000 | 0.0000 |
| `tag:payment_methods` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:product_information` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:product_issue` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:recover_password` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:refund_policy` | 13 | 1.0000 | 0.0000 | 0.0000 |
| `tag:refund_status` | 5 | 1.0000 | 0.0000 | 0.0000 |
| `tag:remove_product` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:request_invoice` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:request_refund` | 5 | 1.0000 | 0.0000 | 0.0000 |
| `tag:request_right_to_rectification` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:return_policy` | 15 | 0.9333 | 0.0667 | 0.0000 |
| `tag:return_product` | 5 | 1.0000 | 0.0000 | 0.0000 |
| `tag:return_product_in_store` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:return_product_online` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:sales_period` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:shipping_costs` | 5 | 1.0000 | 0.0000 | 0.0000 |
| `tag:store_location` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:store_opening_hours` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:submit_feedback` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:submit_product_feedback` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:submit_product_idea` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:technical_issue` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:track_delivery` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:track_order` | 5 | 0.8000 | 0.2000 | 0.0000 |
| `tag:unanswerable` | 18 | 1.0000 | 0.2222 | 1.0000 |
| `tag:uncertainty` | 9 | 1.0000 | 0.1111 | 0.0000 |
| `tag:unsupported_intent` | 4 | 1.0000 | 1.0000 | 1.0000 |
| `tag:use_app` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `tag:wrong_item` | 1 | 1.0000 | 1.0000 | 1.0000 |
| `unanswerable` | 18 | 1.0000 | 0.2222 | 1.0000 |
| `uncertainty_and_faults` | 20 | 0.8500 | 0.2000 | 0.3000 |
| `unsupported` | 34 | 1.0000 | 1.0000 | 1.0000 |

## 3. RAG Semantic Retrieval Performance

- **Recall@1:** `0.7941` (79.4%)
- **Recall@3:** `0.9706` (97.1%) [Target: ≥ 0.80]
- **Recall@5:** `0.9706` (97.1%)
- **Recall@10:** `0.9706` (97.1%)
- **Precision@1:** `0.7941`
- **Precision@3:** `0.3235`
- **Mean Reciprocal Rank (MRR):** `0.8824`
- **nDCG@3:** `0.9055`
- **nDCG@5:** `0.9055`
- **No-Relevant-Document Detection:** `0.2377`
- **Latency p50:** `21.6 ms`
- **Latency p95:** `25.0 ms`

## 4. LLM Grounding & Draft Quality

- **Claim-Level Grounding Rate:** `100.0%` [Target: ≥ 90.0%]
- **Citation Precision:** `100.0%`
- **Citation Completeness:** `100.0%`
- **Citation Correctness:** `100.0%` [Target: 100.0%]
- **Hallucination Rate:** `0.0%`
- **Appropriate Abstention Rate:** `100.0%`
- **Appropriate Clarification Rate:** `100.0%`
- **Unsubstantiated Affirmations:** `0.0%` [Target: 0.0%]
