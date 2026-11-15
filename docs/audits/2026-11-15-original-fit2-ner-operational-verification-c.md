# Original Fit2 NER Provisioning & Operational Verification Audit (Worker C)

**Verdict:** `PASS` — **NER Provisioning & Controlled Local Operational Smoke Only**  
**Baseline Commit Reviewed:** `78b72dd36fae292fa457670878f4217842717e93` (`minh`)  
**Scope Boundary:** Confirms `spacy==3.8.18` / `en_core_web_sm==3.8.0` provisioning, independent real-NER + mock-HTTP verification, and controlled local restart with external LLM drafting disabled. Does **not** certify raw classifier safety (`2/2 STOP`), whole-project acceptance, or all-PII NER recall. Out-of-scope open gaps: `order_context` Engine `6 vs 10` parity and frontend `canSendReply`.

---

## 1. Installed Wheel Provenance & Test Results

- **Package & Wheel Provenance (matches [Worker A report](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-15-original-fit2-ner-provisioning-a.md)):**
  - `spacy==3.8.18`, `en_core_web_sm==3.8.0`
  - Official Explosion URL (`direct_url.json`): `https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl`
  - SHA-256: `1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85`
- **Commands & Counts Executed Independently:**
  - `.\.venv\Scripts\python.exe -B -X utf8 scripts/native_runtime.py preflight` -> exit `0` (`Privacy NER (spaCy en_core_web_sm 3.8.0): ready.`)
  - `.\.venv\Scripts\python.exe -B -m pytest tests/application/test_gap3_privacy_ner_a.py tests/unit/test_privacy_pii.py tests/application/test_workflow_privacy.py tests/application/test_backend_safety_closure.py tests/unit/test_order_context_grounding.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_runtime_preflight.py -rs -q` -> **`66 passed`** (`77.78s`, `0 skipped`, `0 failed`)
  - `.\.venv\Scripts\python.exe -B -m pytest tests/application/test_application.py tests/e2e/test_full_pipeline.py -rs -q` -> **`49 passed`** (`84.28s`, `0 skipped`, `0 failed`)
  - `.\.venv\Scripts\python.exe -B artifacts/evaluation/original_fit2_ner_operational_c_20261115/verify_ner_provisioning_c.py` -> **`VERDICT=PASS`** (`WIRE_CALLS=2`, `15.78s`; [ner_provisioning_verification.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/original_fit2_ner_operational_c_20261115/ner_provisioning_verification.json))

### Real NER vs Mock HTTP Separation & Disclosed Recall Limits
- **Fresh subprocess real NER:** Masks English free-form `PERSON`/`GPE`/`LOC` (`Michael Johnson`, `Seattle`, `Robert Chen`, `Central Park`, `New York`) plus identifiers (`ORD-1001`, `bob@example.com`) and round-trips identically; ordinary order dates/currency pass unmasked (`pmap={}`). Fault injection (`missing_none`, `load_runtime_error`) blocks both `pseudonymize(..., require_ner=True)` and `validate_egress_payload(..., require_ner=True)`.
- **Real NER intake -> worker `httpx.MockTransport` E2E (disposable PG schema, zero live network/LLM):** Real `en_core_web_sm` masks `"Hi, I am Michael Johnson living in Seattle checking order ORD-1001."` to `"[NAME_1]"`, `"[ADDRESS_1]"`, `"[ORDER_ID_1]"`; worker makes `2` mocked HTTP calls (`/v1/analyses`, `/v1/drafts`) with zero raw PII or `pseudonym_map` on wire, and console restores `"Hello Michael Johnson in Seattle, thank you for reaching out."`. Fault-injected intake produces `draft_status="unavailable"`, `reason_codes=["pseudonymization_failed"]`, `0` extra HTTP calls, and disables `retry_suggestion`.
- **Empirical `en_core_web_sm==3.8.0` Recall Limits (Not All-PII Guarantee):**
  - `len <= 2` tokens (e.g., `"WA"` in `"Ship my package to WA today please."`) remain unmasked (`pmap={}`).
  - Non-suffixed street names (`"Deliver to 742 Evergreen Terrace quickly."`) remain unmasked (`pmap={}`).
  - Unaccented Vietnamese (`"Xin chao toi la anh nam o quan 1"`) false-positives `"Xin chao"` -> `[NAME_1]` and `"toi la anh nam o quan"` -> `[ADDRESS_1]`.
  - Accented Vietnamese (`"Tôi là Nguyễn Văn Minh ở 123 Đường Lê Lợi Quận 1"`) misses person `"Nguyễn Văn Minh"` and `"123 ... Quận 1"`, tagging only `"Đường Lê"` -> `[NAME_1]`. Regex + DB `known` metadata remain mandatory complements.

---

## 2. Controlled Local Runtime Startup, Assets & LLM Disabled Status

Recorded prior PIDs (`8680`, `36204`) were inactive. Executed `scripts/stop-app.ps1` (keeping PG untouched) followed by `scripts/start-app.ps1 -SkipInstall -SkipBuild -DisableLLM` inside a process-wait daemon (`IsDaemon: true`), spawning:
- **Process State (`.local/processes.json`):** `ai-service` PID `29708`, `backend` PID `32820` (`StartedAt: 2026-11-15T08:01:33Z`, both alive on `127.0.0.1:8002` and `127.0.0.1:8080`).
- **Evidence JSON:** [runtime_smoke_verification.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/original_fit2_ner_operational_c_20261115/runtime_smoke_verification.json)
- **`http://127.0.0.1:8080/health/ready`:** `{"status": "ready", "backend_build": "application-v1", "privacy_ner_available": true}`.
- **`http://127.0.0.1:8002/health/ready`:** `"status": "ready"`, `"llm_enabled": false`, `"retrieval_ready": true`, `"model_version": "fit2-supcon-energy-boundary-v1"`, `"model_checksum": "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa"`, `"calibration_checksum": "782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39"`, `"model_mode": "trained"`, `"model_verified": true`, `"live_llm_requests_made": 0`, `"max_live_llm_requests": 2`.
- **`http://127.0.0.1:8002/v1/asset-versions` & `8080/v1/admin/versions`:** Match `release_id="local-b1c61e8977e69230"`, `fit2-supcon-energy-boundary-v1`, Original Fit2 model/calibration digests above, `kb_version="sha256:32547457f792d6c61c4dff4493f1b55791e5a28f63a60da0eaf0d9736dfdcf0c"`, and `routing_version="sha256:8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7"`. Zero candidate activation.
- **External Provider Block Verification:** Confirmed `"llm_enabled": false` on `8002/health/ready` before any inference probe. Local `/v1/analyses` classified locally (`return_policy`, `0.9658`, `3` docs); `/v1/drafts` failed closed locally (`status="llm_unavailable"`, `failure_code="llm_not_configured"`); `live_llm_requests_made` remained `0`. Note: per-process `request_count=0` on restart is **not** any new lifetime paid budget allowance.
- **Playwright Read-Only UI Smoke:** Navigated to `http://127.0.0.1:8080/` -> rendered `/sign-in` (`200`, title `SupportIQ`, heading `Sign in to SupportIQ`), signed in read-only as synthetic `admin-1` -> rendered `/console` inbox (`20` tickets) and console navigation, signed out cleanly, closed browser. Console showed only expected pre-auth `401` on `/v1/sessions/current` and CSP `font-src 'self'` notice for embedded `data:font/woff2`. Zero external/customer actions.

---

## 3. Preserved Files & Database Invariants

- `.local/ai.env` unchanged: `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87`
- `.local/training-cap-20261114.json` unchanged (`2/2` `training_stopped: true`): `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`
- `apps/core_backend/safety.py`: `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000`
- `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
- `apps/core_backend/llm/gemini.py`: `c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b`
- `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
- `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
- `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
- **PG counts pre/post startup identical:** `accounts=89`, `orders=3`, `tickets=68`, `suggestions=78`, `audit_log_entries=342`.
