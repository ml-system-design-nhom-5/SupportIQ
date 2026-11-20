# Task B Follow-up: Safe Bounded Error Messages in `IntentClient`

## Scope & Ownership
- Edited: `apps/core_backend/intent/client.py`
- Added test suite: `tests/unit/test_intent_client_safe_errors.py`
- Added report: `artifacts/evaluation/task_b_client_safe_errors_20261113/REPORT.md`
- Unchanged (strict boundary): `routing.py`, `safety.py`, `Engine`, `schemas.py`, `pipeline_runner.py`.
- Provider calls executed: **0** (all verification ran offline with `httpx.MockTransport` and unit test mocks).

## Changes Made in `apps/core_backend/intent/client.py`
1. `httpx.TimeoutException`: replaced `str(exc) or "ML inference timed out"` with bounded `"ML inference timed out"` (`failure_code="ml_timeout"`).
2. `ValueError`: replaced `str(exc) or "Invalid inference payload"` with bounded `"Invalid inference payload"` (`failure_code="invalid_model_output"`).
3. Generic `Exception`: replaced `str(exc) or ...` with bounded `f"ML inference failed ({type(exc).__name__})"` (`failure_code="ml_error"`).
4. Model version mismatch: stopped reflecting remote `resp_version` in warning logs, `IntentPrediction.model_version` (`"unknown"`), and `IntentPrediction.error` (`"Model version mismatch"`, preserving `"version mismatch"` contract and `failure_code="ml_error"`).
5. HTTP 200 payload `error`: replaced raw untrusted `data.get("error")` with `f"ML inference reported failure: {safe_failure_code}"` when error/`failure_code` is present.
6. Kept existing typed `_classify_http_status_failure` HTTP header (`X-SupportIQ-Error-Code`), JSON `detail.error_code`/`error_code`, and `408`/`504` status mapping without exception-string matching.

## Verification (RED -> GREEN)
- **RED (before `client.py` edit):**
  - `pytest tests/unit/test_intent_client_safe_errors.py -v` -> `7 failed, 2 passed in 2.03s` (confirmed fake credentials/tokens in `ReadTimeout`, `ConnectError`, `RuntimeError`, invalid JSON/`ValueError`, and `model_version`/200 `error` payloads leaked into `IntentPrediction.model_dump()`).
- **GREEN (after `client.py` edit):**
  - `pytest tests/unit/test_intent_client_safe_errors.py tests/unit/test_intent_client_rejector_routing.py tests/unit/test_intent_service.py tests/unit/test_pipeline_runner_safety_b.py tests/integration/test_completion_deadline.py tests/unit/test_routing.py -v` -> `95 passed in 12.83s`.
