# Rank 3 Fix & Stage 1 Corrections: Authoritative Source Binding and Clause-Level Grounding Across `safety.py` and `Engine.draft()`

**Date:** 2026-11-14
**Branch:** `minh`
**Tasks:** `task_86ca740999ec` (`ctx_3b0dc30585de`), `task_347dd5c5121b` (`ctx_be26087d704f`), `task_4e7785ed2b13` (`ctx_fed3ef8686d1`), addressing Rank 3 in `docs/audits/2026-11-14-non-model-bottlenecks-c.md`, Stage 1 Review (`b88692c`, `docs/audits/2026-11-14-polite-framing-grounding-review-c.md`), and Stage 1 Re-Review (`8f28fe4`, `docs/audits/2026-11-14-polite-framing-grounding-rereview-c.md`).

## Defect Dispositions (Stage 1 Re-Review `8f28fe4`)
1. **Finding 1 (Critical — Bare present-tense passive status claims bypassing `_PASSIVE_COMMIT`):**
   - **Verified & Fixed.** Updated `_PASSIVE_COMMIT` in `apps/core_backend/safety.py` from `is\s+(?:now|already)` to `is(?:\s+(?:now|already))?` so bare passive status claims (`"Your order is cancelled [S1]."`, `"Your refund is approved [S1]."`, `"Your return is approved [S1]."`, `"Your refund is refunded [S1]."`, `"Your return is processed [S1]."`, `"Your order is credited [S1]."`) are caught against policy sources and contradicting `order_facts` (`order_status: delivered`, `refund_status: pending`, `return_status: requested`).
   - Updated `_is_verified_recorded_order_status()` to verify `order_status`, `refund_status`, `return_status`, and `payment_status` strictly against cited `order_facts` fields while preserving verified order statuses, conditionals (`once`/`if`), and plural general policy statements (`"Refunds are approved after inspection [S1]."`).
2. **Finding 2 (Critical — Unbound LLM-reported `input_snapshot` in `Engine.draft()`):**
   - **Verified & Fixed.** `Engine.draft()` in `apps/ai_service/engine.py` now extracts validated identifier-free `supplied_facts` (`extract_order_facts(..., allowed_fields=ORDER_CONTEXT_ALLOWED_SET, include_order_identifiers=False)`), builds canonical `authoritative_sources` via `build_grounded_sources()` **before** invoking `self.llm.generate()`, and passes isolated copies (`copy.deepcopy`) of retrieved `evidence` and identifier-free `validated_order_input` to `self.llm.generate()`.
   - Exported `validate_snapshot_sources()` in `apps/core_backend/safety.py` and used it in both `validate_generated_draft()` and `Engine.draft()` to verify any LLM-returned `input_snapshot` against `authoritative_sources` on `source_id`, `source_type` (`policy` / `order_facts`), `document_id`, `version`, `excerpt`/`text`, and `sha256` (when present). `find_draft_grounding_violation()`, `validate_generated_draft()`, and final `citations`/`segments` construction in `Engine.draft()` operate exclusively on `authoritative_sources`.
   - Fixed the stale mock mismatch in `tests/e2e/test_full_pipeline.py::test_normal_shipping_cost_flow` so `adapter.retrieve` provides the matching `b1000000-0000-0000-0000-000000000005` `Shipping Fee Policy` evidence rather than relying on LLM self-reported snapshot overrides.
3. **Finding 3 (High — Missing-space period sentence splits and inline clause splices sharing `[S1]`):**
   - **Verified & Fixed.** Expanded `_SENTENCE_BOUNDARY` and `split_draft_sentences()` in `apps/core_backend/safety.py` to split missing-space period boundaries (`.Products`, `.products`) while preserving decimals (`18.000`, `1.000.000`), ISO dates, multi-dot abbreviations (`e.g.`, `i.e.`), `_ABBREVIATION_PREFIX` entries, emails, URLs, and domain/file extensions (`_is_token_identifier_dot()`).
   - Added `_has_spliced_uncited_clause()` / `_clause_lacks_source_support()` in `find_draft_grounding_violation()` to reject uncited trailing clauses after `[S#]` (`"... [S1], shipping is free."`) and inline clause splices across `,`, `:`, ` - `, and `(...)` (`"Shipping is free, products may be returned... [S1]."`, `"Shipping is free: ... [S1]."`, `"... - shipping is free [S1]."`, `"... (shipping is free) [S1]."`) when non-polite predicate claim terms lack support in cited sources.

## Verification Run (Post-Final-Edit)
- `.venv\Scripts\python -m pytest tests/unit/test_gemini_llm.py tests/unit/test_ai_grounding.py tests/unit/test_completion_grounding.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_llm_egress_safety_review.py tests/unit/test_llm_source_privacy.py tests/unit/test_order_context_grounding.py tests/unit/test_guard_corrections_checks.py tests/unit/test_pipeline_runner_safety_b.py tests/unit/test_routing_safety_regressions.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_autoeval.py tests/application/test_ai_boundary.py tests/application/test_application.py tests/application/test_backend_safety_closure.py tests/e2e/test_full_pipeline.py -q` -> **423 passed, 1 deselected** (`103.11s`).

## Files Modified
- `apps/core_backend/safety.py`
- `apps/ai_service/engine.py`
- `tests/unit/test_ai_grounding.py`
- `tests/unit/test_gemini_llm.py`
- `tests/e2e/test_full_pipeline.py`
- `docs/audits/2026-11-14-polite-framing-grounding-b.md`

## Residual Limits
- Only explicitly closed non-factual English polite framing templates (`_SAFE_POLITE_FRAMING`, `_POLITE_NON_CLAIM`) and closed clarification-detail prompts (`_SAFE_CLARIFICATION_QUESTION` when `is_clarification=True`) within 100 characters are accepted without inline citations; novel uncited phrasings remain fail-closed.
- `Engine.draft()` requires a non-empty `input_snapshot` in LLM responses whose listed entries strictly match the precomputed `authoritative_sources`; legacy aliases (`"order"`, `"order_context"`) for `source_type` are rejected in favor of canonical `"policy"` and `"order_facts"`.
