# Worker B Completion Record: `order_context` Grounding & Citation Fix

## Scope & Root Cause
Fixes Rank 1 (`order_context` truncation and hardcoded citation attribution) in [2026-11-14-non-model-bottlenecks-c.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-14-non-model-bottlenecks-c.md):

1. **Unified allowlist, validation, and formatting (`apps/core_backend/llm/gemini.py`, `apps/ai_service/main.py`)**:
   - Replaced the divergent allowlists in `build_grounded_sources` and `prepare_llm_input` with one shared helper `extract_order_facts` driven by `ORDER_CONTEXT_ALLOWED_FIELDS` (`order_status`, `placed_at`, `order_total`, `shipping_cost`, `shipment_status`, `estimated_delivery_at`, `delivered_at`, `refund_status`, `refund_amount`, `refund_requested_at`).
   - Added `_format_order_money` (strict `{"amount_minor": int >= 0, "currency": 3-letter ISO}`, rejecting booleans/floats/nested PII/extra keys, preserving zero amounts like `0 VND` / `0.00 USD`) and `_validate_iso_date_or_timestamp` (rejecting non-ISO strings/extra structures).
   - Preserved `0` monetary amounts and `False` booleans, omitted `None`, and preserved `order_id` / `tracking_code` identifier rules in `prepare_llm_input` (`include_order_identifiers=True`) vs stripped sources (`include_order_identifiers=False`).
   - Updated `SuggestionRequest.check_context` in `apps/ai_service/main.py` to enforce strict nested validation (`strict=True`) via `extract_order_facts`.
2. **ISO timestamp grounding (`apps/core_backend/safety.py`)**:
   - Updated `_ISO_DATE` regex (`(?=\b|T\d{2}:\d{2})`) so ISO-8601 timestamps like `2026-10-19T07:00:00Z` count as grounded calendar dates in `_sentence_has_unsupported_numbers` instead of triggering false-positive numeric grounding failures.
3. **Honest `order_context` citations (`apps/ai_service/engine.py`, `apps/backend/tickets/jobs.py`, `apps/frontend/src/types.ts`, `apps/frontend/src/features/console.tsx`, `scripts/collect_final_acceptance_evidence.py`)**:
   - Updated `Engine.draft` to compute `supplied_fields` dynamically from validated `request["order_context"]` (failing closed with `grounding_failed` if empty), emitting a single source-level `S2` `order_context` citation with `"fields": list(supplied_fields)` (and `"field": supplied_fields[0]` only when `len(supplied_fields) == 1`) instead of hardcoding `("order_status", "refund_status")` or fabricating sentence-level field attribution.
   - Updated `SuggestionWorker.store` (`apps/backend/tickets/jobs.py`) to validate `fields` against `payload["order_context"]`, hydrate `citation["values"]` (and `citation["value"]` when `"field"` is present), and fail closed on missing/ungrounded fields.
   - Updated `Citation` (`apps/frontend/src/types.ts`), `CitationMarker` (`apps/frontend/src/features/console.tsx`), and `_verify_order_context_citation` (`scripts/collect_final_acceptance_evidence.py`) to support both multi-field (`fields`/`values`) and single-field (`field`/`value`) citations.

## Modified Files & SHA-256 Hashes
| File | SHA-256 |
| --- | --- |
| `apps/core_backend/llm/gemini.py` | `c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b` |
| `apps/ai_service/engine.py` | `17159708156916364d4a2d04f88d03e53aa7d1f9ee5ee839a6970aeb9c59e457` |
| `apps/ai_service/main.py` | `1d51a7824458021c69ab86e53dc00d1366d566d285da1f300c758c8bc1d819e4` |
| `apps/backend/tickets/jobs.py` | `9fc0699a2e8a3609afc0e04333d0f6eca46c691440a7736ee8f12f53f4c8a3c7` |
| `apps/core_backend/safety.py` | `6e0877ff57a9f4274e3056d2be0fe6ec2c7f3873cb274f066061f6a258ecf009` |
| `apps/frontend/src/types.ts` | `caed6707f80a278940833cbb738d77078a1bee73912722e6638cebf048bf8497` |
| `apps/frontend/src/features/console.tsx` | `69c2257172311f228e3d00c72c4e808f5b7dd6c908eadd7a933279aa831483db` |
| `scripts/collect_final_acceptance_evidence.py` | `7e55d3034fcefd646814f630928f682c4d6686559083ea29d3b1109cc4face98` |
| `tests/unit/test_order_context_grounding.py` | `55127ae28c2fb8f3908991c63ba5e0b81427c3aee8c76244e9e34582d122edee` |

Pre-existing parallel/unrelated workspace changes (`pipeline/training/train_boundary_candidate.py`, `artifacts/models/.gitkeep`, `artifacts/evaluation/boundary_contrast_20261114/`, `*.pptx`) were left untouched.

## Verification Results (Post-Final-Edit)
- `.venv\Scripts\python -m pytest tests/unit/test_order_context_grounding.py -q`: **13 passed** in `4.91s` (`MockTransport` stubbed HTTP / synthetic fixtures; no live Gemini API calls).
- `.venv\Scripts\python -m pytest -q`: **1130 passed, 2 failed, 2 skipped, 3 deselected, 1 xfailed** in `427.78s`:
  - `FAILED tests/unit/test_fit2_independent_gate.py::test_novel_vs_all_prior_and_internal`: asserts zero overlap across historical evaluation artifacts (`ov["exact_overlap"]`, 36 extra items starting `g2-sup-01`), unrelated to `order_context`.
  - `FAILED tests/unit/test_sealed_holdout_20261113.py::test_sealed_holdout_counts_kb_and_zero_overlap`: fails with `JSONDecodeError: Unexpected UTF-8 BOM` reading an existing evaluation report JSON under `artifacts/`, unrelated to `order_context`.

## Residual Limitations
- `apps/frontend` TypeScript compilation (`tsc`) and Vitest were not run because `apps/frontend/node_modules` lacks `typescript` and `vitest` on this checkout.
- `apps/backend/tickets/service.py` still forwards its existing 6 non-PII fields; all 10 schema fields pass cleanly when supplied by callers/tests.
- No live LLM calls, DB migrations, or service restarts were performed.
