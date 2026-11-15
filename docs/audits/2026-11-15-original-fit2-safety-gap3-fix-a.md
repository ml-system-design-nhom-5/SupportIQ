# Gap 3 Blocker Remediation Audit (Worker A)

**Date:** 2026-11-15
**Branch:** `minh`
**Reviewed Baseline:** `98368a6f401c2c377292b55a7ade56f191c88fc4` + review `5b15f47f9a7d423f52bc832bf7c49174588ec5fd`

## Summary of Fixes

1. **Blocker 1 — Non-Bypassable Strict Privacy NER for Configured AI & HTTP Egress**
   - `apps/backend/platform/config.py` (`Settings._enforce_strict_privacy_ner`): rejects `SUPPORTIQ_REQUIRE_PRIVACY_NER` env-var disablement and rejects `require_privacy_ner=False` whenever `ai_service_base_url` is configured (no URL hostname/loopback bypass, since local `ai_service` also forwards to external LLMs).
   - `apps/backend/tickets/service.py` (`create_suggestion`): unconditionally enforces `require_ner=True` whenever `settings.ai_service_base_url` is set.
   - `apps/backend/tickets/jobs.py` (`SuggestionWorker._uses_real_http_transport`, `SuggestionWorker.process`): unconditionally enforces strict NER whenever any real `httpx.Client` HTTP transport or `ai_service_base_url` is active, independent of intake flags.
   - Updated mock/offline tests (`test_backend_safety_closure.py`, `test_final_acceptance_collector.py`, `test_gap2_authority_outage_a.py`, `test_intent_correction_diagnostic.py`, `test_full_pipeline.py`, `test_order_context_grounding.py`, `test_suggestion_worker_concurrency.py`, `test_typed_fault_propagation_a.py`) to run under strict `require_privacy_ner=True` using in-process `_get_spacy_nlp` stubs rather than env/config NER opt-outs.

2. **Blocker 2 — Canonical Request Envelope & Full-Payload Pre-Dispatch Validation**
   - `apps/backend/tickets/privacy.py` (`validate_egress_payload`, `_validate_order_context`, `_assert_no_raw_pii`): enforces exact `SuggestionRequest` envelope keys (`{"message", "order_context", "as_of"} <= keys <= {"message", "order_context", "as_of", "intent_override"}`, forbidding `pseudonym_map` or unexpected nested containers), validates `order_context` using canonical `ORDER_CONTEXT_ALLOWED_SET` + `extract_order_facts(..., strict=True)` imported read-only from `apps.core_backend.llm.gemini` (preserving the backend 6-field emitter unchanged), validates ISO `as_of` timezone awareness and `intent_override`, and scans all string fields for Luhn `CARD`, `EMAIL`, `ORDER_ID`, `TRACKING_ID`, `TRANSACTION_ID`, `ADDRESS`, and `PHONE` (while skipping ISO date/datetime spans so legitimate timestamps do not false-trigger).
   - `apps/backend/tickets/jobs.py` (`SuggestionWorker.process`): cross-checks against non-literal raw PII stored in `Suggestion.pseudonym_map` when present in DB, rejecting legacy/tampered queued jobs pre-dispatch with `pseudonymization_failed`, `0` HTTP calls, disabled `retry_suggestion`, and sticky Gap 2 `is_authority_required`.

3. **Blocker 3 — Sentinel-Free Span-Based Pseudonymization**
   - `apps/backend/tickets/privacy.py` (`pseudonymize`, `_collect_regex_and_known_spans`, `_collect_ner_spans`): eliminated internal `\x00P<id>\x00` sentinel rewriting completely.
   - Resolves non-overlapping `(start, end, kind, raw)` spans directly against unmodified input in priority tiers: Tier 0 customer literals matching `PLACEHOLDER`, Phase A Luhn `CARD` & high-specificity identifiers (`EMAIL`, `ORDER_ID`, `TRACKING_ID`, `TRANSACTION_ID`), Phase B gap-scoped `PHONE`, Phase C gap-scoped `ADDRESS` (`\b`-bounded street suffixes) + `known` DB values ranked longest-match-first (so short `known` substrings like `"Hue"` cannot fragment `"123 Nguyen Hue Street"`), and Phase D spaCy NER over uncovered gaps only, followed by a single left-to-right slice assembly and single-pass `restore()`.

## Verification

- `.\.venv\Scripts\pytest.exe tests/application/test_gap3_privacy_ner_a.py -q`: **11 passed** (covering all 3 blocker regressions + original Gap 3 suite).
- `.\.venv\Scripts\pytest.exe tests/application/ tests/unit/test_privacy_pii.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_suggestion_worker_concurrency.py tests/unit/test_order_context_grounding.py tests/unit/test_mandatory_routing_b.py tests/unit/test_safety_slice1_gap1_a.py tests/e2e/test_full_pipeline.py -rs -q`: **444 passed, 1 skipped** (`test_live_spacy_free_form_ner_masking_integration` skipped because optional `spaCy`/`en_core_web_sm` is not installed in `.venv`).

## Invariant Digests Verified Unchanged

- `apps/core_backend/safety.py`: `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000`
- `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
- `apps/core_backend/llm/gemini.py`: `c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b`
- `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
- `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
- `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
