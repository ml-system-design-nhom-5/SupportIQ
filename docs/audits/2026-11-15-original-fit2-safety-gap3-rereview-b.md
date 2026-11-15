# Gap 3 Re-Review Audit Report (Worker B)

- **Date:** 2026-11-15
- **Reviewer:** Dispatched Worker B (`term_8533029e-5942-4b1e-8e04-94d88b12411c`)
- **Task / Dispatch:** `task_9e031ba2f032` / `ctx_cc4d739db77d`
- **Target Branch / Commit:** `minh` @ `59a41fe8ddb1926acbef19fc699dc2f15dc91492`
- **Prior Block Reference:** `5b15f47f9a7d423f52bc832bf7c49174588ec5fd`
- **Verdict:** **PASS** (All 3 prior Gap 3 blockers closed; live spaCy NER `en_core_web_sm` remains unprovisioned in `.venv` so `test_live_spacy_free_form_ner_masking_integration` is `SKIPPED` and live-NER recall remains a runtime provisioning prerequisite.)

---

## 1. Prior Blocker Verification Matrix

| Blocker | Status | Verified Code & Behavior |
|---|---|---|
| **1. Strict NER bypass via config/env/intake/worker transport** | **CLOSED** | [config.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/platform/config.py#L33-L40), [service.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L105-L109), [jobs.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L261-L274) |
| **2. Narrow egress validation (`message` only / `_HIGH_SPECIFICITY_KINDS` only / missing DB map check)** | **CLOSED** | [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L24-L26), [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L259-L348), [jobs.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L275-L309) |
| **3. Sentinel collision (`\x00P0\x00`), short known substring fragmentation, placeholder/literal handling** | **CLOSED** | [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L9-L26), [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L67-L235), [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L350-L353) |

---

## 2. Detailed Verification Findings

### Blocker 1 — Non-Bypassable Strict NER Enforcement
- **Config validation (`Settings._enforce_strict_privacy_ner`):** Verified in [config.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/platform/config.py#L33-L40). Probes confirmed `ValidationError` is raised when:
  - `ai_service_base_url` is set (`"http://ai.local"`, `"https://ai.example.com"`, `"   "`, `""`) with `require_privacy_ner=False`.
  - `SUPPORTIQ_REQUIRE_PRIVACY_NER` env var is `"false"`, `"0"`, `"no"`, `"off"`, or `"FALSE"` (and Pydantic `bool_parsing` rejects `" false "`, `"maybe"`, `""`).
  - `_env_file` sets `SUPPORTIQ_REQUIRE_PRIVACY_NER=false` alongside `ai_service_base_url="http://ai.local"`.
- **Intake gate (`service.create_suggestion`):** Verified in [service.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L105-L108) (`require_ner=bool(settings.ai_service_base_url) or bool(getattr(settings, "require_privacy_ner", True))`). Probing with a duck-typed `SimpleNamespace(ai_service_base_url="http://ai.local", require_privacy_ner=False)` without spaCy fails closed (`analysis_status="unavailable"`, `draft_status="unavailable"`, `reason_codes=["pseudonymization_failed"]`).
- **Worker transport gate (`SuggestionWorker._uses_real_http_transport` & `process`):** Verified in [jobs.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L261-L274).
  - Uninjected `httpx.Client` or injected real `httpx.Client` without `httpx.MockTransport` returns `_uses_real_http_transport() == True` even when `ai_service_base_url=None`.
  - Configured `ai_service_base_url="http://ai.local"` forces `strict_ner=True` even when `http_client` is a `httpx.MockTransport` client or a custom `SpyHttpClient` wrapper (`spy_calls=0`, `draft_status="unavailable"`, `reason_codes=["pseudonymization_failed"]`).
  - All 8 modified test files in commit `59a41fe8` replace prior `require_privacy_ner=False` / env opt-outs with in-process `_get_spacy_nlp` monkeypatches.

### Blocker 2 — Full `SuggestionRequest` Envelope Validation & DB Secret Cross-Check
- **Strict envelope & nested typing (`validate_egress_payload` / `_validate_order_context`):** Verified in [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L24-L25) and [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L287-L348). Probes confirmed:
  - **False-positive check PASSES:** Valid payload containing numeric VND amount `1402000`, ISO dates `2026-11-10`, ISO timestamps `2026-11-15T12:00:00+07:00`, and allowed `order_context` money/date fields passes strict validation (`require_ner=True` with offline fake NER stub).
  - **Envelope rejections (zero secret leakage in exception text):** Extra top-level keys (`unexpected_nested`), missing `as_of`, naive/invalid `as_of` (`"tomorrow"`, `"alice@example.com"`, `12345`), bad `intent_override` (`dict`, `int`, or raw PII `"email a@b.com"`), non-dict `order_context`, unknown/legacy keys in `order_context` (`"customer_note"`, `"payment_status"`), nested dicts inside string fields, `bool`/`NaN` in `amount_minor`, invalid `placed_at` date, extra key inside money object, and raw PII (`EMAIL`, `PHONE`, `ADDRESS`) injected inside `order_context["order_status"]`.
  - **Message PII rejections (zero secret leakage):** Luhn payment cards, `EMAIL`, VN & international `PHONE`, `SSN` (`123-45-6789` matched by PHONE pattern), IPv4 (`192.168.1.42` matched by PHONE pattern), `ORDER_ID`, `ADDRESS` (`"123 Nguyen Hue Street"`, `"45 Tran Hung Dao St"`), and DB `pseudonym_map` raw secret values (`forbidden_values=("Nguyen Van A",)`).
- **Worker DB cross-check (`SuggestionWorker.process`):** Verified in [jobs.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L275-L309). A queued `SuggestionJob` carrying raw DB pseudonym value `"SecretPerson"` in `request_payload["message"]` was blocked pre-egress with `http_calls=0`, `finished=True`, `failure_code="pseudonymization_failed"`, `reason_codes=["pseudonymization_failed"]`, and `"SecretPerson"` absent from persisted `payload`. Positive end-to-end masked worker dispatch (`/v1/analyses`) with fake `PERSON` NER sent only `'Hi, I am [NAME_1] at [EMAIL_1]'` and sanitized `order_context`.

### Blocker 3 — Sentinel-Free Span Pseudonymization & One-Pass Restoration
- **Zero sentinels:** `_collision_free_sentinel()` is removed; [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L26) defensively rejects active sentinel pattern `\x00P\d+\x00` in `_assert_no_raw_pii()`.
- **Tiered non-overlapping span collection:** Verified on probes:
  - `P0`/`P1` DB entries (`ORDER_ID`, `NAME`) mask and restore cleanly (`'Reply: Priority P0 ticket for customer P1 with alice@example.com'`).
  - Short known substring (`known={"ADDRESS": ["Hue"]}`) inside `"123 Nguyen Hue Street"` yields single span `{'[ADDRESS_1]': '123 Nguyen Hue Street'}` and exact round-trip restore.
  - Customer-authored `[EMAIL_1]` literal + real `bob@example.com` produces `[LITERAL_1]` + `[EMAIL_1]` and restores without cross-contamination (`'Confirmed: Your system printed [EMAIL_1] when I typed bob@example.com'`).
  - Nested brackets (`[[EMAIL_1]]`), unclosed `[EMAIL_1`, malformed `[EMAIL_abc]`, and NUL byte (`\x00`) all mask and exact-restore cleanly.
  - One-pass `restore()` (`PLACEHOLDER.sub`) does not recursively expand `[NAME_1] -> [EMAIL_1] -> real@example.com` (`'[EMAIL_1] emailed real@example.com'`), and `PLACEHOLDER` regex supports `>999` indices (`restore("Hi [NAME_1000] and [EMAIL_1234]", ...)` -> `'Hi Alice and a@b.com'`).

---

## 3. Non-Blocking Caveats & Observations

1. **Live spaCy runtime not provisioned (`SKIPPED`):** `.venv` does not have `en_core_web_sm` installed, so [test_live_spacy_free_form_ner_masking_integration](file:///F:/Năm%203/SD/project/SupportIQ/tests/unit/test_privacy_pii.py) was `SKIPPED`. Un-stubbed local/runtime calls fail closed (`pseudonymization_failed`), and live spaCy NER detection accuracy on free-form text requires `en_core_web_sm` installation in deployment environments.
2. **Regex `ADDRESS` limitations:** `ADDRESS` pattern in [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L18) matches ASCII alphanumerics + required English street suffixes (`Street|St|...`): `"123 Nguyen Hue Street"` matches (`[ADDRESS_1]`), whereas `"123 Nguyễn Huệ Street"` (Vietnamese diacritics) and `"123 Le Loi"` (no suffix) are not matched by regex alone and rely on DB `known["ADDRESS"]` or live NER.
3. **Unbounded word match for `known` values in `pseudonymize()`:** [privacy.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L133) searches `known` strings without `\b` word boundaries (to handle concatenated/compound matches), so very short 2-character `known` names (e.g., `"An"`) can over-mask inside routine words (`"bananas"` -> `"b[NAME_2][NAME_2]as"`). Round-trip restoration remains exact and fail-closed.
4. **Cross-cutting pre-existing parity:** `service.order_context()` 6-field extraction vs `ORDER_CONTEXT_ALLOWED_SET` 10-field schema was intentionally left unchanged (`6-vs-10` parity out of Gap 3 scope).

---

## 4. Test & Invariant Verification

### Focused Pytest Suite
Command:
```sh
.\.venv\Scripts\python.exe -m pytest tests/application/test_gap3_privacy_ner_a.py tests/unit/test_privacy_pii.py tests/application/test_workflow_privacy.py tests/application/test_backend_safety_closure.py tests/unit/test_order_context_grounding.py tests/unit/test_typed_fault_propagation_a.py -v
```
Result: **`56 passed, 1 skipped` in 65.09s** (skipped test: `tests/unit/test_privacy_pii.py::test_live_spacy_free_form_ner_masking_integration`).

### Invariant SHA-256 Digests (Unchanged)
| File | SHA-256 |
|---|---|
| `apps/core_backend/safety.py` | `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000` |
| `apps/core_backend/retrieval/adapter.py` | `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f` |
| `apps/core_backend/llm/gemini.py` | `c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b` |
| `apps/ai_service/kb-release.json` | `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804` |
| `data/knowledge/approved_kb.v2.json` | `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec` |
| `apps/core_backend/config/policies/intent_policy.v2.json` | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| `.local/training-cap-20261114.json` | `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` |
| `.local/ai.env` | `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87` |
