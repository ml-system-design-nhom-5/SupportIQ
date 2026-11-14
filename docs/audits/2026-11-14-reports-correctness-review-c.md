# Reports Correctness Review (Worker C)

- **Reviewed commit:** `cf58f08a810f1cfa8ec587ddddc239c35ad7a84d` (`fix(reports): normalize SQLite/PG datetimes and track unknown LLM cost`)
- **Branch:** `minh`
- **Verdict:** **PASS**

---

## 1. Datetime Normalization & SQLite / PostgreSQL Parity

Reviewed [reports.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/reports.py#L18-L19), [reports.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/reports.py#L55-L87), [database.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/platform/database.py#L13-L20), and [main.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/main.py#L282-L288):

- **UTC query normalization:** `report()` normalizes `start_at` and `end_at` through `_utc()` (`ensure_utc(dt).astimezone(timezone.utc)`) before binding `Suggestion.completed_at`, `AuditEntry.occurred_at`, `Ticket.created_at`, and `Ticket.closed_at` comparisons, while preserving the half-open `[start_utc, end_utc)` boundary and echoing ISO timestamps in `period`.
- **SQLite naive vs aware parity:** `_utc()` attaches `timezone.utc` to naive `datetime` values returned by SQLite `DateTime(timezone=True)`, eliminating mixed naive/aware `TypeError` failures in `end_to_end_latency_ms` and `handling_time_ms` calculations.
- **No JOIN inflation or pre-window leak:** `Ticket` rows matching created, closed, or `suggestion_ticket_ids` (`trigger == "ticket_created"`) are fetched in one single-table `SELECT ... WHERE or_(...)` query (no join duplication). `ticket_counts.created`, `ticket_counts.closed`, and `handling_time_ms` re-filter explicitly with `start_utc <= _utc(...) < end_utc`, so prior-window tickets included only for `e2e` latency do not inflate `created` counts.
- **SQLite writer invariant (verified via probe):** SQLAlchemy's SQLite `DateTime(timezone=True)` stores naive wall-clock strings without converting non-UTC offsets on insert (a test row inserted directly with `+07:00` stored local wall time and compared as UTC). Production backend paths always write via `utcnow()` ([database.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/platform/database.py#L13-L14)), so production rows are UTC; callers writing directly to SQLite in tests must likewise pass UTC.

---

## 2. LLM Cost Accounting & Truthfulness

Reviewed `_llm_cost_summary` ([reports.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/reports.py#L22-L52)) against [engine.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/ai_service/engine.py#L38-L63), [drafting.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/ai_service/drafting.py#L73-L152), [jobs.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L275-L412), and [service.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L80-L127):

- **Non-LLM exclusion:** Deterministic abstentions/fallbacks (`llm_usage=None`, empty/absent `llm_metadata`, `draft_status != "llm_unavailable"`) are excluded from `known_count` and `unknown_count`.
- **Strict integer micro-USD validation:** Only non-`bool`, non-negative `int` `cost_micro_usd` values with `not incomplete` count toward `known_total`/`known_count`. `bool`, negative `int`, `float` (including `NaN`/`inf`), strings, missing values, and flagged incomplete records increment `unknown_count`.
- **No misleading partial totals:** When `unknown_count > 0`, `total` and `average` return `None` while `known_total`, `known_average`, `known_count`, and `unknown_count` remain separately exposed. When `unknown_count == 0` and `known_count == 0`, `total` is `0` and `average` is `None`.
- **Truthful with current runtime telemetry:** Live Gemini responses in `Engine._extract_llm_usage_and_metadata` do not set `cost_micro_usd`, so live suggestions are consistently reported as unmeasured (`total: None, average: None, known_count: 0, unknown_count: N`).

---

## 3. API Compatibility, Auth & Frontend Rendering

Reviewed [main.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/main.py#L282-L288), [types.ts](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/types.ts#L29), and [reports.tsx](file:///F:/Năm%203/SD/project/SupportIQ/apps/frontend/src/features/reports.tsx#L8-L20):

- **Auth & validation:** `/v1/console/reports` enforces `["manager"]` (`401` unauthenticated; `403` for `customer`, `staff`, `admin`; `200` for `manager`) and returns `422` when `start_at` or `end_at` is naive or `start_at >= end_at`.
- **Frontend rendering:** When `total == null`, the summary card shows `'Unknown'` instead of `$0.0000`. `Known cost subtotal` and `Average across measured suggestions` render only when `unknown_count > 0 && known_count > 0`, preventing an unmeasured period (`known_total: 0, known_count: 0`) from displaying `$0.0000`. No ticket IDs, customer metadata, or raw `llm_metadata` are exposed.

---

## 4. Verification Evidence

Executed on commit `cf58f08a810f1cfa8ec587ddddc239c35ad7a84d` (no source modifications):

| Check | Scope | Result |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_reports_correctness.py tests/application/test_reports_pg.py -v` | SQLite report unit tests (4) + disposable PostgreSQL parity test (1) | **5 passed** (`11.52s`) |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_reports_correctness.py tests/unit/test_accounting_guardrails_b.py tests/application/test_reports_pg.py tests/application/test_application.py -q` | Reports correctness, accounting guardrails, PG report parity, PG application auth/domain suite | **73 passed** (`22.50s`) |
| `npm --prefix apps/frontend test -- src/features/reports.test.tsx` | Frontend `Reports` missing / mixed / verified-zero rendering tests | **3 passed** (1 file) |
| `npm --prefix apps/frontend test` | Full frontend Vitest unit suite | **22 passed** (5 files) |
| `npm --prefix apps/frontend run typecheck` | TypeScript `tsc -b` | **Exit 0** |
| Read-only Python probes | Role matrix (`401`/`403`/`200`/`422`), `NaN`/`inf`/`bool` costs, SQLite offset behavior, `BudgetedDraftClient` -> `Engine` retry `incomplete` propagation | Verified exact behavior noted in Sections 1–5 |

---

## 5. Remaining Instrumentation Gap & Notes for Next Phase

1. **Cost instrumentation absent (expected):** `Engine._extract_llm_usage_and_metadata` ([engine.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/ai_service/engine.py#L38-L63)) does not yet compute or emit `cost_micro_usd`, `usage_incomplete`, or `cost_incomplete`. Until wired with verified provider/model/thought-token pricing, production reports will continue to show `Unknown` LLM cost rather than fabricating totals.
2. **Incomplete-retry propagation hazard when cost instrumentation is wired:**
   - `BudgetedDraftClient._aggregate_usage` ([drafting.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/ai_service/drafting.py#L146-L151)) emits `"incomplete": True` (and `"has_invalid_fields": True`) when an attempt lacks valid usage, or omits `totalTokenCount` (yielding `total_tokens_partial` in `Engine`).
   - Currently, `Engine._extract_llm_usage_and_metadata` drops `incomplete` / `has_invalid_fields`, and `_llm_cost_summary` ([reports.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/reports.py#L37)) checks only `usage_incomplete` / `cost_incomplete` (not `incomplete` or `total_tokens_partial`). Probe confirmed `{cost_micro_usd: 500, incomplete: True}` is treated as known if `usage_incomplete` is not set. Today this cannot misreport because `cost_micro_usd` is absent, but future cost instrumentation must propagate `usage_incomplete` / `cost_incomplete` (or refuse to emit `cost_micro_usd` when `incomplete` or `total_tokens_partial` is set).
3. **Minor non-blocking notes:**
   - If `SuggestionWorker.process` receives an HTTP `503`/`504` before receiving an AI service JSON body ([jobs.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L275-L289)), `draft_status="unavailable"` and `llm_usage=None` are stored without `llm_metadata`; `_llm_cost_summary` excludes it because the backend cannot distinguish pre-LLM ML failure from an LLM timeout across the HTTP error boundary.
   - `reports.py` mixes `.get("trigger")` ([L60](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/reports.py#L60)) with `["trigger"]` / `["draft_status"]` / `["analysis_status"]` ([L72-L78](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/reports.py#L72-L78)); safe for all `create_suggestion` rows.

---

## 6. Smallest Next Action

When adding cost instrumentation in a follow-up change, update [Engine._extract_llm_usage_and_metadata](file:///F:/Năm%203/SD/project/SupportIQ/apps/ai_service/engine.py#L38-L63) (and/or `_llm_cost_summary`) to propagate `BudgetedDraftClient`'s `incomplete` / `has_invalid_fields` / missing `totalTokenCount` state into `usage_incomplete=True` alongside verified `cost_micro_usd` calculation (requiring explicit `provider`, `model`, `total_tokens` accounting including `thought_tokens` rather than synthetic pricing).
