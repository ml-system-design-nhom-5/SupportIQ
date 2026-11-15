# Worker B — Security Re-Review of Quote & Exclusion Structure Fix (`717ac038`)

- **Reviewer:** Worker B (`task_f876078447f8`, `dispatch_id=ctx_8bfe19c61866`, branch `minh`)
- **Reviewed Commit:** [`717ac0382fbaf9d4eebc059724346c6fa503484a`](../../apps/core_backend/safety.py) ([`2026-11-15-original-fit2-safety-quote-structure-fix-a.md`](2026-11-15-original-fit2-safety-quote-structure-fix-a.md)) vs prior B `BLOCK` (`04e63ba32f90a237c03a3c79d3bcf89acab0b63a`)
- **Upstream Adapter Invariant:** `git diff c466ffaa..717ac0382fbaf9d4eebc059724346c6fa503484a -- apps/core_backend/retrieval/adapter.py` is **empty** (`sha256: 3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`, threshold `0.55` unchanged).
- **Verdict:** **`BLOCK`** — `717ac038` closes all `9` prior B leaks (`0` LLM calls), preserves all `6+1` original repros (`0` LLM calls) and `43/43` fixed gate cases, and passes `test_safety_slice1_gap1_a.py` (`148/148`). Technically, moving UI labels under first-person/modal gating (`_UI_OR_SPEECH_QUOTE_PREFIX`), extracting `_DECLARATIVE_NEGATION_STEM`, and unifying `excluding|besides|save|barring` are solid, **but** `_mask_attributed_quotes` + `_is_ambiguous_or_endorsed_post_quote` ([`apps/core_backend/safety.py:496-545`](../../apps/core_backend/safety.py#L496-L545)) still mask unsupported physical-store quotes by default unless a narrow post-quote syntactic absence check fires. That leaves **a direct regression from `c466ffaa`** (declarative first-person endorsements without `?`) plus **structural `outside_quote` and 3rd-person alternative-rejection bypasses** calling the external LLM (`calls=1`) end-to-end.

---

## 1. Fundamental Structural Causes & Verified Changed-Line Leaks (`BLOCK`)

Every bypass below returned `policy_scope_requires_review() -> False`, **`Engine='draft'`**, and **`PipelineRunner` external LLM `calls=1`** (`manual_fallback ['requires_authority', 'grounding_failed']` solely from offline `StubLLM`) with `POL-RET-*` evidence retrieved (`6/8` also hit `real RetrievalAdapter` `status='success'` directly -> `draft` / LLM `calls=1`):

1. **Absence-based `?`-only check in `_is_ambiguous_or_endorsed_post_quote` ([`L499-L517`](../../apps/core_backend/safety.py#L499-L517)) + regression vs `c466ffaa`:**
   - Deleting `_QUOTE_ENDORSEMENT_FOLLOWUP` and requiring `"?" in clause` paired with literal `that|this|it|doing so` (or `or` before `first_alt`) **regressed on declarative endorsements** (`c466ffaa` previously blocked `want to do that` without `?`) AND still permits open-choice questions using non-listed anaphora (`there`, `visiting`, `going there`) or connectors (`before`, `alongside`).
   - **Verified end-to-end leaks (`Engine='draft'`, `Runner` `calls=1`, `real:success` on 3/5 and `pol:draft(0)/calls=1` on all 5):**
     - **Regression vs `c466ffaa` (`declarative`, no `?`):** `"My friend joked 'walk into a physical store to return it', and I want to do that along with the app."` (`pol` `Engine='draft'`, `Runner` `calls=1`; `real` `no_evidence`)
     - `"My friend joked 'walk into a physical store to return it' — please tell me I can do that before booking a courier."` (`real:success`, `Engine='draft'`, `Runner` `calls=1`)
     - `"My friend joked 'walk into a physical store to return it' and I plan to go there instead of waiting for a courier."` (`real:success`, `Engine='draft'`, `Runner` `calls=1` — note `"instead of waiting for a courier"` ALSO wrongly passes `_has_covered_return_alternative_request`!)
     - `"My friend joked 'walk into a physical store to return it' — is going there fine too, alongside booking a courier?"` (`real:success`, `Engine='draft'`, `Runner` `calls=1`)
     - `"My friend joked 'just walk into a retail store' — is visiting allowed before booking courier?"` (`pol` `Engine='draft'`, `Runner` `calls=1`; `real` `no_match`)
2. **Non-local `outside_quote` matching in `_QUOTE_REJECTION_SIGNAL.search(outside_quote)` ([`L535-L540`](../../apps/core_backend/safety.py#L535-L540)):**
   - `_QUOTE_REJECTION_SIGNAL` scans all concatenated `outside_quote` (`text[:m.start()] + text[m.end():]`) instead of the clause locally framing the quote (`local_prefix` or immediate post-quote `by mistake`/`wrongly`). An unrelated `instead` or `joked` in an earlier clause satisfies `_QUOTE_REJECTION_SIGNAL` and masks a completely separate positive quote.
   - **Verified end-to-end leaks (`real:success`, `Engine='draft'`, `Runner` `calls=1`):**
     - `"Instead of buying online, a friend told me 'return at a physical store' — please confirm if visiting is okay when I use the app."`
     - `"My friend joked yesterday, anyway support told me 'bring it to a physical store', let's check via the app."`
3. **1st-person-only `_ALT_CLAUSE_REJECTION` misses 3rd-person alternative negation ([`L375-L383`](../../apps/core_backend/safety.py#L375-L383), [`L492-L501`](../../apps/core_backend/safety.py#L492-L501)):**
   - Reusing `_DECLARATIVE_NEGATION_STEM` (`i|we`) for `_ALT_CLAUSE_REJECTION` leaves 3rd-person/existential negations (`courier isn't available`, `courier doesn't work`, `no courier`, `instead of waiting for a courier`) counted as affirmative covered alternatives.
   - **Verified end-to-end leak (`real:success`, `Engine='draft'`, `Runner` `calls=1`):**
     - `"Because courier isn't available, without visiting a physical store, can I still return this?"`

---

## 2. Minimum Safe Structural Alternative (Fail-Closed Quote Guard)

Rather than adding more forbidden phrases or post-quote regex branches, invert [`_mask_attributed_quotes`](../../apps/core_backend/safety.py#L519-L545) to **fail closed unless locally proven counterfactual**:

1. **Bind disavowal locally to the quote:** Only check `_QUOTE_REJECTION_SIGNAL` on `local_prefix` (or leading `post_quote[:32]`, e.g. `by mistake`/`wrongly`), never arbitrary earlier sentences (`"friend joked yesterday"` or `"Instead of buying..."` in another clause); allow `instead`/`rather` immediately after the quote only when directly pivoting to the covered alternative clause.
2. **Require positive covered-alternative exclusivity after any physical-store quote (fail closed on ambiguity):** After stripping leading `(?:instead\s+of|rather\s+than)\s+(?:doing\s+)?(?:that|it|so)`, if ANY post-quote clause contains a customer desire/question/modal (`want|need|plan|prefer|can|could|should|would|confirm|check|allowed|fine|ok|okay|possible|option|work` or `?`) that **either** lacks an unnegated `_COVERED_RETURN_ALTERNATIVE_PATTERN` in that same clause **or** still references pro-forms/action outside the covered alternative (`that|this|it|there|doing so|go|visit|visiting|going|alongside|before|too|or` before the alternative), **do NOT mask** (fail closed -> `escalate`). This closes declarative AND interrogative endorsements without phrase lists.
3. **Tighten `_ALT_CLAUSE_REJECTION` (`L382`):** Add 3rd-person/gerund rejection (`\b(?:no|not|without|never|instead\s+of\s+(?:waiting\s+for|using)?|rather\s+than\s+(?:waiting\s+for|using)?)\b` and `\b(?:isn't|aren't|doesn't|don't|won't|can't|cannot|unable|unavailable)\b[^.,;?!\n]*$` or post-match unavailability check within the same clause) so `"courier isn't available"` / `"instead of waiting for a courier"` never triggers `_has_covered_return_alternative_request`.

---

## 3. Verification Summary, Invariants & Limits Observed

- **Closed Prior Findings:** All `9/9` Worker B (`04e63ba3`) leaks and `6+1` original B (`9b4be434`) repros now block with **`0` external LLM calls** (`Engine=escalate(0)` / `Runner=escalate(0)` when `POL-RET` retrieved; `deliver` hits real `no_match` `abstain(0)`/`escalate(0)` and `escalate(0)` with `POL-RET` injected).
- **Fixed Gate & Focused Tests:** `43/43` fixed contract (`FAILS=[]`); `pytest tests/unit/test_safety_slice1_gap1_a.py -q` -> **`148 passed in 29.92s`** (A's broader `448 passed, 1 xfailed` suite not repeated); `ReDoS 4x20k = 134.81 ms`; `0` frozen case IDs in `safety.py`. Contrastive/valid positive controls (`Contrastive instead of`, `old page option ... instead`, `wrongly ... but I want ... instead`, `by mistake, instead ... partner post office`, `I see the option ...` fail-closed) match expectations.
- **Invariant SHA-256 Digests Verified Unchanged:**
  - `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
  - Audited `apps/core_backend/safety.py`: `cfda56b9388bfba5dc783e2d2a961525c27c4a614cdb9cee0b8ed06a00578204`
  - `approved_kb.v2.json` (`f8dcfbbb...`), `kb-release.json` (`cf450a72...`), `intent_policy.v2.json` (`8789ee26...`), `.local/training-cap-20261114.json` (`bc0445e0...`), `.local/ai.env` (`26d083c7...`), Fit2 `model.safetensors` (`f695b1fe...`) & `calibration_manifest.json` (`782c88db...`), serving `model.safetensors` (`dc7af8cf...`), `unseen_slice1_scope_gate_cases.jsonl` (`20bb9315...`), `unseen_slice1_negation_gate_cases.jsonl` (`c232bd6e...`).
- **Out-of-Scope / Pending Project Items:** `s1ng-sup-03` remains a `<0.55` dense retrieval miss in untouched `RetrievalAdapter`; Gap 2 (authority) and Gap 3 (NER) remain pending sequentially after Slice 1 clears cleanly for Worker C's `43 + 6 + historical` (`final >= 10`, `system >= 25`, `noise >= 260`) closure.
