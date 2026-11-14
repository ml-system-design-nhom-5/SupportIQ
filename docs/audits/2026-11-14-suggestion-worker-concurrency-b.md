# Worker B Evidence Record: Bounded `SuggestionWorker` Concurrency & HTTP Connection Reuse

Fixes Rank 2's backend serial-queue bottleneck documented in [2026-11-14-non-model-bottlenecks-c.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-14-non-model-bottlenecks-c.md).

## Implementation Summary

1. **Bounded Configurable Worker Concurrency (`apps/backend/platform/config.py`, `apps/backend/main.py`, `apps/backend/tickets/jobs.py`)**:
   - Added `Settings.job_concurrency: int = Field(default=4, ge=1, le=16)` (`SUPPORTIQ_JOB_CONCURRENCY`), conservative to local capacity and PostgreSQL pooling (`engine_kwargs["pool_size"] = max(5, settings.job_concurrency + 2)` in `apps/backend/main.py`).
   - Updated `SuggestionWorker.run()` to execute claimed tickets via `ThreadPoolExecutor(max_workers=self._concurrency)` with strict slot-bounded claiming (`len(in_flight) < self._concurrency` before calling `claim()`). Queued tickets remain unclaimed in DB until a slot frees, preventing leases (`job_lease_ms`) from expiring and burning retry attempts inside an unbounded executor queue.
   - Kept independent short-lived DB sessions per transaction (`database.transaction()`), preserving `FOR UPDATE SKIP LOCKED`, `ticket.current_suggestion_id` checks, `lease_token`/`lease_until` ownership guards, and thread-safe `MetricsRegistry._lock`.
   - When all worker slots are busy, `run()` waits on `concurrent.futures.wait(..., return_when=FIRST_COMPLETED)` instead of sleeping a full poll interval between waves.
2. **Reused Managed HTTP Client & Clean Shutdown (`apps/backend/tickets/jobs.py`)**:
   - Added thread-safe pooled `httpx.Client` reuse in `_post_ai` (`trust_env=False`, `httpx.Limits(max_connections=max(10, self._concurrency * 2), max_keepalive_connections=max(5, self._concurrency))`), plus optional `http_client=` injection while remaining backward-compatible with legacy mock `httpx.Client` stand-ins.
   - `close()` sets `stop_event` (halting new claims and skipping unstarted draft HTTP calls), joins the dispatcher until active executor tasks finish (`executor.shutdown(wait=True)`), and closes worker-owned HTTP clients afterward without closing caller-injected clients.
   - `_process_claimed` isolates per-task exceptions so one ticket failure never aborts sibling concurrent tasks.

## Deferred Optional Changes
- **Circuit-breaker framework**: Deferred; requires cross-worker state/half-open policy calibration against real provider telemetry to avoid false-opening manual fallback on single-ticket errors.
- **Trusted client-supplied analyses / eliminating duplicate `Engine._analyse()`**: Deferred; local CPU `_analyse()` cost (~30ms in C's audit) is minor relative to multi-second LLM calls, and passing pre-computed analyses into `/v1/drafts` adds a cross-service provenance trust boundary.
- **Single-call `/v1/drafts` API redesign**: Deferred; keeping `/v1/analyses` before `/v1/drafts` preserves early abstain/escalate short-circuiting and retains retrieved KB sources if drafting fails.

## Modified Files & SHA-256 Hashes
| File | SHA-256 |
| --- | --- |
| `apps/backend/platform/config.py` | `0bef9385c9fc611f041c2c721df43ba0d47c4c2e643cc6ea4a3aee0eccf2936d` |
| `apps/backend/main.py` | `2187056a66f5fbe4a7a5c9b12459e2cffc4eabd074b5451f3250e533286d8dc` |
| `apps/backend/tickets/jobs.py` | `ca725932bbcf40fbf11e3565b3746c81a34a70371f83830bd904b37a180fbc01` |
| `tests/unit/test_suggestion_worker_concurrency.py` | `51caa4a24343fc415a810efe5e4cb0ffc243c3e5113a39d1b5ca46f66752ece5` |

## Verification & Deterministic Capacity Benchmark

### Focused Backend Test Suite (Post-Final-Edit)
- Command: `.venv\Scripts\python -m pytest tests/unit/test_suggestion_worker_concurrency.py tests/application/test_application.py tests/application/test_backend_safety_closure.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_order_context_grounding.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_pagination_pushdown.py -q`
- Result: **84 passed in 72.51s** (`0` failed, `0` skipped), including `6` new tests in `test_suggestion_worker_concurrency.py`:
  - concurrent ticket overlap (`job_concurrency=3`), max in-flight claim bound (`<= 3`), single shared `httpx.Client` reuse & `is_closed` cleanup;
  - single-task `ConnectError` isolation without stalling sibling tickets;
  - mid-flight shutdown leaving unclaimed jobs untouched (`attempts=0`, `lease_until=None`);
  - multi-wave `job_lease_ms=500` stability (`> 0.55s` wall time, `attempts=1` on all `6` jobs);
  - stale lease token and superseded `current_suggestion_id` dropping late `store()` writes;
  - live disposable PostgreSQL schema (`test_worker_pg_*`, dropped in `finally`) running `2` concurrent `SuggestionWorker` instances (`job_concurrency=2` each) across `8` tickets via `FOR UPDATE SKIP LOCKED` with `8` unique suggestions, `8` claims (`attempts=1`), and `16` audit entries.

### Deterministic Simulated `5.0s`-Delay Benchmark (No Live Provider Calls)
Workload: disposable SQLite DB (`job_poll_interval_ms=20`, `job_lease_ms=20000`, `job_concurrency=4`), `httpx.MockTransport` with `0.03s` `/v1/analyses` + `5.0s` `/v1/drafts` simulated delay, `0` live Gemini calls:

| Workload | Wall Time | Queue Wait (`min / p50 / p95 / max`) | Service Time (`min / p50 / p95 / max`) | End-to-End (`min / p50 / p95 / max`) |
| --- | --- | --- | --- | --- |
| `4` tickets, `4` slots | `5255.1ms` | `19.9 / 38.3 / 81.2 / 81.2ms` | `5125.6 / 5148.0 / 5164.3 / 5164.3ms` | `5145.5 / 5186.3 / 5245.5 / 5245.5ms` |
| `10` tickets, `4` slots (`3` waves) | `15386.2ms` | `13.7 / 5117.2 / 10304.1 / 10304.1ms` | `5059.4 / 5091.7 / 5174.8 / 5174.8ms` | `5092.9 / 10209.9 / 15367.7 / 15367.7ms` |

- **Capacity interpretation:** With `4` concurrent slots and a `5.0s` simulated draft delay, a `4`-ticket burst finishes near `5.26s` (`e2e p95 = 5,245.5ms`), whereas a `10`-ticket burst requires `3` waves (`15.39s` wall time, `e2e p95 = 15,367.7ms`) and **cannot** meet `p95 <= 12s` under sustained `5s+` external provider latency. External provider latency, `503` failures, and `10s` retry budgets remain an external SLA variable separate from worker pool concurrency.

## Remaining Risks & Scope Boundary
- No live Gemini API calls, full-suite pytest rerun, DB migrations, service restarts, or live user DB writes were performed.
- On SQLite (without PostgreSQL `FOR UPDATE SKIP LOCKED`), tests prove single-dispatcher concurrency and lease isolation rather than cross-process row locking; cross-worker `SKIP LOCKED` is proven in the disposable PostgreSQL test above.
- All pre-existing Worker A edits, `.gitkeep` deletion, evaluation artifacts, and `*.pptx` files remain untouched.
