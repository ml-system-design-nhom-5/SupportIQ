# Safety Gap 3 Audit — Strict Privacy / NER Fail-Closed & Literal Collision Hardening

- **Date:** 2026-11-15
- **Branch:** `minh` (on top of closed Gap 2 `d3c4c2a0b6ac5cf789ef409305345c7154acc1da`)
- **Scope:** Gap 3 privacy / NER fail-closed egress gating and pseudonymize/restore placeholder collision hardening across backend config, intake, worker boundary, and focused tests (`apps/core_backend/safety.py`, `apps/core_backend/retrieval/adapter.py`, `apps/ai_service/`, Gap 2 contracts, `order_context`, frontend, weights, KB, policy, `.local/` preserved unchanged).

## 1. Root Defects & Strict Configuration Default

1. **Silent NER skip in `apps/backend/tickets/privacy.py`:**
   - Previously `_get_spacy_nlp()` returned `None` when `spaCy` or `en_core_web_sm` was unavailable, and `pseudonymize()` silently skipped free-form `PERSON` / `GPE` / `LOC` / `FAC` NER (`if nlp is not None: ... except Exception: pass`), returning `privacy_failed=False` and queuing `SuggestionJob` payloads containing unmasked names and locations toward `ai_service` / external LLM.
2. **Literal / sentinel / overlap / `{0,2}` index hazards in `privacy.py`:**
   - `PLACEHOLDER` capped suffix indices at 3 digits (`_[1-9][0-9]{0,2}`), dropping round-trip/validation above `_999`.
   - Literal escaping used bare `\x00{i}\x00` strings without checking raw input or `known` DB values for `\x00`.
   - `known` DB values iterated by dict insertion order rather than longest-match-first globally, and ran before high-specificity identifiers (`EMAIL`), enabling short `known["NAME"]` values to fragment emails or longer addresses.
   - `SuggestionWorker.process()` dispatched queued payloads directly to `_post_ai()` without an independent pre-egress privacy/strictness check.

## 2. Changes Applied

### Source Modules (`4` files)
1. **`apps/backend/platform/config.py` (`Settings`):**
   - Added `require_privacy_ner: bool = True` (strict by default for all production/runtime configurations, including any external or localhost/unknown `ai_service_base_url`; never auto-disabled when `spaCy` is absent). Opt-out requires explicit `require_privacy_ner=False` / `SUPPORTIQ_REQUIRE_PRIVACY_NER=false`.
2. **`apps/backend/tickets/privacy.py`:**
   - Added `is_privacy_ner_available() -> bool`.
   - Removed the 999 cap on `PLACEHOLDER` (`(?:_[1-9][0-9]*)?`).
   - Updated `pseudonymize(message, known, *, require_ner: bool = True)` to fail closed with `ValueError` whenever `_get_spacy_nlp()` returns `None` under `require_ner=True`, or whenever `_get_spacy_nlp()` / `nlp(result)` raises an exception (`except Exception: pass` removed).
   - Replaced literal/marker handling with collision-free sentinels (`_collision_free_sentinel(message, known)`), masked Luhn `CARD` and high-specificity structured identifiers (`EMAIL`, `ORDER_ID`, `TRACKING_ID`, `TRANSACTION_ID`) prior to globally length-sorted `known` entries, ran NER/remaining patterns into unique sentinels, and finalized placeholders in one pass (`restore()` safely performs a single non-recursive `PLACEHOLDER.sub`).
   - Added `validate_egress_payload(payload, *, require_ner: bool = True)` enforcing NER availability, non-empty 1..4000 char masked `message`, and absence of unmasked Luhn cards / `EMAIL` / `ORDER_ID` / `TRACKING_ID` / `TRANSACTION_ID` patterns.
3. **`apps/backend/tickets/service.py` (`create_suggestion`):**
   - Explicitly passes `require_ner=bool(getattr(settings, "require_privacy_ner", True))` from `Settings` on all ticket-intake and override/retry suggestion paths. Failures set `privacy_failed=True`, empty `"message": ""` in `request_payload`, zero `SuggestionJob` rows, `reason_codes=["pseudonymization_failed"]`, and keep sticky `is_authority_required` (Gap 2) + disabled `retry_suggestion`.
4. **`apps/backend/tickets/jobs.py` (`SuggestionWorker.process`):**
   - Invokes `validate_egress_payload(payload, require_ner=bool(getattr(self.settings, "require_privacy_ner", True)))` BEFORE any `_post_ai()` HTTP request; failure records safe manual fallback (`analysis_status="unavailable"`, `draft_status="unavailable"`, `reason_codes=["pseudonymization_failed"]`, zero raw PII) and finishes the job with **0** network calls.

### Explicit Offline Opt-Out Documented on Existing Unit / Mock Test Fixtures
To preserve strict production defaults without silently bypassing tests when optional `en_core_web_sm` is un-installed in `.venv`, offline unit/mocked-AI tests explicitly opt out via `require_privacy_ner=False` / `require_ner=False` / `SUPPORTIQ_REQUIRE_PRIVACY_NER="false"`:
- `tests/unit/test_privacy_pii.py` (`require_ner=False` on regex/Luhn/literal/unavailable-NER unit tests; deterministic `mock_nlp` test uses default strict `require_ner=True`)
- `tests/application/test_workflow_privacy.py` (`require_ner=False` on helper/recall unit checks)
- `tests/application/test_application.py` (`require_ner=False` on `test_pseudonymization_preserves_literals_and_masks_source_ids`)
- `tests/application/test_backend_safety_closure.py` (`require_privacy_ner=False` on mocked-AI `pg_application` + `require_ner=False` on slang unit test)
- `tests/application/test_gap2_authority_outage_a.py` (`require_privacy_ner=False` on `pg_app_ai_enabled` mock fixture)
- `tests/unit/test_typed_fault_propagation_a.py`, `tests/unit/test_suggestion_worker_concurrency.py`, `tests/unit/test_order_context_grounding.py`, `tests/e2e/test_full_pipeline.py` (`require_privacy_ner=False` / `require_ner=False` on offline unit/mock fixtures)
- `tests/application/test_final_acceptance_collector.py`, `tests/application/test_intent_correction_diagnostic.py` (`SUPPORTIQ_REQUIRE_PRIVACY_NER=false` strictly inside offline `mode="mock"` test functions)

*(Preserved historical offline scripts such as `artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114/evaluate_candidate.py` and `pipeline/training/orig_fit2_return_contrast_data.py` were not modified; offline post-privacy evaluations running without `en_core_web_sm` must pass explicit `require_ner=False`.)*

## 3. Verification Results (TDD RED -> GREEN & Regression)

- **TDD RED (`tests/application/test_gap3_privacy_ner_a.py` prior to code edits):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/application/test_gap3_privacy_ner_a.py -v --tb=line`
  - Result: Collection failed (`ImportError: cannot import name 'is_privacy_ner_available' from 'apps.backend.tickets.privacy'`).
- **TDD GREEN (`tests/application/test_gap3_privacy_ner_a.py`):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/application/test_gap3_privacy_ner_a.py -v`
  - Result: **`8 passed in 35.91s`**
  - Verified: strict default config/call (`ValueError` when missing NER); `pseudonymization_failed` with 0 `SuggestionJob` rows, empty `request_payload["message"]`, 0 outbound HTTP calls, disabled `retry_suggestion`, and preserved manual human workflow; NER load/inference runtime exceptions failing closed while retaining sticky Gap 2 authority (`403 authority-required` + manager approval); `SuggestionWorker.process` pre-dispatch gate blocking both strict-missing-NER and unmasked payloads with 0 `_post_ai` calls; valid mocked spaCy `PERSON`/`GPE` masking + console-only restoration; literal/nested/`\x00`/`>999` index/overlap/unicode/length hardening; `AI_REASONS` bounded `29` codes and zero PII in structured logs.
- **Full Gap 1 + Gap 2 + Gap 3 + E2E Regression Suite:**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/application/ tests/unit/test_privacy_pii.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_suggestion_worker_concurrency.py tests/unit/test_order_context_grounding.py tests/unit/test_mandatory_routing_b.py tests/unit/test_safety_slice1_gap1_a.py tests/e2e/test_full_pipeline.py -v`
  - Result: **`441 passed, 1 skipped in 253.01s (0:04:13)`** (single skip: `tests/unit/test_privacy_pii.py::test_live_spacy_free_form_ner_masking_integration`, because optional `spacy`/`en_core_web_sm` is not installed in `.venv`).

## 4. Invariant SHA-256 Verification

`git diff --stat HEAD -- apps/core_backend/ apps/ai_service/` returned empty (no modifications).

| Artifact | Verified SHA-256 |
| --- | --- |
| `apps/core_backend/safety.py` | `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000` |
| `apps/core_backend/retrieval/adapter.py` | `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f` |
| `data/knowledge/approved_kb.v2.json` | `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec` |
| `apps/ai_service/kb-release.json` | `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804` |
| `apps/core_backend/config/policies/intent_policy.v2.json` | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors` | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` |
| `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json` | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` |
| `artifacts/models/trained/distilbert-supportiq/model.safetensors` | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| `.local/training-cap-20261114.json` | `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` |
| `.local/ai.env` | `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87` |

## 5. Remaining Operational & Separate Items

- **Deployment NER Provisioning Issue (Remaining):** `spaCy` + `en_core_web_sm` remain un-installed in the local environment (intentionally not installed in this slice). Under the strict safe default (`require_privacy_ner=True`), external AI/LLM drafting fails closed cleanly to `"pseudonymization_failed"` manual handling rather than silently leaking raw names/addresses until the runtime image provisions `spaCy` + `en_core_web_sm`.
- **Out of Scope / Separately Tracked (Not Bundled):** `order_context` parity (`6 vs 10` fields) and frontend `canSendReply` fallback remain open in their respective tracked workstreams.
