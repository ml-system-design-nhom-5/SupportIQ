# Worker C Independent Verification: `order_context` 10-Field Contract Parity (`b94df274`)

- **Date:** 2026-11-15
- **Branch:** `minh`
- **Commit Verified:** `b94df2744d4e9d57bbbc5b4ae3b29a466d886027` (`fix(grounding): align backend order_context with canonical 10-field allowlist`)
- **Prior Audit:** [2026-11-15-order-context-contract-parity-a.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-15-order-context-contract-parity-a.md)
- **Verdict:** **PASS** (scoped strictly to the `order_context` 10-field contract parity slice; not whole-project acceptance).
- **Runtime / Safety Posture:** Zero production patches, zero training, zero paid/live LLM calls, zero service restarts (`.local/processes.json` services remain LLM-disabled pending grouped runtime restart after frontend `canSendReply` fix).

---

## 1. End-to-End Parity & Adversarial Verification

Independent script [verify_order_context_parity_c.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/evaluation/order_context_contract_parity_c_20261115/verify_order_context_parity_c.py) recorded `VERDICT=PASS PASSED=6/6 DUR_S=16.18` in [order_context_parity_verification.json](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/evaluation/order_context_contract_parity_c_20261115/order_context_parity_verification.json) using real spaCy NER (`en_core_web_sm`), real `RetrievalAdapter`, fake HTTP `httpx.MockTransport` LLM responses (dynamically resolving the `order_facts` `source_id`), and a disposable PostgreSQL schema:

| Case ID | Scope Exercised | Result | Observed Evidence |
| --- | --- | --- | --- |
| `oc-10fields-usd-e2e` | All 10 canonical fields (`" usd "` -> `"USD"`, offset/microsecond Z/date-only ISO timestamps) -> `validate_egress_payload(..., require_ner=True)` -> `SuggestionRequest` -> `Engine.draft` -> `SuggestionWorker.process` | **PASS** | Exact 10-key order `ORDER_CONTEXT_ALLOWED_FIELDS`; money dicts preserved; 13 legacy/PII keys absent from `order_context` and wire payload; `ORDER-FACTS` source & `order_facts` wire keys match 10/10; worker hydrates `fields` and `values == ctx`. |
| `oc-missing-non-dict-precedence` | `payload` as `None`/`{}`/`["bad"]`/`"bad"`, `shipment`/`refund` as `None`/non-dict, and `data > shipment > refund` skipping `None` | **PASS** | Non-dict containers yield `{}` or surviving root facts without crash; `data` `delivered_at=None` falls through to `shipment.delivered_at`; `data.shipment_status` beats `shipment`, `shipment.refund_status` beats `refund`. |
| `oc-malformed-invalid-pii-probe` | Invalid calendar/prose/bool/blank dates, bool/float/neg/extra-key/bad-currency money, dict-in-non-money (`order_status: {amount_minor, currency}`), PII/identifier redaction, `forbidden_values`, and 19 direct invalid egress/schema probes | **PASS** | Sibling valid fields survive (`order_status`, `shipment_status`, `refund_status`); `order_id`/`customer_name`/`tracking_code`/email/phone masked (`[IDENTIFIER]`, `[EMAIL]`, `[PHONE_OR_NUMBER]`); dict in `order_status` dropped; `19/19` rejected by both `validate_egress_payload` and `SuggestionRequest`; street address & short `forbidden_values` blocked fail-closed. |
| `oc-no-date-invention-grounding-strict` | Order with `estimated_delivery_text` & `expected_refund_time` (prose only, no ISO `estimated_delivery_at`/`refund_requested_at`) + fabricated date/amount/commitment probes | **PASS** | Missing ISO date keys stay absent from `order_context` and wire `order_facts`; fabricated `estimated_delivery_at` (`2026-10-04`), fabricated `refund_requested_at` (`2026-10-05`), wrong `order_total` (`250,000 VND`), and ungrounded `cancelled` commitment all fail closed (`llm_unavailable` + `grounding_failed`), while grounded `2026-10-01` passes (`draft_ready`). |
| `oc-single-field-hydration` | Single-field `{"placed_at": "2026-10-01"}` through `Engine.draft` -> `SuggestionWorker.process` | **PASS** | Hydrates both `fields: ["placed_at"]` + `values` and `field: "placed_at"` + `value: "2026-10-01"`. |
| `oc-pg-e2e-10fields-roundtrip` | Disposable PG schema -> `seed()` -> `ORD-C-10F` (10 fields, `"vnd"` -> `"VND"`) + `ORD-1001` check -> `TestClient` `POST /v1/shop/tickets` (real NER) -> `SuggestionJob` -> `SuggestionWorker` -> `Engine` -> `GET /v1/console/tickets/{tid}` | **PASS** | Staff workspace reaches `draft_status == "draft_ready"` with all 10 fields hydrated and zero secrets on the AI wire; seeded `ORD-1001` emits `placed_at` without inventing `estimated_delivery_at`/`refund_requested_at`. |

---

## 2. Focused Regression Suites (Mock/Fake LLM, Zero Paid Calls)

1. **Order-Context, Grounding, Privacy, Application & Full-Pipeline Suite (15 files):**
   - Command: `$env:PSYCOPG_IMPL="python"; $env:PATH="F:\PostgreSQL\bin;$env:PATH"; .\.venv\Scripts\python.exe -m pytest tests/unit/test_order_context_grounding.py tests/unit/test_ai_grounding.py tests/unit/test_completion_grounding.py tests/unit/test_privacy_pii.py tests/unit/test_gemini_llm.py tests/unit/test_llm_source_privacy.py tests/unit/test_llm_egress_safety_review.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_pipeline_runner_safety_b.py tests/application/test_backend_safety_closure.py tests/application/test_workflow_privacy.py tests/application/test_gap3_privacy_ner_a.py tests/application/test_ai_boundary.py tests/application/test_application.py tests/e2e/test_full_pipeline.py -q`
   - Result: **`294 passed` in `178.68s`** (`0 failed, 0 skipped`).
2. **Final Acceptance Collector Contract Suite:**
   - Command: `$env:PSYCOPG_IMPL="python"; $env:PATH="F:\PostgreSQL\bin;$env:PATH"; .\.venv\Scripts\python.exe -m pytest tests/application/test_final_acceptance_collector.py -q`
   - Result: **`15 passed` in `28.37s`** (`0 failed, 0 skipped`).

---

## 3. Preserved Invariants & Observed Non-Blocking Nuances

- **All 11 Pinned SHA-256 Digests Match (`mismatches: []`) & Training Cap Preserved (`2/2` stopped):**
  - `apps/core_backend/safety.py`: `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000`
  - `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
  - `apps/core_backend/llm/gemini.py`: `c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b`
  - `apps/core_backend/orchestration/pipeline_runner.py`: `c981baf833a4071220b62b14043985c684dfbc307af79bc4426f18ea615765a6`
  - `apps/ai_service/engine.py`: `481bc7ab7fa2a7ad42ca00add79925339b138116aa2b57e233300ba3f7bc88ff`
  - `apps/ai_service/main.py`: `933851213299db2f051de10d6d701a94faad36c58e94623fb0ab05d8e55309cc`
  - `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
  - `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
  - `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
  - `.local/training-cap-20261114.json`: `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` (`training_stopped: true`, `additional_attempts_started: 2`)
  - `.local/ai.env`: `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87`
- **Non-Blocking Code Nuances (No Defect Blocking Parity):**
  1. `order_context(order)` ([service.py:45-49](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L45-L49)) picks the first non-`None` value across `(data, shipment, refund)`; a malformed non-`None` root value shadows a valid nested value and is dropped by `extract_order_facts(..., strict=False)` (safe fail-closed).
  2. Pre-existing `create_suggestion` ([service.py:120](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L120), untouched by `b94df27`) indexes `order.payload["shipment"].get("tracking_code")` without a dict guard (unlike `order_context(order)`), assuming persisted DB `Order` rows contain a dict `shipment`.
  3. `order_context(order)` feeds `shipment.get("tracking_code")` (not top-level `data`) into `lookup`, and `_redact_known_context_identifiers` ([gemini.py:553-568](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/core_backend/llm/gemini.py#L553-L568)) redacts `_CONTEXT_SECRET_KEYS` of length `>= 4`; short names or unpatterned PII in string fields remain gated by `SuggestionWorker.process` passing `pseudonym_map` `forbidden_values` to `validate_egress_payload`.
  4. `PipelineRunner.run` ([pipeline_runner.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/core_backend/orchestration/pipeline_runner.py), untouched) remains on `prepare_llm_input` (`_PROMPT_SAFE_ORDER_FIELDS`), while live backend -> AI service egress remains restricted to the 10 canonical `ORDER_CONTEXT_ALLOWED_FIELDS`.
- **Skipped / Not Exercised:** Live Gemini API calls, full model evaluation benchmarks, frontend tests, and live runtime service reload (intentionally deferred).
