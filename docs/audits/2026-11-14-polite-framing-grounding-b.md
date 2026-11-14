# Rank 3 Fix: Narrow Polite Framing in Uncited Grounding Validation

**Date:** 2026-11-14
**Branch:** `minh`
**Task:** `task_86ca740999ec` (`ctx_3b0dc30585de`), addressing Rank 3 in `docs/audits/2026-11-14-non-model-bottlenecks-c.md`.

## Root Cause
`_is_safe_uncited_sentence()` in `apps/core_backend/safety.py` checked `_UNCITED_CLAIM_TERMS` and `FACTUAL_COMMITMENT` against every uncited sentence before checking polite framing. Non-factual polite acknowledgments and closing invitations mentioning neutral topics (`order`, `refund`, `return`, `policy`)—such as `"Thank you for reaching out about your order."` and `"Please let us know if you have questions about this policy."`—surrounding a correctly cited factual answer (`[S1]`) were rejected as `"uncited_claim"` (`llm_invalid_citations` / `grounding_failed` -> `llm_unavailable`). Additionally, `Engine.draft()` in `apps/ai_service/engine.py` rejected any uncited paragraph over 40 characters without delegating to the shared polite-framing check.

In parallel, the previous `_POLITE_NON_CLAIM` regex used broad character wildcards (`[^.!?]{0,60}` / `[^.!?]{0,80}`), which risked accepting arbitrary clauses appended after `"Hello,"`, `"Thank you,"`, or `"Please ..."` whenever no term in `_UNCITED_CLAIM_TERMS` matched.

## Fix Summary
1. **`apps/core_backend/safety.py`**:
   - Replaced wildcard `_POLITE_NON_CLAIM` clauses with a strict, closed polite acknowledgment/invitation grammar (`_SAFE_POLITE_FRAMING`) requiring terminal sentence punctuation (`.`, `!`, `?`) and limiting topic mentions (`order`, `return`, `refund`, `delivery`, `shipping`, `shipment`, `cancellation`, `payment`, `request`, `inquiry`, `question`, `concern`, `issue`, `policy`, `policies`) strictly to neutral prepositional objects (`about/regarding/with your/this/the/our ...`).
   - Tightened `_POLITE_NON_CLAIM` to bare/named greetings and simple sign-offs without free-form clauses.
   - Enforced unconditional pre-checks on all uncited sentences (`len <= 100`, no digits, no currency symbols/`VND` tokens, no spelled-out number or relative-day/duration words via `_UNSAFE_UNCITED_TOKENS`, and no ungrounded transaction commitments via `has_ungrounded_transaction_commitment()`), while preserving `_UNCITED_CLAIM_TERMS` and `FACTUAL_COMMITMENT` for all sentences outside `_SAFE_POLITE_FRAMING`.
   - Exported `is_safe_uncited_paragraph()` using `split_draft_sentences()` so multi-line/multi-sentence uncited blocks are checked sentence-by-sentence.
2. **`apps/ai_service/engine.py`**:
   - Updated `Engine.draft()` to reuse `is_safe_uncited_paragraph()` from `apps/core_backend/safety.py` for uncited paragraphs, eliminating false `grounding_failed` rejections on >40-character polite framing while keeping short-commitment and uncited-claim rejections intact.
3. **Tests**:
   - `tests/unit/test_gemini_llm.py`: Added parameterized positive cases (audit greeting/closing around `[S1]`, refund/return framing, inline multi-sentence framing) and negative adversarial boundary cases (`"Thank you, your refund is approved."`, `"Please know shipping is free."`, `"We apologize, your order will arrive tomorrow."`, `"Let us know after 5 days."` / `"five days"`, greeting+factual clause, multiline/semicolon/no-space bypasses, money/fee mention, and uncited-only drafts).
   - `tests/unit/test_ai_grounding.py`: Added `Engine.draft()` coverage confirming >40-char polite topic framing passes alongside `[S1]` while `"We apologize, your order will arrive tomorrow."` fails closed with `grounding_failed`.

## Residual Limits
- Only explicitly structured English non-factual acknowledgments/invitations within 100 characters are accepted without citation; novel conversational phrasing outside those closed templates must still either carry an inline citation or be omitted.
- `Engine.draft()` preserves the existing `<= 40` char clarification exemption for non-`FACTUAL_COMMITMENT` short questions (`"Could you provide your order ID?"`).
