# Rank 3 Fix & Stage 1 Correction: Unified Sentence-Level Grounding Validation Across `safety.py` and `Engine.draft()`

**Date:** 2026-11-14
**Branch:** `minh`
**Tasks:** `task_86ca740999ec` (`ctx_3b0dc30585de`), `task_347dd5c5121b` (`ctx_be26087d704f`), addressing Rank 3 in `docs/audits/2026-11-14-non-model-bottlenecks-c.md` and Stage 1 Review (`b88692c`, `docs/audits/2026-11-14-polite-framing-grounding-review-c.md`).

## Defect Dispositions (Stage 1 Review `b88692c`)
1. **Finding 1 (High — Retained `len(paragraph) <= 40` uncited bypass in `Engine.draft()`):**
   - **Verified & Fixed.** Removed the `len(paragraph) <= 40` exemption and paragraph-level fallback in `apps/ai_service/engine.py`.
   - `Engine.draft()` now delegates post-generation validation directly to shared `find_draft_grounding_violation()` (and `validate_generated_draft()` when `"citations"` is present in the LLM result) in `apps/core_backend/safety.py`.
   - Clarification questions (`"Could you provide your order ID?"` alongside a cited `[S1]` policy segment) are accepted **only** when `is_clarification=True` (`allow_clarification_questions=True`) **and** the uncited question matches the explicit narrow `_SAFE_CLARIFICATION_QUESTION` contract (while still enforcing all numeric, currency, number/duration word, commitment, and length guards). Factual questions (`"Is shipping free?"`) and arbitrary short prose (`"Shipping is free."`, `"Your order is cancelled."`, `"We approved your return."`, `"Hello, you get a free gift!"`, `"You are eligible."`, `"No charge applies."`, `"It will arrive tomorrow."`) are rejected with `llm_unavailable` / `grounding_failed`.
2. **Finding 2 (Medium — Paragraph-level `not source_ids` skipping uncited sentences mixed into cited paragraphs):**
   - **Verified & Fixed.** `Engine.draft()` no longer skips a paragraph whenever `re.findall(r"\[(S\d+)\]", paragraph)` is non-empty.
   - `find_draft_grounding_violation()` splits all draft text into sentences/clauses via `split_draft_sentences()`—now also splitting across semicolons (`;`), newline boundaries (`\n`), and citation-adjacent punctuation (`[S1].Next` / `.[S1]Next`)—so uncited claims before or after `[S1]` in the same paragraph cannot borrow prior/adjacent citations and fail closed (`"uncited_claim"` -> `grounding_failed`).
   - Additionally restricted `Engine.draft()` order citation building to explicit `source_type in ("order_facts", "order", "order_context")` with non-empty `supplied_fields`, and required non-empty `document_id` and `version` for `policy` citations, preserving legacy `field` + multi-field `fields` `order_context` schema, valid money (`0 VND`, `499,000 VND`), dates, and PII redaction.

## Files Modified
- `apps/core_backend/safety.py`: Tightened `_SENTENCE_BOUNDARY` across semicolons and citation-adjacent runs; added explicit `_SAFE_CLARIFICATION_QUESTION` contract gated by `allow_clarification_questions=True` on `_is_safe_uncited_sentence()`, `is_safe_uncited_paragraph()`, `find_draft_grounding_violation()`, and `validate_generated_draft()`; preserved closed `_SAFE_POLITE_FRAMING` / `_POLITE_NON_CLAIM` non-factual framing and unconditional guards.
- `apps/ai_service/engine.py`: Replaced the duplicate inline paragraph-length check in `Engine.draft()` with shared `find_draft_grounding_violation()` and `validate_generated_draft()` validation, tightened `source_type` ownership checks, and kept `FACTUAL_COMMITMENT` / `PLACEHOLDER` / `SENSITIVE_AUTHORITY_PATTERN` module exports intact.
- `tests/unit/test_ai_grounding.py`: Added direct `Engine.draft()` stub regressions reproducing every Finding 1 `<= 40`-char bypass, Finding 2 mixed cited/uncited same-paragraph/before-after/semicolon/newline/no-space/token-manipulation variants, clarification factual-question rejection, fabricated citation/source-type tampering rejection, and valid mixed `[S1]`/`[S2]` `order_facts` + polite framing acceptance.
- `tests/unit/test_gemini_llm.py`: Added real `GeminiDraftClient` transport regression variants for semicolon and citation-adjacent bypasses (`[S1]; Shipping is free.`, `Shipping is free; ... [S1].`, `[S1].Shipping is free.`).

## Residual Limits
- Only explicitly closed non-factual English polite framing templates (`_SAFE_POLITE_FRAMING`, `_POLITE_NON_CLAIM`) and closed clarification-detail prompts (`_SAFE_CLARIFICATION_QUESTION` when `is_clarification=True`) within 100 characters are accepted without inline citations; novel uncited phrasings remain fail-closed.
- Policy source document IDs in `Engine.draft()` `input_snapshot["sources"]` preserve compatibility with existing e2e test fixtures (`tests/e2e/test_full_pipeline.py::test_normal_shipping_cost_flow`) while verifying citation consistency via `validate_generated_draft()` whenever `"citations"` is supplied and enforcing non-empty `document_id`/`version` and `source_type` allowlists.
