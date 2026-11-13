# Task C Bounded Live Oracle-Intent Provider Verification (`ff0e147`)

- **Generated At (UTC):** `2026-11-13T02:15:25.918467+00:00`
- **Candidate Runtime Commit:** `ff0e147d0181317d1550cec8df53420d8eddf771`
- **Verification Scope:** `oracle_intent_grounded_provider_component_verification`
- **Boundary:** Diagnostic component check using expected-intent oracle override and approved KB sources on 4 cases. NOT automatic end-to-end classifier coverage, and does NOT claim whole-system live acceptance.
- **Provider / Model / Prompt:** `google_ai_studio` / `gemini-3.1-flash-lite` / `grounded-v3` (`attempt_timeout=5.0s`, `budget=10.0s`)
- **Preflight Budget:** `0/8` | **Final Actual HTTP Requests:** **`8/8`** | **Rejected Before Network:** `0` | **Transport Retries:** `0`
- **Cases Executed:** `4` | **Draft Ready:** `2/4` | **Fallback:** `2/4` | **No-Auto-Send All:** `True`
- **Wall Elapsed Latency (All Cases incl. Failures):** p50=`9.9265s`, max=`10.1452s`
- **Token & Cost Status:** `incomplete_token_coverage` | `complete_token_coverage=False` | `attempts_missing_usage=6/8` | `observed_prompt=3446`, `observed_candidate=250`, `observed_thought=0`, `observed_reported_total=None` | `conditional_observed_list_price_usd=0.00033345` (`complete_cost_known=False`, NOT an invoice)

## Per-Case Diagnostic Results (Oracle Expected Intent + Approved KB)

| Case ID | Expected Intent | Serving Raw Pred (Conf) | Terminal Status | Failure | HTTP Calls / Attempts | Wall / LLM Rep (s) | Retrieved Docs |
| :--- | :--- | :--- | :--- | :--- | ---: | :--- | :--- |
| `final-case-02` | `return_product` | `return_policy` (0.7699) | `llm_unavailable` | `llm_timeout` | 2 / 2 | 9.93s / 9.91s | `POL-RET-002:2.0`, `POL-SHIP-004:1.0`, `POL-ORD-002:1.0` |
| `final-case-03` | `refund_policy` | `payment_issue` (0.4416) | `llm_unavailable` | `llm_timeout` | 2 / 2 | 10.15s / 10.11s | `POL-REFUND-001:1.0`, `POL-ORD-002:1.0`, `POL-RET-003:2.0` |
| `final-case-10` | `delivery_issue` | `delivery_issue` (0.2618) | `draft_ready` | `None` | 2 / 2 | 6.60s / 6.49s | `POL-SHIP-004:1.0`, `POL-ORD-001:1.0`, `POL-ORD-003:1.0` |
| `final-case-12` | `payment_issue` | `track_order` (0.5636) | `draft_ready` | `None` | 2 / 2 | 6.48s / 6.35s | `POL-PAY-001:1.0`, `POL-REFUND-007:1.0`, `POL-ORD-001:1.0` |

## Per-Attempt Telemetry

| Case ID | Attempt # | Status | HTTP | Stage | Exception Category | Latency (s) | Prompt / Cand / Total Tokens |
| :--- | ---: | :--- | ---: | :--- | :--- | ---: | :--- |
| `final-case-02` | 0 | `llm_unavailable` | `503` | `http_response` | `http_status` | 4.6577 | `None / None / None` |
| `final-case-02` | 1 | `llm_timeout` | `None` | `transport` | `timeout` | 5.0053 | `None / None / None` |
| `final-case-03` | 0 | `llm_timeout` | `None` | `transport` | `timeout` | 5.1053 | `None / None / None` |
| `final-case-03` | 1 | `llm_timeout` | `None` | `transport` | `timeout` | 5.0045 | `None / None / None` |
| `final-case-10` | 0 | `llm_timeout` | `None` | `transport` | `timeout` | 5.1047 | `None / None / None` |
| `final-case-10` | 1 | `success` | `200` | `complete` | `None` | 1.3891 | `1742 / 122 / 1864` |
| `final-case-12` | 0 | `llm_timeout` | `None` | `transport` | `timeout` | 5.0171 | `None / None / None` |
| `final-case-12` | 1 | `success` | `200` | `complete` | `None` | 1.3321 | `1704 / 128 / 1832` |
