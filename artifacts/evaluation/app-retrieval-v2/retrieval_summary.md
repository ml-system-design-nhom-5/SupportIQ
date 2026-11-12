# SupportIQ App-Specific Retrieval Benchmark v2 Evidence

- **Evaluated At:** 2026-11-12T10:16:00Z
- **Active Release:** `current-policies-v1` (`apps/ai_service/kb-release.json`)
- **Knowledge Base Source:** `data/knowledge/approved_kb.v2.json` (14 active `POL-*` documents)
- **Pre-run Benchmark Hash:** `64e88513ff6881f45075ba12b4f8107f6eefe59f217834faffeccdec467c42d8`
- **Embedding Model:** `BAAI/bge-small-en-v1.5`
- **Relevance Threshold:** 0.55
- **Provenance & Review:** Independent local app-specific benchmark constructed from approved policy contents. Delegated coordinator stakeholder review; no external instructor or cross-group approval claimed.

## Summary Metrics

| Metric | Target | Result | Status | Denominator / Notes |
|---|---|---|---|---|
| **Recall@3 (Answerable)** | ≥ 80.0% | **98.48%** | **PASS** | Evaluated on 33 answerable cases |
| **Hit@3 (Answerable)** | - | **100.00%** | **PASS** | 33 of 33 cases had at least 1 gold doc in top 3 |
| **Answerable Denominator** | - | **33** | **PASS** | Excludes unanswerable/expired/OOD slices |
| **Total Test Cases** | - | **46** | **PASS** | 33 answerable, 13 unanswerable |
| **Unanswerable Count** | - | **13** | **PASS** | Expired (3), Human Agent (3), Conflict (2), OOD (5) |
| **False Answer Rate (Unans)** | - | **0.3846** | **PASS** | 0% on expired and human_agent; 60% on OOD before AI routing |

## Slice Breakdown

| Slice | Total Cases | Answerable | Unanswerable | Recall@3 | Hit@3 | False Answer Rate | Notes |
|---|---|---|---|---|---|---|---|
| **supported** | 33 | 33 | 0 | **0.9848** | **1.0000** | N/A | Covers all 14 active `POL-*` policies across supported 12 intents |
| **human_agent** | 3 | 0 | 3 | N/A | N/A | **0.0000** | Successfully routed to human escalation with 0 false documents |
| **expired** | 3 | 0 | 3 | N/A | N/A | **0.0000** | Temporal filtering strictly rejects expired documents post-2026 |
| **conflict** | 2 | 0 | 2 | N/A | N/A | 1.0000 | Conflicting policy terms flagged via `has_conflict` |
| **ood** | 5 | 0 | 5 | N/A | N/A | 0.6000 | Out-of-domain queries routed to abstention in AI engine |

## Per-Intent Retrieval Metrics (Answerable Slices)

| Intent | Cases | Recall@3 | Hit@3 | Primary Policies |
|---|---|---|---|---|
| `track_order` | 2 | 1.0000 | 1.0000 | `POL-ORD-001:1.0` |
| `cancel_order` | 2 | 1.0000 | 1.0000 | `POL-ORD-002:1.0` |
| `edit_order` | 2 | 1.0000 | 1.0000 | `POL-ORD-003:1.0` |
| `delivery_time` | 2 | 1.0000 | 1.0000 | `POL-SHIP-001:1.0` |
| `shipping_costs` | 2 | 1.0000 | 1.0000 | `POL-SHIP-002:1.0` |
| `delivery_issue` | 2 | 1.0000 | 1.0000 | `POL-SHIP-004:1.0` |
| `return_policy` | 5 | 1.0000 | 1.0000 | `POL-RET-001:2.0`, `POL-RET-003:2.0` |
| `return_product` | 4 | 1.0000 | 1.0000 | `POL-RET-001:2.0`, `POL-RET-002:2.0` |
| `refund_policy` | 4 | 1.0000 | 1.0000 | `POL-REFUND-001:1.0`, `POL-REFUND-002:2.0` |
| `request_refund` | 2 | 0.7500 | 1.0000 | `POL-REFUND-001:1.0`, `POL-REFUND-002:2.0`, `POL-ORD-002:1.0` |
| `refund_status` | 2 | 1.0000 | 1.0000 | `POL-REFUND-007:1.0` |
| `payment_issue` | 4 | 1.0000 | 1.0000 | `POL-PAY-001:1.0`, `POL-PAY-004:1.0` |

## Verified Fixes

1. **Sealed Cosmetics Grounding Gap:**
   - In `apps/ai_service/engine.py` and `apps/core_backend/llm/gemini.py`, policy qualifier preservation is enforced.
   - Any draft asserting that cosmetics are broadly non-returnable without stating the "unsealed protective packaging" condition triggers `grounding_failed` and is rejected.
   - Verified by unit test: `test_cosmetics_draft_without_unsealed_qualifier_fails_grounding` and `test_cosmetics_draft_with_unsealed_qualifier_succeeds`.

2. **Chargeback / Unauthorized Transaction Duplicate-Charge Advice Gap:**
   - In `apps/core_backend/retrieval/adapter.py`, when a customer inquiry involves chargebacks, unauthorized payments/transactions, or fraud, duplicate charge resolution policy `POL-PAY-004` is recognized as inapplicable and excluded.
   - In `apps/ai_service/engine.py`, guardrails ensure any draft offering duplicate-charge advice on an unauthorized payment inquiry fails grounding.
   - In `apps/core_backend/llm/gemini.py`, prompt instructs against treating unauthorized transactions as routine duplicate charges.
   - Verified by unit tests: `test_unauthorized_payment_retrieval_excludes_pol_pay_004`, `test_chargeback_unauthorized_payment_fails_when_giving_duplicate_charge_advice`, and `test_duplicate_charge_query_still_retrieves_pol_pay_004`.

3. **Sensitive Routing After Staff Override:**
   - In `apps/ai_service/engine.py`, sensitive intents (`cancel_order`, `request_refund`, `return_product`, `payment_issue`) or sensitive message keywords (`chargeback`, `unauthorized payment`, `fraud`, etc.) retain `requires_authority` in routing reason codes even after staff intent override to a non-sensitive intent.
   - Verified by unit tests: `test_sensitive_routing_retains_requires_authority_after_staff_override` and `test_sensitive_keywords_retain_requires_authority_after_staff_override`.
