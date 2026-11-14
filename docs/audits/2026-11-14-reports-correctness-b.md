# Reports Correctness Audit & Fix (Worker B)

## Scope

Targeted correctness fix for `report()` (`apps/backend/tickets/reports.py`), `Report` typing (`apps/frontend/src/types.ts`), and the support reports view (`apps/frontend/src/features/reports.tsx`) based on Rank 4 of `docs/audits/2026-11-14-non-model-bottlenecks-c.md`.

## Issues Verified & Fixed

1. **SQLite naive/aware `TypeError` & unbounded `Ticket` scan (`apps/backend/tickets/reports.py`)**
   - **Before:** `report()` queried `select(Ticket)` unboundedly without SQL date filters and compared naive SQLite `DateTime(timezone=True)` readbacks (`ticket.created_at`, `ticket.closed_at`, `ticket.handling_started_at`, `suggestion.completed_at`) directly against timezone-aware `start_at` / `end_at`, raising `TypeError` on SQLite. Non-UTC offsets (e.g. `+07:00`) were also passed directly to SQL comparisons without UTC normalization.
   - **After:**
     - Converts `start_at` and `end_at` to UTC (`_utc(...)`) before SQL filtering and Python comparisons, preserving half-open `[start_at, end_at)` bounds.
     - Normalizes ORM datetimes with `ensure_utc(...).astimezone(timezone.utc)` before subtracting or comparing.
     - Filters `Ticket` SQL-side via `or_(and_(Ticket.created_at >= start_utc, Ticket.created_at < end_utc), and_(Ticket.closed_at.is_not(None), Ticket.closed_at >= start_utc, Ticket.closed_at < end_utc), Ticket.ticket_id.in_(suggestion_ticket_ids))` and indexes `ticket_created_at` by `ticket_id` instead of scanning all tickets in Python.

2. **Dishonest `$0.0000` cost reporting (`apps/backend/tickets/reports.py`, `apps/frontend/src/types.ts`, `apps/frontend/src/features/reports.tsx`)**
   - **Before:** `reports.py` computed `[suggestion.payload["llm_usage"].get("cost_micro_usd", 0) ...]` and returned `{"total": sum(costs), "average": sum(costs) / len(costs) if costs else None}`. When `cost_micro_usd` was omitted (as in live `GeminiDraftClient` / `SuggestionWorker` payloads), invalid, or incomplete, missing costs were treated as `0`, displaying `$0.0000` in the console UI. Furthermore, `reports.tsx` divided `report.llm_cost_micro_usd.total / 1_000_000`, which in JS evaluates `null / 1_000_000` as `$0.0000`.
   - **After:**
     - `_llm_cost_summary()` inspects suggestions that invoked or attempted the LLM (`llm_usage is not None`, non-empty `llm_metadata`, or `draft_status == "llm_unavailable"`).
     - Only non-boolean non-negative `int` `cost_micro_usd` without `usage_incomplete`/`cost_incomplete` flags enters `known_total` and `known_count`; missing, `None`, `bool`, negative, non-int, or incomplete entries increment `unknown_count`.
     - Deterministic non-LLM outcomes (e.g. `abstained` / `escalation_recommended` without `llm_usage`, `llm_metadata`, or `llm_unavailable`) are excluded from both denominators.
     - `reports.tsx` renders `'Unknown'` (never `$0.0000`) for `Total LLM cost` when `total == null`, and renders `'Unmeasured LLM suggestions'` plus partial `'Known cost subtotal (<N> measured)'` and `'Average across measured suggestions'` when `unknown_count > 0`.

## Before / After Report JSON Examples (`llm_cost_micro_usd`)

- **Period with 2 LLM suggestions lacking `cost_micro_usd`:**
  - Before: `{"total": 0, "average": 0.0}` (UI rendered `$0.0000` / `$0.0000`)
  - After: `{"total": null, "known_total": 0, "average": null, "known_average": null, "known_count": 0, "unknown_count": 2}` (UI renders `Unknown` / `—` and `Unmeasured LLM suggestions: 2`)
- **Mixed period (1 known `1200` micro USD + 1 missing `cost_micro_usd`):**
  - Before: `{"total": 1200, "average": 600.0}` (wrongly divided by 2, treating missing cost as `0`)
  - After: `{"total": null, "known_total": 1200, "average": null, "known_average": 1200.0, "known_count": 1, "unknown_count": 1}` (UI renders `Total LLM cost: Unknown`, `Known cost subtotal (1 measured): $0.0012`, `Average across measured suggestions: $0.0012`, `Unmeasured LLM suggestions: 1`)
- **Verified zero-cost LLM calls (1 explicit `cost_micro_usd: 0`) vs zero LLM calls:**
  - 1 known `0`: `{"total": 0, "known_total": 0, "average": 0.0, "known_average": 0.0, "known_count": 1, "unknown_count": 0}`
  - 0 LLM calls: `{"total": 0, "known_total": 0, "average": null, "known_average": null, "known_count": 0, "unknown_count": 0}`

## Denominators & Telemetry Limits

- `average`: Complete period average across all LLM suggestions (`known_total / known_count`) only when `unknown_count == 0` and `known_count > 0`; otherwise `null`.
- `known_average`: Average over measured suggestions only (`known_total / known_count` when `known_count > 0`; otherwise `null`).
- **Limit:** Runtime draft synthesis (`apps/ai_service/engine.py`, `apps/backend/tickets/jobs.py`) records token counts (`input_tokens`, `output_tokens`, `total_tokens`/`total_tokens_partial`, optional `thought_tokens`) without provider billing `cost_micro_usd`. Rather than inventing prices from tokens (especially when `thoughtsTokenCount` or `totalTokenCount` may be omitted), `reports.py` surfaces unmeasured suggestions honestly until authoritative cost metadata is recorded.
