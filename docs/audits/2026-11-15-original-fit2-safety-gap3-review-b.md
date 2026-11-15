# Security & Semantic Review B: Safety Gap 3 — Strict Privacy / NER Fail-Closed & Literal Collision Hardening (`98368a6f`)

- **Reviewer:** Worker B (Security & Semantic Review)
- **Target Commit:** `98368a6f401c2c377292b55a7ade56f191c88fc4` on branch `minh`
- **Baseline:** `d3c4c2a0b6ac5cf789ef409305345c7154acc1da` (Gap 2 verified)
- **Verdict:** **BLOCK** (3 concrete security/correctness blockers in egress gating, worker payload validation, and sentinel-aware masking)

## 1. Blocking Security & Correctness Defects

### Blocker 1 (CRITICAL): `require_privacy_ner=False` + remote `ai_service_base_url` allows raw PII HTTP egress
- **Locations:** `apps/backend/platform/config.py:23-24`, `apps/backend/tickets/service.py:105-109`, `apps/backend/tickets/jobs.py:261-264`.
- **Defect:** `Settings` permits `require_privacy_ner=False` (`SUPPORTIQ_REQUIRE_PRIVACY_NER=false`) alongside any non-loopback / remote `ai_service_base_url` without rejecting the combination or overriding strictness before remote egress. Both `create_suggestion()` (`service.py:108`) and `SuggestionWorker.process()` (`jobs.py:262-264`) blindly honor `getattr(settings, "require_privacy_ner", True)`.
- **Observed Probe (`probe_gap3_privacy_b.py` `[PROBE A]`):** With `Settings(ai_service_base_url="https://remote-ai.prod.example.com", require_privacy_ner=False)` and `en_core_web_sm` absent, customer intake for `"Customer Nguyen Minh Tuan at 45 Tran Hung Dao wants status update."` created `jobs_created=1` with unmasked `queued_msg='Customer Nguyen Minh Tuan at 45 Tran Hung Dao wants status update.'`, and `SuggestionWorker.process()` executed `egress_calls=1` to `https://remote-ai.prod.example.com/v1/analyses` with **`raw_pii_leaked=True`**.
- **Required Fix:** Reject or override `require_privacy_ner=False` whenever `ai_service_base_url` is set and non-loopback/non-test-offline (and enforce fail-closed strict NER in `SuggestionWorker.process()` independent of untrusted opt-out flags for remote URLs). Only explicit offline/loopback test environments should ever opt out.

### Blocker 2 (HIGH): `validate_egress_payload()` omits `PHONE`, `ADDRESS`, `order_context`, and extra/nested fields
- **Locations:** `apps/backend/tickets/privacy.py:166-180`, `apps/backend/tickets/jobs.py:262-266`.
- **Defect:** `validate_egress_payload()` only inspects `payload.get("message")` against Luhn `CARD` and `_HIGH_SPECIFICITY_KINDS` (`{"EMAIL", "ORDER_ID", "TRACKING_ID", "TRANSACTION_ID"}`).
  1. Unmasked `PHONE` and `ADDRESS` patterns in `IDENTIFIER_PATTERNS` are never checked on `message`.
  2. Top-level keys (`{"message", "order_context", "as_of", "intent_override"}`), `payload["order_context"]` (allowlisted 10-field identifier-free contract `ORDER_CONTEXT_ALLOWED_SET`), and arbitrary nested strings/objects are never validated before `_post_ai()` transmits the full `payload` dict.
- **Observed Probe (`probe_gap3_privacy_b.py` `[PROBE B]`):**
  - `{"message": "Call +84901234567 at 123 Nguyen Hue Street regarding shipment.", ...}` passed `validate_egress_payload(..., require_ner=False)` (`raw_phone_address_msg_bypassed=True`).
  - A forged/legacy payload `{"message": "Where is [ORDER_ID_1]?", "order_context": {"order_status": "shipped", "customer_name": "Nguyen Van A", "phone": "+84901234567", "shipping_address": "123 Le Loi Street", "order_id": "ORD-1001"}, "unexpected_nested": {"email": "leak@example.com"}}` passed **`validate_egress_payload(..., require_ner=True)`** even with strict NER active (`forged_order_context_and_nested_pii_bypassed_even_strict_true=True`).
- **Required Fix:** Validate the full egress payload schema (strict allowed top-level keys, `order_context` strictly matching `ORDER_CONTEXT_ALLOWED_SET` with no PII/identifiers, recursive string scan across nested values, and `PHONE` + `ADDRESS` checks in `validate_egress_payload()`).

### Blocker 3 (MEDIUM-HIGH): Sentinel corruption via `known` values matching `P\d+` & Step 3 breaking `ADDRESS` regex
- **Locations:** `apps/backend/tickets/privacy.py:85-155`.
- **Defect 3A:** Steps 3–5 run `re.sub(..., result)` over the full intermediate `result` string without excluding existing `f"{sentinel}P{n}{sentinel}"` spans. Because `\x00` does not block substring matching (and counts as `\W` for word boundaries), any `known` DB value such as `"P0"` or `"p1"` (or a 3+ char NER token like `"P10"`) matches *inside* active sentinels.
- **Observed Probe (`probe_gap3_privacy_b.py` `[PROBE C1]`):** `pseudonymize("Hi Alice, email alice@example.com.", {"NAME": ["Alice", "P0"]}, require_ner=False)` corrupted `\x00P0\x00` into `\x00\x00P2\x00\x00`, producing `masked='Hi [NAME_1], email \x00[NAME_2]\x00.'` (raw NUL bytes in egress) and `restore='Hi Alice, email \x00P0\x00.'` (`corrupted=True`).
- **Defect 3B:** Running `known` DB substitution (Step 3) globally before `ADDRESS`/`PHONE` regexes (Step 5) lets short `known` substrings fragment regex-detectable addresses (`[PROBE C2]`: `known={"NAME": ["Hue"]}` on `"Deliver to 123 Nguyen Hue Street"` yielded `'Deliver to 123 Nguyen [NAME_1] Street'`, leaking `"123 Nguyen"`).
- **Required Fix:** Tokenize/apply regex & `known` substitutions only across non-sentinel spans (never inside already-wrapped sentinel markers), and detect `ADDRESS`/`PHONE` spans before splitting them with shorter `known` values (or resolve all spans by longest-match priority on the unmasked text).

## 2. Verified Non-Blocking Controls & Invariants

- **Strict Default & Env Parsing (PASS):** `Settings()` defaults `require_privacy_ner=True` (`config.py:24`); `SUPPORTIQ_REQUIRE_PRIVACY_NER=""` raises `ValidationError`. Note `.env` and `.local/backend.env` do not weaken `require_privacy_ner` (`SUPPORTIQ_REQUIRE_PRIVACY_NER` unset).
- **Missing/Failing NER Under `require_privacy_ner=True` (PASS):** Missing spaCy, load exception, inference exception, or cached `_SPACY_NLP = False` fails closed -> `0` `SuggestionJob` rows, `request_payload["message"] == ""`, `0` outbound AI HTTP calls, `reason_codes=["pseudonymization_failed"]`, `retry_suggestion` disabled (`422`), sticky Gap 2 `is_authority_required` preserved (`403`), and manual workflow intact. Blocking backend->AI egress also conservatively protects downstream external Gemini LLM calls (`ai_service`).
- **Literal / Index / One-Pass `restore()` Hardening (PASS where non-`P\d+`):** Customer literals (`[EMAIL_1]`, `[LITERAL_1]`, `[[EMAIL_1]]`), `\x000\x00`, `>999` indices (`[EMAIL_1234]`), unclosed/malformed tokens (`[NAME_1`, `[NAME_0]`), unknown invented placeholders (`[NAME_99]`), Unicode, `1..4000` length limits, single-pass non-recursive `restore()`, and zero PII in logs/API errors passed (`[PROBE C3]` & `test_gap3_privacy_ner_a.py`).
- **Fixture Opt-Outs & Test Scope:** All `11` modified existing test files apply `require_privacy_ner=False` / `require_ner=False` / `SUPPORTIQ_REQUIRE_PRIVACY_NER="false"` strictly in offline/mocked tests (preserving strict default on `test_gap3_privacy_ner_a.py`, `test_deterministic_ner_adapter_masks_free_form_person`, and `test_live_spacy_free_form_ner_masking_integration`). However, the `1` skipped test (`test_live_spacy_free_form_ner_masking_integration`) confirms **live spaCy NER is unproven in `.venv`**.
- **Operational Cost When Unprovisioned:** Until `spaCy` + `en_core_web_sm` are provisioned in the runtime image, strict `require_privacy_ner=True` forces all live tickets into `pseudonymization_failed` manual handling (no AI analyses/drafts).
- **Invariants & Scope Verified Unchanged:** `git diff --name-only d3c4c2a..98368a6f` shows zero edits to `apps/core_backend/`, `apps/ai_service/`, `apps/frontend/`, models, KB, policy, or `.local/`.
  - `apps/core_backend/safety.py`: `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000`
  - `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
  - `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
  - `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
  - `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
- **Tests Run on `98368a6f`:**
  - `.\.venv\Scripts\python.exe -m pytest tests/application/test_gap3_privacy_ner_a.py tests/unit/test_privacy_pii.py tests/application/test_workflow_privacy.py tests/application/test_backend_safety_closure.py -v`: **30 passed, 1 skipped** (`44.78s`; skip = `test_live_spacy_free_form_ner_masking_integration` because `spaCy`/`en_core_web_sm` is uninstalled).
  - Adversarial scratch probe (`probe_gap3_privacy_b.py` against PG + FastAPI `TestClient`): reproduced **Blocker 1 (`raw_pii_leaked=True`)**, **Blocker 2 (`raw_phone_address_msg_bypassed=True`, `forged_order_context_and_nested_pii_bypassed_even_strict_true=True`)**, and **Blocker 3 (`corrupted=True`, `street_fragment_leaked=True`)**.

## 3. Next Step Before Worker C Closure

Return to Worker A to remediate Blockers 1–3 (`config.py`/`service.py`/`jobs.py` remote-URL + offline opt-out fail-closed enforcement, full-payload + `PHONE`/`ADDRESS`/`order_context` validation in `validate_egress_payload()`, and sentinel-safe span replacement in `pseudonymize()`), re-verify via Worker B, and then proceed to Worker C independent privacy closure (plus `spaCy` + `en_core_web_sm` provisioning in deployment).
