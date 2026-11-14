# Guard & Fault Corrections Verification Report (`0` Live Calls)

- **Generated UTC:** `2026-11-13T09:33:43.235088Z`
- **Target Worktree:** `C:\Users\PC\.gemini\antigravity-cli\brain\bfd11621-fe3b-48af-939d-9f67699ebca6\scratch\combined_ab_verify` (`git 9f2e9d15836a235d6ddc0665e5a536b6d96b5840`)
- **Loaded `apps` Package:** `C:\Users\PC\.gemini\antigravity-cli\brain\bfd11621-fe3b-48af-939d-9f67699ebca6\scratch\combined_ab_verify\apps\__init__.py`
- **Surface Mode:** `all`
- **Historic `8f7d542` Fault Evidence Intact:** `True`

## Fault-Boundary Re-Execution (`ZeroBudgetTransport` max=0)

- **Live HTTP Attempted:** `0` / `0`
- **PG Temporary Schema Cleaned:** `fault_chk_201d3cdf90` (`absent=True`)

| Case ID | Fault | Surface / Scenario | Raw Outcome | Mapped | Privacy 404 | Strict Must-Escalate | Strict Reason | `no_draft` | Verdict |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `unc-track_order-03` | `ml_timeout` | `backend_pg_gateway` / `backend_pg_analysis_read_timeout` | `unavailable` | `manual_fallback` | `False` | `False` | `True` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-03` | `ml_timeout` | `backend_pg_gateway` / `backend_pg_model_timeout_error` | `unavailable` | `manual_fallback` | `False` | `False` | `True` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-return_policy-04` | `encoder_failure` | `backend_pg_gateway` / `backend_pg_encoder_runtime_failure` | `escalation_recommended` | `escalate` | `False` | `True` | `True` | `True` | `STRICT_PASS` |
| `unc-return_policy-04` | `encoder_failure` | `backend_pg_gateway` / `backend_pg_encoder_unavailable` | `abstained` | `manual_fallback` | `False` | `False` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-05` | `commerce_unauthorized` | `backend_pg_gateway` / `backend_pg_explicit_unauthorized_order` | `urn:supportiq:problem:not-found` | `http_404_denied` | `True` | `False` | `False` | `True` | `INTAKE_DENIAL_404_MISMATCH` |
| `unc-track_order-05` | `commerce_unauthorized` | `backend_pg_gateway` / `backend_pg_text_only_unauthorized_order` | `escalation_recommended` | `escalate` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-03` | `ml_timeout` | `pipeline_runner` / `pipeline_runner_ml_read_timeout` | `manual_fallback` | `manual_fallback` | `False` | `False` | `True` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-return_policy-04` | `encoder_failure` | `pipeline_runner` / `pipeline_runner_encoder_runtime_failure` | `escalate` | `escalate` | `False` | `True` | `True` | `True` | `STRICT_PASS` |
| `unc-return_policy-04` | `encoder_failure` | `pipeline_runner` / `pipeline_runner_encoder_unavailable` | `escalate` | `escalate` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-05` | `commerce_unauthorized` | `pipeline_runner` / `pipeline_runner_real_classifier_commerce_unauthorized` | `escalate` | `escalate` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-05` | `commerce_unauthorized` | `pipeline_runner` / `pipeline_runner_track_order_commerce_unauthorized` | `escalate` | `escalate` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-04` | `ml_error` | `backend_pg_gateway` / `backend_pg_ml_runtime_error_503` | `unavailable` | `manual_fallback` | `False` | `True` | `True` | `True` | `STRICT_PASS` |
| `unc-return_policy-03` | `encoder_unavailable` | `backend_pg_gateway` / `backend_pg_companion_encoder_unavailable` | `abstained` | `manual_fallback` | `False` | `True` | `True` | `True` | `STRICT_PASS` |
| `unc-track_order-06` | `commerce_not_found` | `backend_pg_gateway` / `backend_pg_explicit_not_found_order` | `urn:supportiq:problem:not-found` | `http_404_denied` | `False` | `True` | `False` | `True` | `INTAKE_DENIAL_404_MISMATCH` |
| `unc-track_order-06` | `commerce_not_found` | `backend_pg_gateway` / `backend_pg_text_only_not_found_order` | `abstained` | `manual_fallback` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-return_policy-03` | `encoder_unavailable` | `pipeline_runner` / `pipeline_runner_companion_encoder_unavailable` | `escalate` | `escalate` | `False` | `True` | `True` | `True` | `STRICT_PASS` |
| `unc-track_order-04` | `ml_error` | `pipeline_runner` / `pipeline_runner_ml_error_503` | `manual_fallback` | `manual_fallback` | `False` | `True` | `True` | `True` | `STRICT_PASS` |
| `unc-track_order-06` | `commerce_not_found` | `pipeline_runner` / `pipeline_runner_commerce_not_found_frozen_empty_slots` | `clarify` | `clarify` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-06` | `commerce_not_found` | `pipeline_runner` / `pipeline_runner_commerce_not_found_explicit_slot` | `escalate` | `escalate` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-refund_policy-01` | `llm_timeout` | `pipeline_runner` / `pipeline_runner_llm_timeout_offline_spy` | `manual_fallback` | `manual_fallback` | `False` | `True` | `True` | `True` | `STRICT_PASS` |
| `unc-cancel_order-03` | `llm_invalid_citations` | `pipeline_runner` / `pipeline_runner_llm_invalid_citations_offline_spy` | `manual_fallback` | `manual_fallback` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-refund_policy-01` | `llm_timeout` | `ai_service_engine_offline_spy` / `engine_llm_timeout` | `llm_unavailable` | `manual_fallback` | `False` | `True` | `True` | `True` | `STRICT_PASS` |
| `unc-cancel_order-03` | `llm_invalid_citations` | `ai_service_engine_offline_spy` / `engine_llm_invalid_citations` | `llm_unavailable` | `manual_fallback` | `False` | `True` | `False` | `True` | `SAFE_FALLBACK_MISMATCH` |

## Guard Priority, Negation & `GeminiDraftClient` Boundary Probes

| Probe Tag | Expectation | Initial | Final | Queue / Team | Reason Codes | `llm_called` |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| `human_fraud_priority` | `must_escalate_manager` | `clarify` | `escalate` | `manager` / `payments_support` | `low_confidence, human_agent_requested, requires_authority` | `False` |
| `human_fraud_return` | `must_escalate_manager` | `clarify` | `escalate` | `manager` / `payments_support` | `low_confidence, human_agent_requested, requires_authority` | `False` |
| `clarify_low_conf_fraud` | `must_escalate` | `clarify` | `escalate` | `manager` / `order_support` | `low_confidence, low_margin, human_agent_requested, requires_authority` | `False` |
| `clarify_missing_oid_tax` | `must_not_draft` | `clarify` | `manual_fallback` | `standard` / `returns_support` | `low_confidence, out_of_scope_intent` | `False` |
| `overlapping_scope_conflict` | `must_escalate_over_abstain` | `retrieve_draft` | `escalate` | `standard` / `delivery_support` | `insufficient_evidence, no_valid_document` | `False` |
| `negated_human` | `should_not_false_escalate_human` | `retrieve_draft` | `retrieve_draft` | `standard` / `returns_support` | `-` | `True` |
| `negated_dispute` | `should_not_false_escalate_dispute` | `retrieve_draft` | `retrieve_draft` | `manager` / `payments_support` | `requires_authority` | `True` |
| `negated_exception` | `should_not_false_escalate_exception` | `clarify` | `clarify` | `standard` / `payments_support` | `low_confidence, low_margin` | `False` |
| `draft_verb_policy` | `should_draft_supported` | `retrieve_draft` | `retrieve_draft` | `standard` / `returns_support` | `-` | `True` |
| `expired_product_policy` | `should_draft_supported` | `retrieve_draft` | `retrieve_draft` | `standard` / `returns_support` | `-` | `True` |
| `purchase_year_current_policy` | `should_draft_supported` | `retrieve_draft` | `retrieve_draft` | `standard` / `returns_support` | `-` | `True` |
| `courier_pickup_ordinary` | `should_draft_supported` | `retrieve_draft` | `retrieve_draft` | `standard` / `returns_support` | `-` | `True` |
| `privacy_policy_ordinary` | `should_draft_supported` | `retrieve_draft` | `retrieve_draft` | `standard` / `returns_support` | `-` | `True` |

### `final_acceptance` `product_12_answerable` Ownership Check

- `ticket_customer_id=cust_1`: `raw_draft=2/12`, `correct_intent_draft=2/12`, `commerce_unauthorized_count=9`
- `ticket_customer_id=demo-customer`: `raw_draft=5/12`, `correct_intent_draft=4/12`, `commerce_unauthorized_count=0`

### `GeminiDraftClient` & Post-Generation Boundary Checks

- **Real `GeminiDraftClient` valid JSON mock:** `pipeline_action=retrieve_draft`, `pipeline_has_draft=True`, `engine_status=draft_ready`, `confidence=0.9705943465232849`, `margin=0.9655377864837646`, `mock_http_calls=9`
- **Default `GeminiDraftClient` invalid citation check:** raised `llm_invalid_citations`
- **Injected unraised `unknown_citation`:** `pipeline_action=manual_fallback` (`draft_present=False`, reasons=`['grounding_failed']`), `engine_status=llm_unavailable` (`draft_present=False`, reasons=`['grounding_failed']`)
- **Injected unraised `uncited_long_claim`:** `pipeline_action=manual_fallback` (`draft_present=False`, reasons=`['grounding_failed']`), `engine_status=llm_unavailable` (`draft_present=False`, reasons=`['grounding_failed']`)
- **Injected unraised `placeholder_leak`:** `pipeline_action=manual_fallback` (`draft_present=False`, reasons=`['llm_invalid_output']`), `engine_status=llm_unavailable` (`draft_present=False`, reasons=`['llm_invalid_output']`)

