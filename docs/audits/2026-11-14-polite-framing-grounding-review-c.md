# Stage 1 Independent Review — Polite Topic Framing Grounding Fix (Worker B)

- **Reviewer:** Worker C (`task_4f788d7610c7`)
- **Reviewed Commit:** `ce20c5225aa0039663aa7bb61a39a64b192c8645` (`fix(safety): allow strictly narrow polite topic framing in grounding validation`)
- **Primary Artifact Reviewed:** `docs/audits/2026-11-14-polite-framing-grounding-b.md`
- **Modified Code Reviewed:** `apps/core_backend/safety.py`, `apps/ai_service/engine.py`, `tests/unit/test_ai_grounding.py`, `tests/unit/test_gemini_llm.py`
- **Verdict:** **`CHANGES_REQUIRED`**
- **Stage 2 Gate Status:** **HALTED after Stage 1.** Per the sequential review gate, Stage 2 fixed model evaluation (`fit2-taxonomy-audit-v5-r2`) was **not** executed because Stage 1 found material grounding/validation defects in `apps/ai_service/engine.py`.

---

## 1. Summary

The sentence-level polite-framing classifier added in `apps/core_backend/safety.py` (`_SAFE_POLITE_FRAMING`, `_POLITE_NON_CLAIM`, `_is_safe_uncited_sentence`, `is_safe_uncited_paragraph`) is tight and rejects adversarial bypasses in direct validation (`find_draft_grounding_violation` / `validate_generated_draft`).

However, the caller wiring in `apps/ai_service/engine.py` (`Engine.draft`) retains an unguarded `len(paragraph) <= 40` exemption and validates uncited text only at paragraph granularity. Together, those two gaps allow uncited substantive claims, transaction commitments, currency-word/time promises, and appended uncited claims inside cited paragraphs to pass `Engine.draft()` with `status="draft_ready"`.

---

## 2. Findings

### Finding 1 (High) — Retained `<= 40`-char uncited paragraph exemption in `Engine.draft` smuggles factual claims and transaction commitments
- **Location:** `apps/ai_service/engine.py:280-284`
- **Audit Doc Discrepancy:** `docs/audits/2026-11-14-polite-framing-grounding-b.md:26` states that `Engine.draft()` preserves the `<= 40` char exemption `"for non-FACTUAL_COMMITMENT short questions ('Could you provide your order ID?')"`. In code, `Engine.draft()` checks:
  ```python
  if not source_ids and not is_safe_uncited_paragraph(paragraph) and (
      len(paragraph) > 40 or FACTUAL_COMMITMENT.search(paragraph)
  ):
  ```
- **Why this fails:**
  1. There is no requirement that the `<= 40`-char paragraph be a clarification question (neither `endswith("?")` nor `generated.get("is_clarification")` is checked).
  2. `FACTUAL_COMMITMENT` (`apps/core_backend/safety.py:17-20`) only matches `$\d`, numeric time durations (`\d (days?|business days?|hours?|weeks?|months?)`), and `{refund, refunded, refunds, return window, fee, fees, warranty}`. It does **not** catch transaction commitments (`has_ungrounded_transaction_commitment`), uncited claim/policy terms (`_UNCITED_CLAIM_TERMS`), non-`$` currencies/time words (`_UNSAFE_UNCITED_TOKENS`), or general policy assertions (`is free`, `eligible`, `no charge`, `cancelled`, `approved`).
- **Observed Reproduction (`Engine.draft` with `MockLLM`, paired with a cited policy paragraph `[S1]`):**
  - `"Shipping is free."` (`len=17`) -> `is_safe_uncited_paragraph=False`, `Engine.draft` -> `draft_ready` (`find_draft_grounding_violation` -> `uncited_claim`)
  - `"Your order is cancelled."` (`len=24`) -> `is_safe_uncited_paragraph=False`, `Engine.draft` -> `draft_ready` (`find_draft_grounding_violation` -> `uncited_claim`)
  - `"We approved your return."` (`len=24`) -> `is_safe_uncited_paragraph=False`, `Engine.draft` -> `draft_ready` (`find_draft_grounding_violation` -> `uncited_claim`)
  - `"You are eligible."` (`len=17`) -> `is_safe_uncited_paragraph=False`, `Engine.draft` -> `draft_ready` (`find_draft_grounding_violation` -> `uncited_claim`)
  - `"No charge applies."` (`len=18`) -> `is_safe_uncited_paragraph=False`, `Engine.draft` -> `draft_ready` (`find_draft_grounding_violation` -> `uncited_claim`)
  - `"It will arrive tomorrow."` (`len=24`) -> `is_safe_uncited_paragraph=False`, `Engine.draft` -> `draft_ready` (`find_draft_grounding_violation` -> `uncited_claim`)
  - `"Hello, you get a free gift!"` (`len=27`) -> `is_safe_uncited_paragraph=False`, `Engine.draft` -> `draft_ready` (`find_draft_grounding_violation` -> `uncited_claim`)
- **Required Fix:** Remove the blanket `len(paragraph) <= 40` bypass. Any clarification exception (e.g., `"Could you provide your order ID?"` in `test_short_clarification_without_citation_allowed`) must require an actual clarification/question form and still enforce `has_ungrounded_transaction_commitment`, `_UNSAFE_UNCITED_TOKENS`, `_VND_CURRENCY`, digits, and substantive claim guards (or use an explicit closed clarification question pattern / allow-list).

### Finding 2 (Medium) — Paragraph-level `not source_ids` skips uncited sentences mixed into a cited paragraph
- **Location:** `apps/ai_service/engine.py:280-284`
- **Why this fails:** `Engine.draft()` only checks `is_safe_uncited_paragraph(paragraph)` when `source_ids = re.findall(r"\[(S\d+)\]", paragraph)` is empty. If a paragraph contains a cited sentence followed by an uncited factual claim or commitment, `Engine.draft()` accepts it whereas `safety.py`'s `find_draft_grounding_violation` splits sentences (`split_draft_sentences`) and rejects the uncited sentence (`uncited_claim`).
- **Observed Reproduction:**
  - `"Standard delivery takes 3 to 5 days [S1]. Shipping is free."` -> `is_safe_uncited_paragraph=False`, `Engine.draft` -> `draft_ready`, `find_draft_grounding_violation` -> `uncited_claim`, `validate_generated_draft` -> `(False, ['grounding_failed'])`.
- **Required Fix:** Validate uncited segments at sentence granularity in `Engine.draft()` (reusing `find_draft_grounding_violation` or `split_draft_sentences` + `_is_safe_uncited_sentence` semantics) so cited paragraphs cannot harbor ungrounded uncited sentences.

---

## 3. What Passed Review (`apps/core_backend/safety.py` & Focused Suite)

- **Shared Helper & Safety Rules (`apps/core_backend/safety.py:394-436, 514-537`):**
  - `_SAFE_POLITE_FRAMING` and `_POLITE_NON_CLAIM` are anchored (`^...$`), capped (`len(cleaned) <= 100`), reject digits, currency/time/duration words (`_UNSAFE_UNCITED_TOKENS`, `_VND_CURRENCY`), transaction commitments (`has_ungrounded_transaction_commitment`), `FACTUAL_COMMITMENT`, and `_UNCITED_CLAIM_TERMS`.
  - Legitimate topic framing (`"Thank you for reaching out about your order."`) returns `is_safe_uncited_paragraph=True`, `find_draft_grounding_violation=None`, and `validate_generated_draft=(True, [])`.
  - Adversarial variants (`"Thank you for contacting us, your order is cancelled."`, `"Thank you for contacting support regarding your 50000 VND fee."`, `"Hello, you get a free gift!"`, mixed-citation paragraphs) all fail `is_safe_uncited_paragraph` and `validate_generated_draft` with `grounding_failed`.
  - Citation parsing (`[S\d+]`) and privacy redaction boundaries were preserved (`apps/core_backend/llm/gemini.py:934-953`).
- **Focused Test Suite Run (`pytest` on current `HEAD` `ce20c52`):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_llm.py tests/unit/test_ai_grounding.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_order_context_grounding.py tests/unit/test_pipeline_runner_safety_b.py tests/unit/test_retrieval_grounding_b2.py tests/application/test_application.py tests/application/test_backend_safety_closure.py -q`
  - Result: **`173 passed in 36.58s`** (confirms existing tests did not cover `<= 40`-char factual smuggling or mixed cited/uncited sentences in `Engine.draft()`).

---

## 4. Required Actions Before Stage 2

1. Tighten `Engine.draft()` in `apps/ai_service/engine.py:280-284` to close the `<= 40`-char smuggling loophole and check uncited sentences inside cited paragraphs consistently with `apps/core_backend/safety.py`.
2. Add unit regression tests in `tests/unit/test_ai_grounding.py` covering:
   - Short (`<= 40` char) uncited factual claims and transaction commitments rejected in `Engine.draft()` (`"Shipping is free."`, `"Your order is cancelled."`, `"We approved your return."`, `"Hello, you get a free gift!"`).
   - Mixed cited + uncited factual sentence in the same paragraph rejected in `Engine.draft()`.
   - Legitimate clarification question (`"Could you provide your order ID?"`) remaining allowed cleanly via a narrow question/clarification guard.
3. Re-submit for Stage 1 review and pass before running Stage 2 evaluation on `fit2-taxonomy-audit-v5-r2`.
