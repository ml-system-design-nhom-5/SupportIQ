# `order_context` Canonical 10-Field Contract Parity Audit (Worker A)

- **Date:** 2026-11-15
- **Branch:** `minh`
- **Baseline Parent Commit:** `25700c100f1053b4ed5adf599972a01e1273de79` (Worker C real-NER verification)
- **Scope:** Trace and resolve the reported `order_context` 6-vs-10 canonical allowlist mismatch across backend fact creation, egress validation, `SuggestionRequest`, `Engine.draft`, grounding/citations/prompt consumers, and `PipelineRunner` comparison. Zero training, zero calibration/threshold edits, zero paid LLM calls, zero service restarts.

## 1. End-to-End Trace & Confirmed Root Cause

1. **Canonical Contract (`apps/core_backend/llm/gemini.py:418-430, 514-550`):**
   - `ORDER_CONTEXT_ALLOWED_FIELDS` / `ORDER_CONTEXT_ALLOWED_SET` already defines all 10 canonical fields: `order_status`, `placed_at`, `order_total`, `shipping_cost`, `shipment_status`, `estimated_delivery_at`, `delivered_at`, `refund_status`, `refund_amount`, `refund_requested_at`.
2. **Backend Fact Creation — CONFIRMED 6-vs-10 Mismatch (`apps/backend/tickets/service.py:39-44` before fix, `request_payload` at `:144`):**
   - `order_context(order)` previously extracted only 6 fields (`order_status`, `order_total`, `shipping_cost`, `shipment.shipment_status`, `refund.refund_status`, `refund.refund_amount`) and silently dropped the 4 canonical timestamp fields (`placed_at`, `estimated_delivery_at`, `delivered_at`, `refund_requested_at`), even though `apps/backend/seed.py:31-33` and `apps/backend/main.py:181-184` already store `placed_at` on every order and `shipment.delivered_at` on delivered seeded orders.
3. **Backend Egress Gate & Worker Hydration (`apps/backend/tickets/privacy.py:285-308`, `apps/backend/tickets/jobs.py:336-352`):**
   - Already enforced canonical 10-field `ORDER_CONTEXT_ALLOWED_SET` + `extract_order_facts(..., strict=True)` in `_validate_order_context`, and dynamically hydrated cited `fields` from `payload["order_context"]` in `SuggestionWorker.process`.
4. **AI Service Request & Engine Validation / Grounding (`apps/ai_service/main.py:45-66`, `apps/ai_service/engine.py:216-239, 324-333`):**
   - Already resolved in commit `013d1c4`: `SuggestionRequest.check_context` validates `<= ORDER_CONTEXT_ALLOWED_SET` with `extract_order_facts(..., strict=True)`. `Engine.draft` filters via `ORDER_CONTEXT_ALLOWED_SET`, preserves field ordering via `ORDER_CONTEXT_ALLOWED_FIELDS`, builds `authoritative_sources` (`build_grounded_sources(..., include_order_identifiers=True)`), forwards `validated_order_input` to `self.llm.generate` (`prepare_llm_input`, `apps/core_backend/llm/gemini.py:655-667`), and emits all supplied canonical fields in `citations[]["fields"]`.
5. **Comparison with `PipelineRunner` (`apps/core_backend/orchestration/pipeline_runner.py:103, 149, 158`):**
   - `PipelineRunner.run` reads raw `CommerceAdapter.lookup_order` records (`data/knowledge/mock_orders.json`, separate from Postgres `Order.payload` / `order_context(order)`) and passes them straight to `prepare_llm_input` (`gemini.py:655-667`), which uses `_PROMPT_SAFE_ORDER_FIELDS` (`ORDER_CONTEXT_ALLOWED_SET | _LEGACY_SAFE_ORDER_FIELDS`, 17 fields) and places `order_id`/`tracking_code` only in `internal_sources` (`include_order_identifiers=True`), without building structured `order_context` citations. By contrast, the live backend -> AI service flow remains strictly restricted to the 10 canonical `ORDER_CONTEXT_ALLOWED_FIELDS` with no widening to `_LEGACY_SAFE_ORDER_FIELDS` or identifiers.

## 2. Minimal Fix Applied (Zero Core-Helper Blast Radius)

- **`apps/backend/tickets/service.py:12, 39-64` (`order_context`):**
  - Reuses shared `ORDER_CONTEXT_ALLOWED_FIELDS`, `ORDER_CONTEXT_ALLOWED_SET`, and `extract_order_facts(..., allowed_fields=ORDER_CONTEXT_ALLOWED_SET, include_order_identifiers=False, strict=False)` from `apps.core_backend.llm.gemini`.
  - Collects non-`None` candidate values across top-level `order.payload`, `shipment`, and `refund` strictly for `ORDER_CONTEXT_ALLOWED_FIELDS`, passes order/customer secret keys alongside candidates only for identifier redaction (`_redact_known_context_identifiers`), drops `None`/malformed fields safely without failing healthy sibling fields, preserves canonical `{amount_minor, currency}` dicts with uppercase ISO currency for money fields, and excludes legacy keys/customer PII/identifiers.
- **No edits** to `apps/core_backend/llm/gemini.py`, `apps/core_backend/safety.py`, `apps/core_backend/orchestration/pipeline_runner.py`, `apps/ai_service/engine.py`, or `apps/ai_service/main.py` (zero blast radius to shared core/Runner paths).
- **Tests:**
  - `tests/application/test_backend_safety_closure.py:734-738`: updated `transport_order_context` allowlist assertion from the stale 6-field literal set to `ORDER_CONTEXT_ALLOWED_SET` and verified `placed_at` forwarding on seeded `ORD-1001`.
  - `tests/unit/test_order_context_grounding.py:553-698`: added `test_backend_order_context_to_engine_all_ten_canonical_fields_and_exclusion` proving all 10 canonical fields survive `order_context(order)` -> `validate_egress_payload` -> `SuggestionRequest` -> `Engine.draft` (stub `MockTransport` Gemini client, zero paid calls) -> `SuggestionWorker` hydration, while `None`, malformed, legacy, and PII inputs stay excluded/rejected.

## 3. Post-Edit Verification Results (Mock/Fake LLM, Zero Paid Calls)

1. **Order-Context, Grounding, Privacy, Runner & Full-Pipeline Regressions (`281 passed, 0 failed, 0 skipped` in `159.42s`):**
   - Command: `$env:PSYCOPG_IMPL="python"; $env:PATH="F:\PostgreSQL\bin;$env:PATH"; .\.venv\Scripts\python.exe -m pytest tests/unit/test_order_context_grounding.py tests/unit/test_ai_grounding.py tests/unit/test_completion_grounding.py tests/unit/test_privacy_pii.py tests/unit/test_gemini_llm.py tests/unit/test_llm_source_privacy.py tests/unit/test_llm_egress_safety_review.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_pipeline_runner_safety_b.py tests/application/test_backend_safety_closure.py tests/application/test_workflow_privacy.py tests/application/test_gap3_privacy_ner_a.py tests/application/test_application.py tests/e2e/test_full_pipeline.py -q`
2. **Acceptance Collector & AI Boundary Contracts (`28 passed, 0 failed, 0 skipped` in `29.27s`):**
   - Command: `$env:PSYCOPG_IMPL="python"; $env:PATH="F:\PostgreSQL\bin;$env:PATH"; .\.venv\Scripts\python.exe -m pytest tests/application/test_final_acceptance_collector.py tests/application/test_ai_boundary.py -q`

## 4. Unchanged Core & Frozen Invariant SHA-256 Digests

- `apps/core_backend/safety.py`: `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000`
- `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
- `apps/core_backend/llm/gemini.py`: `c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b`
- `apps/core_backend/orchestration/pipeline_runner.py`: `c981baf833a4071220b62b14043985c684dfbc307af79bc4426f18ea615765a6`
- `apps/ai_service/engine.py`: `481bc7ab7fa2a7ad42ca00add79925339b138116aa2b57e233300ba3f7bc88ff`
- `apps/ai_service/main.py`: `933851213299db2f051de10d6d701a94faad36c58e94623fb0ab05d8e55309cc`
- `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
- `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
- `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
- `.local/training-cap-20261114.json`: `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`
- `.local/ai.env`: `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87`

## 5. Remaining Limits

- Seeded `data/knowledge/mock_orders.json` / `apps/backend/seed.py` records only populate prose `shipment.estimated_delivery_text` (not ISO `estimated_delivery_at`) and do not yet populate `refund.refund_requested_at`; those fields now pass automatically whenever upstream order payloads provide ISO values.
- Already-running backend/ai-service processes (`.local/processes.json`) were not restarted and runtime remains LLM-disabled.
