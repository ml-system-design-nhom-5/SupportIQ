# Rank 2 Review: `SuggestionWorker` Bounded Concurrency & HTTP Reuse (Worker C)

**Verdict:** `PASS` (bounded concurrency, thread/session/lease safety, and PG `SKIP LOCKED` verified; **no blanket SLA or whole-system acceptance claim**)
**Reviewed Commit SHA:** `21cb8fe789f6f3a408ee98a1b0110fc98234fea3` (`perf(worker): add bounded SuggestionWorker concurrency and pooled httpx reuse`)
**Worker B Record:** [2026-11-14-suggestion-worker-concurrency-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-suggestion-worker-concurrency-b.md)

## 1. Audited Artifact Hashes (`21cb8fe` == Working Tree)

| File | Observed SHA-256 |
|---|---|
| [config.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/platform/config.py) | `0bef9385c9fc611f041c2c721df43ba0d47c4c2e643cc6ea4a3aee0eccf2936d` |
| [main.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/main.py) | `2187056a66f5fbe4a7a5c9b12459e2cffc4eabd074b5451f3250e533286d8dc` |
| [jobs.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py) | `ca725932bbcf40fbf11e3565b3746c81a34a70371f83830bd904b37a180fbc01` |
| [test_suggestion_worker_concurrency.py](file:///F:/Năm%203/SD/project/SupportIQ/tests/unit/test_suggestion_worker_concurrency.py) | `51caa4a24343fc415a810efe5e4cb0ffc243c3e5113a39d1b5ca46f66752ece5` |

---

## 2. Correctness, Concurrency & Security Verification

- **Slot-bounded scheduling (`jobs.py:196-226`):** `run()` uses `ThreadPoolExecutor(max_workers=self._concurrency)` and checks `len(in_flight) < self._concurrency` before calling `claim()`, so waiting tickets stay unclaimed in DB instead of expiring `job_lease_ms` in an unbounded executor queue. When saturated, `wait(in_flight, timeout=min(0.05, poll_s), return_when=FIRST_COMPLETED)` wakes as slots free rather than sleeping a full `job_poll_interval_ms`. `claim()` (`jobs.py:228-258`) skips superseded (`ticket.current_suggestion_id != suggestion.suggestion_id`) and exhausted (`attempts >= 3`) jobs via `continue` so stalled rows do not starve eligible work behind them.
- **Session isolation, DB pooling & `Settings` defaults:** Every `claim()` and `store()` call opens its own short-lived `Session` via `database.transaction()` (`database.py:32-35`), with per-transaction commit/rollback; zero `Session` objects cross threads. `Settings.job_concurrency` (`config.py:28`) defaults to `4` with `ge=1, le=16` (`ValidationError` verified on `0`, `17`, `-1`), and `create_app` (`main.py:39-42`) sets `pool_size = max(5, settings.job_concurrency + 2)` (`18` verified at `job_concurrency=16`) for PostgreSQL while skipping pool kwargs on SQLite. `_process_claimed` (`jobs.py:189-194`) isolates per-task errors so sibling concurrent tasks continue cleanly, and `MetricsRegistry` (`observability.py:97-280`) synchronizes under `self._lock`.
- **`httpx.Client` thread/lifetime safety & customer isolation:** `_post_ai` (`jobs.py:145-188`) lazily initializes one pooled `_owned_http_client` under `_client_lock` with `trust_env=False` and `httpx.Limits(max_connections=max(10, self._concurrency * 2), max_keepalive_connections=max(5, self._concurrency))`, runs concurrent `.post(url, json=payload, timeout=timeout_s)` calls outside `_client_lock`, preserves non-pooled fallback for monkeypatched test clients, and closes owned clients only after `ThreadPoolExecutor` (`wait=True`) / `thread.join()` completes (`jobs.py:135-143, 226`) without closing caller-injected clients. Per-ticket authorization/ownership (`service.py`, `main.py`) is untouched; `apps/ai_service/main.py` emits no `Set-Cookie` headers, and `_post_ai` sends only pseudonymized JSON payloads.
- **Stale lease, cancellation & PG `FOR UPDATE SKIP LOCKED`:** `store()` (`jobs.py:373-380`) locks `Ticket` then `SuggestionJob` (`with_for_update()`) and drops late writes whenever `ticket.current_suggestion_id != identifier`, `job.lease_token != token`, or `lease_until <= utcnow()`. HTTP failures resolve `unavailable` in 1 attempt (no retry multiplication). `test_pg_skip_locked_concurrent_workers_no_duplicate_claims_or_suggestions` (`test_suggestion_worker_concurrency.py:371-482`) executed against a live disposable PostgreSQL schema (`test_worker_pg_*`, dropped in `finally`) with `2` workers (`job_concurrency=2` each, `8` tickets) -> `8` drafts, `8` `attempts=1` jobs, `16` audit entries. Our independent live PG takeover probe (`job_lease_ms=250`, Attempt 1 stalled `650ms`) further confirmed `w2` reclaimed `attempts=2` and wrote `Reply WINNER-ATTEMPT-2.` while `w1`'s stale write was dropped (`part_audits=3`).

### Non-Blocking Observations (`Low`)
1. **`Low` — [`apps/backend/tickets/jobs.py:169`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L169):** Pooled `httpx.Client` (`0.28.1`) keeps a default mutable cookie jar; our mock probe confirmed an upstream `Set-Cookie` header (`sid=cust1`) would attach `Cookie: sid=cust1` on a subsequent request to `ai_service_base_url`. Not exploitable in SupportIQ's current topology because `apps/ai_service/main.py` is an internal stateless JSON service that sets/reads no cookies, but clearing cookies / using a stateless jar is trivial defense-in-depth if ever touched.
2. **`Low` — [`apps/backend/tickets/jobs.py:229-258`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L229-L258):** `claim()`'s `while True:` skip loop over superseded/exhausted jobs does not re-check `self.stop_event.is_set()` between `continue` iterations (bounded by existing backlog size).
3. **`Low` — [`apps/backend/tickets/jobs.py:114-143`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L114-L143):** `start()` does not guard against double-start if a previous worker thread were still alive after a `join(timeout=join_timeout)` timeout (safe under `main.py`'s single-start lifespan).

---

## 3. Verification Commands & Capacity Limits

1. **Focused Backend Suite (live PG `SKIP LOCKED` ran, not skipped):**
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_suggestion_worker_concurrency.py tests/application/test_application.py tests/application/test_backend_safety_closure.py tests/unit/test_typed_fault_propagation_a.py tests/unit/test_order_context_grounding.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_pagination_pushdown.py -v`
   - Result: **84 passed in 69.19s (0:01:09)** (`0` failed, `0` skipped).
2. **Independent Disposable Probes (no repo edits, `0` live LLM calls):**
   - `Settings` bounds/default & `create_app` PG pool size (`pool_size=18` at `job_concurrency=16`): passed.
   - Live PG lease takeover probe (`test_worker_c_probe_*`, `job_lease_ms=250`, Attempt 1 `650ms`): `attempts=2`, `finished=True`, `draft_text="Reply WINNER-ATTEMPT-2."`, `part_audits=3`.
   - Shared `httpx.Client` cookie-jar probe (`httpx==0.28.1`): confirmed `REQ2_COOKIE: sid=cust1` if `Set-Cookie` returned.
   - Deterministic `5.0s`-delay SQLite benchmark (`job_concurrency=4`, `job_poll_interval_ms=20`, `0.03s` `/v1/analyses` + `5.0s` `/v1/drafts`):
     - `4` tickets (`4` slots): `wall = 5154.4ms`, `e2e min/p95/max = 5098.4 / 5160.3 / 5160.3ms` (reproduces B's `~5.25s`).
     - `10` tickets (`4` slots, `3` waves): `wall = 15361.5ms`, `e2e min/p95/max = 5101.6 / 15344.4 / 15344.4ms` (reproduces B's `~15.4s` -> **exceeds `12s` `p95` SLA**).
3. **Unresolved Latency & External LLM Uncertainty:**
   - Fixture timings isolate worker scheduling overhead only and **must not** be extrapolated to a live SLA. Under sustained `5s+` LLM latency, bursts above `4` concurrent tickets still breach `12s`, and actual live Gemini/Hydrogen tail latency/retry behavior (`0` live calls run here) remains external runtime uncertainty.

---

## 4. Smallest Next Reliability / Latency Task

- Keep **circuit-breaker** and **eliminating duplicate `Engine._analyse()`** (`~30ms` CPU) **deferred** until live runtime telemetry warrants them.
- **Smallest next task:** Address **Rank 3** ([`apps/core_backend/safety.py`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/safety.py) `_is_safe_uncited_sentence()` rejecting benign polite openings/closings mentioning `"order"`/`"policy"` as `uncited_claim`), preventing `5–10s` LLM drafts from being unnecessarily discarded as `llm_unavailable` — followed by **Rank 4** telemetry fixes (`reports.py` `cost_micro_usd`, `ensure_utc`, `summary()` N+1).
