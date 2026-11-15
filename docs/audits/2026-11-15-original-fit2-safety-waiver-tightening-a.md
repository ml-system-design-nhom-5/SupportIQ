# Original fit2 Safety Waiver Tightening Audit (Worker A)

- **Date:** 2026-11-15
- **Branch:** `minh`
- **Reviewed Blocker:** `docs/audits/2026-11-15-original-fit2-safety-scope-language-review-b.md` (**BLOCK** at `9b4be4347a487ebdc47167786a147c5dbad48466` reviewing `6f5fb995c57c1265b41f15f35a4cbbca3d3d4add`)
- **Modified Files:**
  - `apps/core_backend/safety.py` (`sha256: d485d91b255575eaa7ace2970a817ee141d65e944323ef2186ad3b3938686f77`)
  - `tests/unit/test_safety_slice1_gap1_a.py`
  - `docs/audits/2026-11-15-original-fit2-safety-waiver-tightening-a.md`
- **Untouched Adapter & Thresholds:** `apps/core_backend/retrieval/adapter.py` (`sha256: 3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`, `0.55` threshold) unchanged. No training, optimizer, calibrator, KB/release/policy, `.local/ai.env`, or frozen C gate edits.

---

## 1. Correction to `6f5fb995` Audit Documentation (Without Rewriting Sealed History)

Worker B accurately identified a discrepancy in `docs/audits/2026-11-15-original-fit2-safety-scope-language-fix-a.md:22`, which erroneously stated that the `{1,5}` object NP span did **not** apply after `without`. In `6f5fb995`, `(?:\s+{_NEG_CHANNEL_ACTION_CLAUSE})?` sat outside the alternation containing `|without...`, allowing `"Without bringing the box to a physical store, can I still return my headphones?"` to pass through without an approved return channel. That historic doc is preserved untouched as sealed history and explicitly corrected here: `without <transitive> <NP>` is allowed **only** when the object NP is pure (non-boundary, non-action) **and** the query affirmatively requests a covered return alternative (`courier`, `partner/designated post office`, `tiki app`, `order management`, `online return`).

---

## 2. Repro & Root-Cause Fixes (`apps/core_backend/safety.py`)

All `6` Worker B end-to-end FAIL-OPEN leaks (plus `deliver` and structural/quote/unqualified paraphrases) were reproduced end-to-end with an active `_PreLLMSpy` (`configured=True`) on both `Engine` and `PipelineRunner` (`16 failed, 1 passed` before the fix) and closed:

1. **Unified Action/Boundary Vocabulary & Both-Side NP Guard:**
   - Consolidated verb sets into `_NEG_CHANNEL_INTRANSITIVE_VERBS`, `_NEG_CHANNEL_TRANSITIVE_VERBS`, and `_NEG_CLAUSE_BOUNDARY_WORDS` (exception/contrast/preposition/modal/pronoun boundaries including `except`, `without`, `unless`, `instead`, `rather`, `only`, `just`, `head`, `stop`, `deliver`, `leave`, `wait`, `stay`, `keep`, `print`, `download`, `ask`, `mail`).
   - Used the **same** unified exclusion token matcher `_NEG_NON_OBJECT_TOKEN` for both `_NEG_OBJECT_NP_WORD` (prefix before match) and `_STORE_CHANNEL_VERB_PREFIX_SPLIT` (interior span inside `_PHYSICAL_STORE_CHANNEL_PATTERN` matches like `"return this item except at a physical store"`, where `m.start()` began at `return` and bypassed prefix-only guards).
   - **Closed repros:** `"I can't return this item except at a physical store"`, `"I can't return it except at a retail shop."`, `"I cannot return the opened TV without stopping by a physical store"`, `"I won't return my item instead head to a retail shop"`, `"I cannot ship my parcel home deliver it at a physical shop"`, `"Instead of courier, I can't return this item except at a physical store."`, `"We won't drop our parcel off only return at a physical shop."`, `"I will not return my item unless at a physical store."`

2. **Affirmative Covered Alternative Required for Physical-Store Waivers:**
   - Added `_clause_before` (splitting both punctuation/contrast via `_local_clause_prefix` and spaced dashes `" - "`/`"--"`), `_COVERED_RETURN_ALTERNATIVE_PATTERN`, `_ALT_CLAUSE_REJECTION`, and `_has_covered_return_alternative_request`.
   - Physical-store negation waivers in `_has_uncovered_channel_or_capability` now require **both** `_has_covered_return_alternative_request(normalized)` **and** clean `_is_negated_channel_alternative(...)`. Unqualified `without`/negated questions with no approved alternative fail closed (`escalate`, `['insufficient_evidence']`) pre-LLM while preserving C's explicit courier/post-office/app counterexamples (`s1ng-sup-04`, `"Without bringing the faulty headset into a local store, how do I book courier pickup?"`).
   - **Closed repros:** `"Without bringing the box to a physical store, can I still return my headphones?"`, `"Without visiting a physical store, can I still return my headphones?"`, `"We will not go to a physical store; can I still return this defective item?"`

3. **Credible Third-Party Declarative Reported Speech Quotes Only:**
   - Split `_QUOTE_ATTRIBUTION_PREFIX` into `_UI_OR_CONTRAST_QUOTE_PREFIX` and `_REPORTED_SPEECH_QUOTE_PREFIX` (finite declarative forms only: `said|says|asked|asks|told me/us|wrote|writes|stated|states|mentioned|mentions|reads?|joked|jokes|claimed|claims|suggested|suggests|replied|replies|advised|advises` — omitting bare modal infinitives like `advise`/`ask`).
   - Preserved punctuation before quotes (`:` / `,` / `-`) when slicing `local_prefix` via `_clause_before`, while rejecting masking when `before_verb` contains first-person subjects or request/question modals (`_QUOTE_FIRST_PERSON_OR_MODAL`), when post-quote text contains anaphoric endorsement (`_QUOTE_ENDORSEMENT_FOLLOWUP`, e.g., `"can I do that now?"`), or when the quoted span names a physical-store channel without an unquoted covered alternative outside the quote (`_has_covered_return_alternative_request(outside_quote)`).
   - **Closed repros:** `"I asked, 'can I walk into a physical shop to return this?'"`, `"Could support advise, 'bring it to a physical shop', and can I do that now?"`, `"We asked, 'can we walk into a physical shop to return this?'"`, `"Can someone advise, 'bring it to a physical shop', and can I do that now?"`, `"My friend joked 'just walk into a retail store', and can I do that now?"`, `"My friend joked 'just walk into a retail store' — can I do that or schedule courier pickup?"`, `"A friend joked 'use courier or walk into a retail store'?"`

---

## 3. Verification Results

| Check | Command / Scope | Observed Result |
| :--- | :--- | :--- |
| TDD RED (`test_gap1d`) | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -k test_gap1d -v --tb=line` | `16 failed, 1 passed, 109 deselected in 7.49s` |
| TDD GREEN (`test_safety_slice1_gap1_a.py`) | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q` (includes Engine & PipelineRunner `_PreLLMSpy` `calls == []`) | `127 passed in 20.40s` |
| Focused Core Suite | `tests/unit/test_safety_slice1_gap1_a.py` + boundary/grounding/guardrails/routing/retrieval/system/application/integration/completion suites (`-q`) | `427 passed, 1 xfailed in 99.72s (0:01:39)` |
| Frozen `43`-Case Predicate | Direct `policy_scope_requires_review` over `unseen_slice1_scope_gate_cases.jsonl` (`27`) + `unseen_slice1_negation_gate_cases.jsonl` (`16`) against real `POL-RET-001/002`, `POL-ORD-001` | `PASS_COUNT: 43` (`43_GATE_FAILS: []`) |
| ReDoS Stress Timing | `4 x ~20k`-char adversarial strings timed in Python | `70.81 ms` |

### Invariant SHA-256 Digests (Verified Unchanged)
- `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
- `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
- `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
- `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
- `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`
- `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json`: `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39`
- `artifacts/models/trained/distilbert-supportiq/model.safetensors`: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`
- `.local/training-cap-20261114.json`: `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`
- `.local/ai.env`: `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87`
- `artifacts/evaluation/original_fit2_safety_slice1_c_20261115/unseen_slice1_scope_gate_cases.jsonl`: `20bb9315c8d4be4670fd2e8157053eea29ee43eec6a7510029ccbb49a66b84d8`
- `artifacts/evaluation/original_fit2_safety_slice1_negation_c_20261115/unseen_slice1_negation_gate_cases.jsonl`: `c232bd6e21db2c497bc566ddc9e668f5efa3ca11e638fa3e6f6ba67fcc825a3a`

---

## 4. Residual Ambiguities & Handoff

- **Conservative Fail-Closed Trade-Off:** Unqualified negated physical-store queries without an explicit covered return alternative (e.g., *"We will not go to a physical store; can I still return this?"*), object spans >5 tokens or containing prepositions/actions, and unattributed or novel reporting-verb quotes intentionally escalate (`policy_scope_requires_review=True`) rather than risk fail-open leaks.
- **Unchanged Non-Slice-1 Residuals:** `s1ng-sup-03` remains a `<0.55` dense-retrieval miss (`RetrievalAdapter` untouched). Gap 2 (authority/personal-account outage) and Gap 3 (NER privacy) remain pending and unbundled.
- **Next:** Worker B review on this commit -> Worker C bounded closure verification across the frozen `43` cases + `6` B regressions + historical continuity floors before moving sequentially to Gap 2.
