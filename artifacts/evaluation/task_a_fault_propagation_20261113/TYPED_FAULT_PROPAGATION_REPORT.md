# Task A Report — Guard Review Corrections: Typed Fault Propagation (`c4520c1`)

**Dispatch:** `ctx_8cfe8ef31c18` (`task_b835116dd3c1`)  
**Branch / Base HEAD:** `MINHDZVODICH/supportiq-final-routing` at `f97baf1` (matches root `c4520c1` under `apps/`)  
**Runtime / Provider calls:** Python 3.12 (`F:\Năm 3\SD\project\SupportIQ\.venv\Scripts\python.exe`), `0` live provider calls, `0` model fits.

---

## 1. Scope & Owned Code Changes

Only Task A-owned files were modified:

1. **[`apps/core_backend/retrieval/adapter.py`](../../../apps/core_backend/retrieval/adapter.py)**
   - Added `BOUNDED_RETRIEVAL_REASON_CODES` and `_filter_bounded_reasons()` so no raw exception strings or arbitrary reason values cross the retrieval return boundary.
   - In `RetrievalAdapter.__init__`: sanitized `self.encoder_error = type(e).__name__` and warned only with `type(e).__name__` (never raw `str(e)` or credentials). Invalid optional approval metadata records `reason="invalid_approval_metadata"` in `quarantined_docs`.
   - In `RetrievalAdapter.retrieve()`:
     - Missing `self.encoder` returns `{"status": "encoder_unavailable", "evidence": [], "reason_codes": ["encoder_unavailable"], "has_conflict": False}` (no `"error"` key).
     - Exceptions raised by `search_policies()` or returned via `res.status == "error"` / `"encoder_failed"` / `"encoder_failure"` return `{"status": "encoder_failure", "evidence": [], "reason_codes": ["encoder_failure", "encoder_failed"], "has_conflict": False}` and strip raw exception text from `index.py`.
     - Missing/expired/low-relevance evidence remains distinct (`empty_kb`, `no_match`, `no_evidence` with bounded codes such as `below_relevance_threshold`).

2. **[`apps/ai_service/main.py`](../../../apps/ai_service/main.py)**
   - Added `_BOUNDED_GATEWAY_CODES`, `_gateway_http_error()`, and `_execute_gateway_call()` wrapping `/v1/analyses` and `/v1/drafts`:
     - Unready ML model (`engine()`) raises HTTP `503` with `detail.error_code = "ml_unavailable"`, `detail.reason_codes = ["ml_unavailable", "ai_service_unavailable"]`, and header `X-SupportIQ-Error-Code: ml_unavailable`.
     - `TimeoutError` or `exc.code == "ml_timeout"` raises HTTP `504` (`"ml_timeout"`).
     - Exceptions carrying an allowlisted `exc.code` in `_BOUNDED_GATEWAY_CODES` raise HTTP `503` with canonical error code (`"encoder_failed"` normalizes canonical `error_code="encoder_failure"` while retaining `["encoder_failure", "encoder_failed", "ai_service_unavailable"]`).
     - Any other runtime/unexpected exception raises HTTP `503` with `error_code="ml_error"` and generic message (never HTTP `500` or raw exception/credential strings).

3. **[`apps/backend/tickets/jobs.py`](../../../apps/backend/tickets/jobs.py)**
   - Added `_BOUNDED_REMOTE_FAULT_CODES` and expanded `AI_REASONS` to allow `"ml_timeout"`, `"ml_error"`, `"ml_unavailable"`, `"encoder_unavailable"`, `"encoder_failure"`, `"encoder_failed"`, `"ai_service_unavailable"`, `"llm_timeout"`, `"llm_rate_limited"`, `"llm_insufficient_evidence"`, `"selective_rejected"`, `"low_margin"`, `"invalid_model_output"`, and `"explicit_human_request"` alongside existing routing/drafting reasons.
   - Added `_classify_http_failure(exc)` mapping `httpx.TimeoutException` -> `ml_timeout`, `httpx.HTTPStatusError` (reading bounded `X-SupportIQ-Error-Code` or allowlisted `detail`) -> typed `failure_code` + `"ai_service_unavailable"` compatibility alias, and transport/validation failures -> `"ai_service_unavailable"` without exposing raw exception text.
   - Updated `SuggestionWorker.process()` and `SuggestionWorker.store(..., failure_info=None)` to record `"failure_code"`, preserve `"ai_service_unavailable"` in `"reason_codes"`, keep `status="unavailable"` and manual `staff_note` so existing `retry_suggestion` and `send_reply` workflows remain functional.

4. **[`tests/unit/test_typed_fault_propagation_a.py`](../../../tests/unit/test_typed_fault_propagation_a.py)**
   - Added 8 offline pytest items (`test_retrieval_adapter_encoder_unavailable_bounded_no_raw_error`, `test_retrieval_adapter_runtime_encoder_failure_preserves_bounded_codes_without_raw_exception`, `test_retrieval_adapter_missing_evidence_remains_distinct_from_encoder_faults`, 2 parametrized `/v1/analyses` & `/v1/drafts` gateway fault tests, `test_jobs_ai_reasons_accepts_typed_fault_codes_and_rejects_unbounded`, `test_jobs_worker_propagates_typed_faults_with_compatibility_on_synthetic_db`, and `test_cross_customer_order_intake_returns_404_with_zero_ticket_creation`) running on isolated temporary SQLite DB (`tmp_path`) and mocked transport/encoders (`8 passed in 17.08s`).

No edits were made to Worker B files (`apps/ai_service/engine.py`, `apps/core_backend/orchestration/pipeline_runner.py`), `pipeline/evaluation/`, or `data/`.

---

## 2. Coordinator & Cross-Worker Contract Alignment

- **Coordinator approval:** `msg_ba192a42db70` approved the concrete Stage A typed fault contract protocol, and `msg_d11e5e635e37` confirmed B's acceptance (`msg_8d6886a84ff9`).
- **Worker A <-> Worker B alignment:** `msg_f77e8c196982` -> accepted in `msg_27ccb3d2b022` (Worker B, `ctx_7c618e86a674`), confirmed via `msg_07005e06bef6` and status `msg_c666762db35b`.
- Worker B retains downstream responsibility for inspecting `RetrievalAdapter.retrieve()` `status`/`reason_codes` inside `Engine._analyse()` / `PipelineRunner` (`encoder_unavailable`, `encoder_failure`/`encoder_failed`) and propagating `ml_timeout` / `ml_error` in `PipelineRunner`.

---

## 3. Verification Results

### Passed Offline Unit, Integration, and Non-PG Application Suites (after final edit)

Command (targeted Stage A suite):
```powershell
$env:PSYCOPG_IMPL='python'; & 'F:\Năm 3\SD\project\SupportIQ\.venv\Scripts\python.exe' -m pytest -q tests/unit/test_typed_fault_propagation_a.py
```
Result: **`8 passed in 17.08s`** (0 failed, 0 skipped).

Command (Stage A + 13 affected suites):
```powershell
$env:PSYCOPG_IMPL='python'; & 'F:\Năm 3\SD\project\SupportIQ\.venv\Scripts\python.exe' -m pytest -q tests/unit/test_typed_fault_propagation_a.py tests/unit/test_semantic_retrieval.py tests/unit/test_retrieval_grounding_b2.py tests/application/test_gateway_version_identity.py tests/application/test_workflow_privacy.py tests/application/test_ai_boundary.py tests/integration/test_routing_retrieval.py tests/unit/test_completion_routing.py tests/unit/test_completion_retrieval.py tests/unit/test_completion_http_clients.py tests/unit/test_retry_draft.py tests/unit/test_routing_safety_regressions.py tests/unit/test_system_contracts.py tests/unit/test_system_execution.py
```
Result: **`153 passed in 23.03s`** (0 failed, 0 skipped).

### PostgreSQL Application Suites (`tests/application/test_backend_safety_closure.py`, `tests/application/test_application.py`)

Command:
```powershell
$env:PSYCOPG_IMPL='python'; $env:SUPPORTIQ_APPLICATION_SECRETS='F:/Năm 3/SD/project/SupportIQ/.local/application.json'; & 'F:\Năm 3\SD\project\SupportIQ\.venv\Scripts\python.exe' -m pytest -q tests/application/test_backend_safety_closure.py tests/application/test_application.py
```
Result: **`2 passed, 28 errors in 6.30s`**.  
All 28 PostgreSQL-fixture tests errored during fixture setup (`pg_application` / `create_engine`) because `libpq library not found` under `PSYCOPG_IMPL=python` (PostgreSQL client `libpq.dll` is not installed in `C:\Program Files\PostgreSQL` on this host) and default `psycopg_binary` is blocked by Windows Application Control (`DLL load failed while importing pq: An Application Control policy has blocked this file`). No tests ran against live PostgreSQL in this environment.

---

## 4. Explicit Boundary Note: Cross-Customer Order Intake (`unc-track_order-05`)

- `POST /v1/shop/tickets` with another customer's order (`ORD-1002` in `test_cross_customer_order_intake_returns_404_with_zero_ticket_creation`) intentionally returns HTTP **`404`** (`type="urn:supportiq:problem:not-found"`) and creates **`0`** tickets and **`0`** suggestions.
- This privacy-enforcing denial is intentionally preserved and is incompatible with any frozen benchmark expectation expecting `"escalate"` at the downstream AI-pipeline stage for that intake scenario; no privacy guard was weakened and no fake PASS was introduced.
