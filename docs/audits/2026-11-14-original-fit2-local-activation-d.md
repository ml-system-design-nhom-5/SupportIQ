# Original Fit2 Local Activation & Playwright Verification (Worker D)

- **Date:** 2026-11-14
- **Branch / Base Commit:** `minh` @ `697c72508d74a87e18186a2cf719555920e02885`
- **Authorization & Scope:** User-authorized local activation of **Original Fit2** (`fit2-supcon-energy-boundary-v1`) on the local runtime (`127.0.0.1:8080`, `127.0.0.1:8002`, `127.0.0.1:55432`) for direct UI observation. This is **not** production promotion or gate clearance.

---

## 1. Model Identity & Checksum Verification

### Previous Serving Model (Preserved Untouched)
- **Directory:** `artifacts/models/trained/distilbert-supportiq`
- **Pinned Version:** `v1.0.0` (prior running gateway release `local-ca030a2d70dc0da4`)
- **Checksums:**
  - `model.safetensors`: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`
  - `tokenizer.json`: `5f218e0ea9eaa9f154815cc067351fb941bea26da81bfd12af3ded3cc66fa3ff`
  - `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`

### Activated Target Model (Original Fit2 — Unmodified Weights & Calibration)
- **Directory:** `artifacts/models/candidates/reconstructed-fit2-supcon-20261113`
- **Manifest:** `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json` (`selective_calibration.v1`)
- **Model Version:** `fit2-supcon-energy-boundary-v1`
- **Checksums (Verified on disk & in live runtime):**
  - `model.safetensors`: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`
  - `tokenizer.json`: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`
  - `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
  - `calibration_manifest.json`: `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39`
- **Calibration & Rejector Metadata:** `num_labels=46` (`valid_46_label_bijection=true`), `max_length=64`, `padding="max_length"`, `truncation=true`, `temperature=1.0`, `min_temperature=1.0`, `calibrated=true`, `selective_rejector.enabled=false`.

---

## 2. Reversible Local Deployment Changes & Rollback

### Tracked vs Ignored Changes
- **Tracked code ([`apps/ai_service/main.py`](file:///F:/Năm%203/SD/project/SupportIQ/apps/ai_service/main.py)):**
  - Extended `AiSettings` to read gitignored `.local/ai.env` (after `.env`) and added optional local override fields (`supportiq_model_dir`, `supportiq_calibration_manifest_path`, `supportiq_max_live_llm_requests`, `supportiq_llm_max_attempts`), keeping all serving defaults unchanged (`None`).
  - Added startup log (`AI gateway model loaded: ...`) and runtime `model_checksum`, `calibration_checksum`, `live_llm_requests_made`, and `max_live_llm_requests` on `/health/ready` and `/v1/asset-versions`.
  - Added pre-egress thread-safe `max_requests` cap inside `AllowListedTransport` raising `httpx.RequestError("Live LLM budget exhausted")` before outbound HTTP I/O once exhausted.
- **Tracked test ([`tests/unit/test_local_fit2_activation_guard.py`](file:///F:/Năm%203/SD/project/SupportIQ/tests/unit/test_local_fit2_activation_guard.py)):**
  - Verifies default `AiSettings` stays unpinned, `AllowListedTransport` hard-caps requests, and `create_app()` loads Original Fit2 when explicitly configured.
- **Gitignored local runtime override (`.local/ai.env`, never committed):**
  - `SUPPORTIQ_MODEL_DIR=artifacts/models/candidates/reconstructed-fit2-supcon-20261113`
  - `SUPPORTIQ_CALIBRATION_MANIFEST_PATH=artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json`
  - `SUPPORTIQ_MAX_LIVE_LLM_REQUESTS=2`
  - `SUPPORTIQ_LLM_MAX_ATTEMPTS=1`

### Safe Rollback Commands (PowerShell)
```powershell
Remove-Item .local\ai.env -Force
.\scripts\stop-app.ps1
$env:PSYCOPG_IMPL="python"
$env:PATH="F:\PostgreSQL\bin;$env:PATH"
.\scripts\start-app.ps1 -SkipInstall
```
Removing `.local\ai.env` restores `ModelContainer.load()` defaults (`artifacts/models/trained/distilbert-supportiq`, SHA-256 `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`, `v1.0.0`) without modifying weights or git history.

---

## 3. Running Services, Ports & Runtime Proof

- **Launch command:** `.\scripts\start-app.ps1 -SkipInstall -SkipBuild` (with `PSYCOPG_IMPL=python` and `F:\PostgreSQL\bin` on `PATH`; frontend built via `.\scripts\start-app.ps1 -SkipInstall` prior).
- **Processes & Listening Ports:**
  - **PostgreSQL (`127.0.0.1:55432`):** `postgres.exe` PID `27860` (`Psycopg 3.3.8`, `impl: python`, `libpq 180006`).
  - **AI Gateway (`127.0.0.1:8002`):** `uvicorn apps.ai_service.main:create_app` child PID `15492` (`.local/processes.json` wrapper PID `37804`).
  - **Backend + Frontend SPA (`127.0.0.1:8080`):** `uvicorn apps.backend.main:create_app` child PID `27100` (`.local/processes.json` wrapper PID `24716`).
- **Startup Log Proof (`.local/ai.stderr.log`):**
  ```text
  INFO: AI gateway model loaded: version=fit2-supcon-energy-boundary-v1 mode=trained verified=True model_sha256=f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa calibration_sha256=782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39 release_id=local-b1c61e8977e69230 max_live_llm_requests=2
  ```
- **Live Endpoints Verified (`200 OK`):**
  - `GET http://127.0.0.1:8080/health/live` -> `{"status":"ok"}`
  - `GET http://127.0.0.1:8080/health/ready` -> `{"status":"ready","backend_build":"application-v1"}`
  - `GET http://127.0.0.1:8002/health/ready` -> `model_version="fit2-supcon-energy-boundary-v1"`, `model_checksum="f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa"`, `calibration_checksum="782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39"`, `model_mode="trained"`, `model_verified=true`, `llm_enabled=true`, `llm_configured=true`, `retrieval_ready=true`.
  - `GET http://127.0.0.1:8002/v1/asset-versions` -> `release_id="local-b1c61e8977e69230"`, `prompt_version="grounded-v3"`.

---

## 4. Playwright Real-Browser Verification

- **Engine:** `@playwright/test` (`1.64.1`) Chromium / `msedge` channel (`headless: true`, `1440x900`) against `http://127.0.0.1:8080`.
- **Evidence Folder:** `artifacts/browser/fit2-local-activation-d-20261114/`
  - Summaries: `actions_summary.json`, `console_and_network_summary.json` (trace saved locally in `playwright-trace.zip`, gitignored via `/artifacts/**/*.zip`).
  - Screenshots: `01-admin-versions.png` through `10-manager-ticket2-escalated.png`.
- **Flow Results:**
  1. **Admin `/admin/versions` (`admin-1`):** PASS — Rendered `AI service: Available`, `Backend build: application-v1`, `Release ID: local-b1c61e8977e69230`, `Model artifact: fit2-supcon-energy-boundary-v1`, `Prompts: grounded-v3`.
  2. **Customer Ticket Creation (`customer-1`, `/shop/support`):** PASS — Submitted synthetic return-policy ticket `TCK-1076` (`[SYNTHETIC LOCAL TEST D] What is the return policy and how many days do I have to return a product sold by Tiki Trading?`).
  3. **Staff Analysis, Grounded Draft, Citations & Reply (`staff-1`, `/console/tickets/TCK-1076`):** PASS —
     - Fit2 classified `Return policy` (`High · 0.932`, calibrated, top alternatives `Refund policy 0.004`, `Return product 0.003`).
     - Real Gemini (`gemini-3.5-flash-lite`) produced `Draft ready` with 1 inline citation `[1]` and 3 retrieved KB sources (`POL-RET-001 · 2.0`, `POL-RET-002 · 2.0`, `POL-REFUND-001 · 1.0`).
     - Expanded `Developer details` showing `Trace ID: 85fdee23-122a-42bd-af37-60a8926f4327`, `model_checksum`, `calibration_checksum`, `Analysis: 128 ms`, `Draft: 1656 ms`, `Llm: 1509 ms`.
     - Clicked `[1]` citation popover -> clicked `Read full document` -> verified `SourceSheet` modal (`Tiki Standard Product Return and Exchange Policy and Conditions`).
     - Clicked `Edit draft`, appended `[Synthetic local test D review verified by staff-1]`, clicked `Send reply` and confirmed -> status transitioned to `Sent reply`.
  4. **Customer Reply View & Escalation Intake (`customer-1`):** PASS — Verified `Reply from support` visible on `TCK-1076`; submitted `TCK-1077` (`[SYNTHETIC LOCAL TEST D ESCALATION] Please connect me with a human supervisor immediately regarding a damaged item dispute and compensation claim.`).
  5. **Staff Escalation (`staff-1`, `/console/tickets/TCK-1077`):** PASS — AI returned `Escalation recommended` (0 LLM calls); escalated ticket via modal (`Escalated by` warning notice rendered).
  6. **Manager Reports & Escalated Authority (`manager-1`, `/console/reports`, `/console`):** PASS — Reports page loaded cleanly; filtered `Escalated` tickets, opened `TCK-1077`, verified `Escalated by` notice and enabled `Send reply` action.
- **Browser Errors:** `pageErrors: []`, `requestFailures: []`; only expected unauthenticated initial `GET /v1/sessions/current -> 401` on `/sign-in` load before sign-in.

---

## 5. Live LLM Budget Accounting & Known Limitations

- **LLM Model Selected:** `gemini-3.5-flash-lite` (unchanged).
- **Pre-Task Global Remaining Ledger:** `3` of `24` (`21` prior used per `artifacts/evaluation/classifier_vs_serving_live_20261113/comparison_report.json`).
- **Task Cap Enforced:** `SUPPORTIQ_MAX_LIVE_LLM_REQUESTS=2`, `SUPPORTIQ_LLM_MAX_ATTEMPTS=1` in `AllowListedTransport` + `BudgetedDraftClient`.
- **Actual Live HTTP Attempts Used in This Task:** `1` (`live_llm_requests_made: 1`, `max_live_llm_requests: 2` confirmed on `/health/ready` after Playwright run). Estimated global remaining ledger: `2` of `24` (note `comparison_report.json` was not modified).
- **Known Safety / Gate Limitations:**
  - Original Fit2 is running with **`temperature=1.0`** and **`selective_rejector.enabled=false`** per `calibration_manifest.json`.
  - Independent acceptance gates remain **unmet** for production deployment (for example, `candidate_provenance_manifest.json` records `max_neg_cal_supported12_prob: 0.557692`).
  - Zero-LLM precheck (`return_policy`: `0.9324` vs `escalation`: `0.0258` on `product_information` -> `escalate`) showed expected behavior on tested synthetic prompts, while prior evaluations showed Fit2 still requires human review and does not pass production OOD/selective gates.

---

## 6. Automated Test Verification

Executed after final code and test edits (`PSYCOPG_IMPL=python`, `F:\PostgreSQL\bin` on `PATH`):
```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/unit/test_local_fit2_activation_guard.py `
  tests/application/test_gateway_version_identity.py `
  tests/unit/test_model_provenance.py `
  tests/unit/test_model_runtime_parity_b.py `
  tests/unit/test_intent_service.py `
  tests/unit/test_gemini_llm.py `
  tests/unit/test_typed_fault_propagation_a.py `
  tests/application/test_ai_boundary.py `
  -m "real_model or not real_model" -v
```
- **Result:** `161 passed in 22.42s` (0 failed, 0 skipped; `--run-live` omitted so live Gemini pytest tests remain excluded).
