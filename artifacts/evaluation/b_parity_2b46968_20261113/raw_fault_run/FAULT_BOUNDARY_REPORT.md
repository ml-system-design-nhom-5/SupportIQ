# Fault Boundary Execution Report (`0` Live LLM Requests)

- **Generated UTC:** `2026-11-13T11:41:04.778837+00:00`
- **Git Commit:** `018cdcacee27533dae6bf3d6f9e5c988ea1f228d`
- **Live Provider Requests Attempted:** `0` / `0`
- **PostgreSQL Temporary Schema:** `fault_chk_29c13e7fef` (cleanup verified: `True`)

## Primary Target Faults (Previously `NOT_EXECUTED`)

| Case ID | Fault | Surface / Scenario | Raw Outcome | Mapped Action | Reason Codes | `llm_calls` | `customer_reply_is_none` | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `unc-track_order-03` | `ml_timeout` | `backend_pg_gateway` / `backend_pg_analysis_read_timeout` | `unavailable` | `manual_fallback` | `ai_service_unavailable, ml_timeout` | `0` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-03` | `ml_timeout` | `backend_pg_gateway` / `backend_pg_model_timeout_error` | `unavailable` | `manual_fallback` | `ai_service_unavailable, ml_timeout` | `0` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-return_policy-04` | `encoder_failure` | `backend_pg_gateway` / `backend_pg_encoder_runtime_failure` | `escalation_recommended` | `escalate` | `encoder_failed, encoder_failure, insufficient_evidence` | `0` | `True` | `STRICT_PASS` |
| `unc-return_policy-04` | `encoder_failure` | `backend_pg_gateway` / `backend_pg_encoder_unavailable` | `escalation_recommended` | `escalate` | `encoder_unavailable, insufficient_evidence` | `0` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-05` | `commerce_unauthorized` | `backend_pg_gateway` / `backend_pg_explicit_unauthorized_order` | `urn:supportiq:problem:not-found` | `http_404_denied` | `http_404, urn:supportiq:problem:not-found` | `0` | `None` | `INTAKE_DENIAL_404_MISMATCH` |
| `unc-track_order-05` | `commerce_unauthorized` | `backend_pg_gateway` / `backend_pg_text_only_unauthorized_order` | `escalation_recommended` | `escalate` | `out_of_scope_intent` | `0` | `True` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-03` | `ml_timeout` | `pipeline_runner` / `pipeline_runner_ml_read_timeout` | `manual_fallback` | `manual_fallback` | `ml_unavailable, ml_timeout` | `0` | `None` | `SAFE_FALLBACK_MISMATCH` |
| `unc-return_policy-04` | `encoder_failure` | `pipeline_runner` / `pipeline_runner_encoder_runtime_failure` | `escalate` | `escalate` | `insufficient_evidence, encoder_failure, encoder_failed` | `0` | `None` | `STRICT_PASS` |
| `unc-return_policy-04` | `encoder_failure` | `pipeline_runner` / `pipeline_runner_encoder_unavailable` | `escalate` | `escalate` | `insufficient_evidence, encoder_unavailable` | `0` | `None` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-05` | `commerce_unauthorized` | `pipeline_runner` / `pipeline_runner_real_classifier_commerce_unauthorized` | `escalate` | `escalate` | `recognized_outside_product_scope` | `0` | `None` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-05` | `commerce_unauthorized` | `pipeline_runner` / `pipeline_runner_track_order_commerce_unauthorized` | `escalate` | `escalate` | `commerce_unauthorized_customer` | `0` | `None` | `SAFE_FALLBACK_MISMATCH` |

## Companion Faults (Acceptance v2 Fault Matrix)

| Case ID | Fault | Surface / Scenario | Raw Outcome | Mapped Action | Reason Codes | `llm_calls` | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `unc-track_order-04` | `ml_error` | `backend_pg_gateway` / `backend_pg_ml_runtime_error_503` | `unavailable` | `manual_fallback` | `ai_service_unavailable, ml_error` | `0` | `STRICT_PASS` |
| `unc-return_policy-03` | `encoder_unavailable` | `backend_pg_gateway` / `backend_pg_companion_encoder_unavailable` | `escalation_recommended` | `escalate` | `encoder_unavailable, insufficient_evidence` | `0` | `STRICT_PASS` |
| `unc-track_order-06` | `commerce_not_found` | `backend_pg_gateway` / `backend_pg_explicit_not_found_order` | `urn:supportiq:problem:not-found` | `http_404_denied` | `http_404, urn:supportiq:problem:not-found` | `0` | `INTAKE_DENIAL_404_MISMATCH` |
| `unc-track_order-06` | `commerce_not_found` | `backend_pg_gateway` / `backend_pg_text_only_not_found_order` | `abstained` | `manual_fallback` | `low_confidence, out_of_scope_intent` | `0` | `SAFE_FALLBACK_MISMATCH` |
| `unc-return_policy-03` | `encoder_unavailable` | `pipeline_runner` / `pipeline_runner_companion_encoder_unavailable` | `escalate` | `escalate` | `insufficient_evidence, encoder_unavailable` | `0` | `STRICT_PASS` |
| `unc-track_order-04` | `ml_error` | `pipeline_runner` / `pipeline_runner_ml_error_503` | `manual_fallback` | `manual_fallback` | `ml_unavailable, ml_error` | `0` | `STRICT_PASS` |
| `unc-track_order-06` | `commerce_not_found` | `pipeline_runner` / `pipeline_runner_commerce_not_found_frozen_empty_slots` | `clarify` | `clarify` | `missing_order_id` | `0` | `SAFE_FALLBACK_MISMATCH` |
| `unc-track_order-06` | `commerce_not_found` | `pipeline_runner` / `pipeline_runner_commerce_not_found_explicit_slot` | `escalate` | `escalate` | `commerce_order_not_found` | `0` | `SAFE_FALLBACK_MISMATCH` |
| `unc-refund_policy-01` | `llm_timeout` | `pipeline_runner` / `pipeline_runner_llm_timeout_offline_spy` | `manual_fallback` | `manual_fallback` | `llm_timeout` | `1` | `STRICT_PASS` |
| `unc-cancel_order-03` | `llm_invalid_citations` | `pipeline_runner` / `pipeline_runner_llm_invalid_citations_offline_spy` | `manual_fallback` | `manual_fallback` | `grounding_failed` | `1` | `SAFE_FALLBACK_MISMATCH` |
| `unc-refund_policy-01` | `llm_timeout` | `ai_service_engine_offline_spy` / `engine_llm_timeout` | `llm_unavailable` | `manual_fallback` | `llm_timeout, llm_unavailable` | `1` | `STRICT_PASS` |
| `unc-cancel_order-03` | `llm_invalid_citations` | `ai_service_engine_offline_spy` / `engine_llm_invalid_citations` | `llm_unavailable` | `manual_fallback` | `grounding_failed` | `1` | `SAFE_FALLBACK_MISMATCH` |

## Concrete Cross-Architecture Findings & Reproductions

- **unc-track_order-03 (`ml_timeout`) — Fails closed safely as manual fallback, but misses strict must_escalate=true and reason 'ml_timeout':** Backend worker HTTP ReadTimeout -> draft_status=unavailable reasons=['ai_service_unavailable', 'ml_timeout']; in-process ModelContainer TimeoutError -> http/fallback reasons=['ai_service_unavailable', 'ml_timeout']; PipelineRunner ReadTimeout -> action=manual_fallback reasons=['ml_unavailable', 'ml_timeout'] (0 LLM calls, no draft leaked).
- **unc-return_policy-04 (`encoder_failure`) — Backend abstains as generic no_valid_document; PipelineRunner escalates without 'encoder_failure' code:** Backend runtime encode_queries RuntimeError -> draft_status=escalation_recommended reasons=['encoder_failed', 'encoder_failure', 'insufficient_evidence'] (mapped=escalate, strict must_escalate mismatch). PipelineRunner runtime encode_queries RuntimeError -> action=escalate reasons=['insufficient_evidence', 'encoder_failure', 'encoder_failed'] (RetrievalAdapter strips search_policies ['encoder_failed'] down to status='error'; encoder=None gives ['insufficient_evidence', 'encoder_unavailable']).
- **unc-track_order-05 (`commerce_unauthorized`) — Explicit order_id returns HTTP 404 denial; text-only drops order link without commerce auth code; PipelineRunner emits 'commerce_unauthorized_customer':** Backend explicit ORD-1002 by demo-customer -> HTTP 404 (urn:supportiq:problem:not-found, 0 tickets). Backend text-only 'Track order ORD-1002 for customer cust_1' -> ticket created with order_id=None, predicted_intent=customer_service, draft_status=escalation_recommended, reasons=['out_of_scope_intent']. PipelineRunner real classifier -> action=escalate reasons=['recognized_outside_product_scope']; PipelineRunner track_order -> action=escalate reasons=['commerce_unauthorized_customer'].
