# Task B: Full HTTP IntentClient -> decide_route -> PipelineRunner Safety Verification (2026-11-13)

## Scope & Harness
- Path exercised end-to-end: `IntentClient` (FastAPI `TestClient` over HTTP/ASGI) -> `ml_inference` serving model (`distilbert-supportiq`) -> `decide_route` (`apps/core_backend/intent/routing.py`) -> `PipelineRunner.run` (`apps/core_backend/orchestration/pipeline_runner.py`).
- Real `RetrievalAdapter` over approved `apps/ai_service/kb-release.json` and synthetic `CommerceAdapter` (`mock_orders.json`).
- `SpyCompliantLLMClient` (`configured=True`): always succeeds on `generate()` so downstream routing/guard leaks are never hidden by LLM refusal or network errors. Zero live Gemini calls made.
- Baseline (`BEFORE`): commit `e46e1c9` (root `665c6cf` reconciled).
- Guarded (`AFTER`): minimal shared pre-generation & evidence-scope guards inside `PipelineRunner.run` (`apps/core_backend/orchestration/pipeline_runner.py`).

## Side-by-Side Metrics (BEFORE `e46e1c9` vs AFTER)

| Slice | Executed | BEFORE Unsafe Terminal Drafts / LLM | AFTER Unsafe Terminal Drafts / LLM | BEFORE Final Actions | AFTER Final Actions |
|---|---:|---:|---:|---|---|
| Mandatory HTTP-leaky 12 | 12 | 12 / 12 | 0 / 0 | `{'retrieve_draft': 12}` | `{'escalate': 11, 'manual_fallback': 1}` |
| ml_oos HTTP-leaky 2 | 2 | 2 / 2 | 0 / 0 | `{'retrieve_draft': 2}` | `{'manual_fallback': 1, 'escalate': 1}` |
| Final acceptance non-ans 4 | 4 | 3 / 3 | 0 / 0 | `{'escalate': 1, 'retrieve_draft': 3}` | `{'escalate': 4}` |
| Mandatory unfaulted 60 (3 faulted NOT_EXECUTED) | 60 | 12 / 12 | 0 / 0 | `{'escalate': 37, 'clarify': 11, 'retrieve_draft': 12}` | `{'escalate': 48, 'clarify': 11, 'manual_fallback': 1}` |
| ml_oos 80 | 80 | 2 / 2 | 0 / 0 | `{'escalate': 64, 'clarify': 14, 'retrieve_draft': 2}` | `{'escalate': 65, 'clarify': 14, 'manual_fallback': 1}` |
| Supported answerable `draft_expected_34` | 34 | raw=21, correct=17, llm=21 | raw=21, correct=17, llm=21 | `{'retrieve_draft': 21, 'clarify': 12, 'escalate': 1}` | `{'retrieve_draft': 21, 'clarify': 12, 'escalate': 1}` |
| Final acceptance answerable 12 | 12 | raw=2, correct=2, llm=2 | raw=2, correct=2, llm=2 | `{'escalate': 10, 'retrieve_draft': 2}` | `{'escalate': 10, 'retrieve_draft': 2}` |
| Final acceptance non-answerable 11 (case-21 NOT_EXECUTED) | 11 | 3 / 3 | 0 / 0 | `{'escalate': 5, 'clarify': 3, 'retrieve_draft': 3}` | `{'escalate': 8, 'clarify': 3}` |
| `ml_noise_420` | 420 | llm=214 | llm=214 | `{'retrieve_draft': 214, 'escalate': 71, 'clarify': 135}` | `{'retrieve_draft': 214, 'escalate': 71, 'clarify': 135}` |

## Trace of 12 Mandatory + 2 ml_oos + 4 Final Acceptance Non-Answerable Cases

| Group | ID | Initial (`decide_route`) | BEFORE Final (LLM) | AFTER Final (LLM) | Queue / Team | Reason Codes (AFTER) |
|---|---|---|---|---|---|---|
| mandatory_http_leak_12 | `uns-return_product_online-01` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `returns_support` | `['recognized_outside_product_scope', 'out_of_scope_intent']` |
| mandatory_http_leak_12 | `una-shipping_costs-01` | `retrieve_draft` | `retrieve_draft` (`True`) | `manual_fallback` (`False`) | `standard` / `delivery_support` | `['no_valid_document']` |
| mandatory_http_leak_12 | `una-return_policy-01` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `returns_support` | `['insufficient_evidence']` |
| mandatory_http_leak_12 | `una-refund_policy-02` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `payments_support` | `['insufficient_evidence']` |
| mandatory_http_leak_12 | `una-cancel_order-01` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `returns_support` | `['insufficient_evidence']` |
| mandatory_http_leak_12 | `una-shipping_costs-02` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `returns_support` | `['insufficient_evidence']` |
| mandatory_http_leak_12 | `una-request_refund-01` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `manager` / `payments_support` | `['requires_authority', 'insufficient_evidence']` |
| mandatory_http_leak_12 | `una-return_policy-02` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `returns_support` | `['insufficient_evidence']` |
| mandatory_http_leak_12 | `una-cancel_order-02` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `manager` / `order_support` | `['requires_authority', 'insufficient_evidence']` |
| mandatory_http_leak_12 | `una-payment_issue-01` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `manager` / `payments_support` | `['requires_authority', 'insufficient_evidence']` |
| mandatory_http_leak_12 | `una-return_policy-03` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `returns_support` | `['insufficient_evidence']` |
| mandatory_http_leak_12 | `una-refund_policy-03` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `payments_support` | `['insufficient_evidence']` |
| ml_oos_http_leak_2 | `oos-other_domain-11` | `retrieve_draft` | `retrieve_draft` (`True`) | `manual_fallback` (`False`) | `standard` / `returns_support` | `['out_of_scope_intent']` |
| ml_oos_http_leak_2 | `oos-multi_intent-08` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `returns_support` | `['recognized_outside_product_scope', 'out_of_scope_intent']` |
| fa_non_answerable_4 | `final-case-13` | `retrieve_draft` | `escalate` (`False`) | `escalate` (`False`) | `manager` / `order_support` | `['requires_authority', 'commerce_unauthorized_customer']` |
| fa_non_answerable_4 | `final-case-22` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `payments_support` | `['insufficient_evidence']` |
| fa_non_answerable_4 | `final-case-23` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `standard` / `returns_support` | `['insufficient_evidence']` |
| fa_non_answerable_4 | `final-case-24` | `retrieve_draft` | `retrieve_draft` (`True`) | `escalate` (`False`) | `manager` / `payments_support` | `['requires_authority', 'insufficient_evidence']` |

## Uninjected Faults (Reported Explicitly as `NOT_EXECUTED`)
- `mandatory_must_escalate` uninjected faults (3): `[{'id': 'unc-track_order-03', 'fault': 'ml_timeout', 'status': 'NOT_EXECUTED'}, {'id': 'unc-return_policy-04', 'fault': 'encoder_failure', 'status': 'NOT_EXECUTED'}, {'id': 'unc-track_order-05', 'fault': 'commerce_unauthorized', 'status': 'NOT_EXECUTED'}]`
- `final_acceptance` uninjected synthetic conflict fault (1): `final-case-21` (`NOT_EXECUTED`)
