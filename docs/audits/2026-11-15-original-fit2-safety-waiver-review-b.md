# Worker B — Security Re-Review of Slice 1 Waiver Tightening (`c466ffaa`)

- **Reviewer:** Worker B (`task_c3b71a0e697b`, `dispatch_id=ctx_25affb61d1d8`, branch `minh`)
- **Reviewed Commit:** [`c466ffaa87b3b1d160657715e14f3a9323037797`](../../apps/core_backend/safety.py) ([`2026-11-15-original-fit2-safety-waiver-tightening-a.md`](2026-11-15-original-fit2-safety-waiver-tightening-a.md)) vs prior B `BLOCK` (`9b4be4347a487ebdc47167786a147c5dbad48466`)
- **Upstream Adapter Invariant:** `git diff 6f5fb995..c466ffaa87b3b1d160657715e14f3a9323037797 -- apps/core_backend/retrieval/adapter.py` is **empty** (`sha256: 3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`, threshold `0.55` unchanged).
- **Verdict:** **`BLOCK`** — All `6` (`+1` `deliver`) prior B fail-open leaks are closed (`0` external LLM calls), the `43`-case gate and `19/19` `must_not_draft` pass, and `test_safety_slice1_gap1_a.py` passes (`127/127`). However, the oversized `+143/-26` patch in [`apps/core_backend/safety.py`](../../apps/core_backend/safety.py#L279-L654) (`sha256: d485d91b...`) leaves **concrete changed-line end-to-end FAIL-OPEN bypasses** where real `RetrievalAdapter` retrieves approved `POL-RET-*` (`status='success'`), `Engine` outputs **`recommendation='draft'`**, and `PipelineRunner` **invokes the external LLM (`calls == 1`)**.

---

## 1. Concrete Changed-Line Security Bypasses (`BLOCK`)

Every query below was verified end-to-end against real `approved_kb.v2.json` via real `RetrievalAdapter` (`status='success'`) and `_SpyLLM(configured=True)`: on all `9` queries, `policy_scope_requires_review() -> False`, **`Engine` returns `draft`**, and **`PipelineRunner` invokes the external LLM (`calls=1`)** (`manual_fallback ['requires_authority', 'grounding_failed']` only because `StubLLM` fails offline grounding).

1. **Cohesion / missing exclusion tokens in `_NEG_CLAUSE_BOUNDARY_WORDS` ([`safety.py:331-354`](../../apps/core_backend/safety.py#L331-L354)):**
   - `_ALTERNATIVE_NEG_PREFIX` ([`L126`](../../apps/core_backend/safety.py#L126)) already includes `excluding`, yet `_NEG_CLAUSE_BOUNDARY_WORDS` ([`L333`](../../apps/core_backend/safety.py#L333)) omits `excluding`, `besides`, and `save`. Because `"return it besides"` / `"return this excluding"` match as `<=3` interior tokens inside `_PHYSICAL_STORE_CHANNEL_PATTERN`, `_STORE_CHANNEL_VERB_PREFIX_SPLIT` passes `_NEG_NON_OBJECT_TOKEN` and waives them whenever a covered alternative appears.
   - **Verified LLM-invoking bypasses (`Engine='draft'`, `Runner` `calls=1`):**
     - `"I won't return this excluding at a physical store, can I use a courier?"`
     - `"I can't return it besides at a physical store, or can I use a courier?"`
     - `"I won't return my item save at a physical store, or can I book a courier?"`
2. **Brittle `_QUOTE_ENDORSEMENT_FOLLOWUP` closed whitelist ([`safety.py:293-298`](../../apps/core_backend/safety.py#L293-L298), [`L522`](../../apps/core_backend/safety.py#L522)):**
   - `_mask_attributed_quotes` blanks third-party physical-store quotes whenever `outside_quote` contains an affirmative alternative (`courier` / `app`), rejecting ONLY a closed 7-phrase list (`do that|follow that|try that|allowed|possible|okay|ok`). Any natural endorsement question outside those 7 strings masks the quoted imperative and lets the unsupported request reach the LLM.
   - **Verified LLM-invoking bypasses (`Engine='draft'`, `Runner` `calls=1`):**
     - `"My friend said 'walk into a physical store to return it' — is that an option, or courier pickup?"`
     - `"Someone told me 'return it in-store' — does that work, or should I use the app?"`
     - `"A friend said 'bring it to a physical store', should I go ahead with that or use courier?"`
3. **`_UI_OR_CONTRAST_QUOTE_PREFIX` unguarded early bypass ([`safety.py:279-282`](../../apps/core_backend/safety.py#L279-L282), [`L512-L515`](../../apps/core_backend/safety.py#L512-L515)):**
   - Splitting `_QUOTE_ATTRIBUTION_PREFIX` put an unconditional `continue` at `L515` for `button|tab|section|page|menu|option|called|labeled|titled` **before** checking `_QUOTE_FIRST_PERSON_OR_MODAL`, `_QUOTE_ENDORSEMENT_FOLLOWUP`, or `_has_covered_return_alternative_request(outside_quote)`. Direct customer modal/UI requests with zero covered alternative are blanked and permitted pre-LLM.
   - **Verified LLM-invoking bypasses (`Engine='draft'`, `Runner` `calls=1`):**
     - `"Can I use the option 'return at a physical store' to send back my order?"`
     - `"Where do I click the button 'drop off at a physical store' so I can return this?"`
4. **`_ALT_CLAUSE_REJECTION` cohesion miss vs `_DECLARATIVE_CHANNEL_NEG_PREFIX` ([`safety.py:378-382`](../../apps/core_backend/safety.py#L378-L382) vs [`L388-L389`](../../apps/core_backend/safety.py#L388-L389)):**
   - `_DECLARATIVE_CHANNEL_NEG_PREFIX` rejects `(?:i'm|we're|(?:i|we)\s+(?:am|are))\s+(?:not|unable)`, yet `_ALT_CLAUSE_REJECTION` right above it omits `am not` / `'m not` / `are not` / `unable`. Negated alternative clauses containing `"using the app"` therefore satisfy `_has_covered_return_alternative_request` (`True`) and unlock store-negation waivers.
   - **Verified LLM-invoking bypass (`Engine='draft'`, `Runner` `calls=1`):**
     - `"I am not using the app, and without visiting a physical store, can I still return this?"`

### Complexity Assessment & Minimal Non-Bloating Fix (No New Whitelists)
- `+143/-26` in [`safety.py`](../../apps/core_backend/safety.py) exceeded expected diff size largely due to `_QUOTE_ENDORSEMENT_FOLLOWUP` + duplicate UI/speech branches. Adding more endorsement phrases will keep bloating regexes and leaking.
- **Minimal fix (actually shrinks regex surface):**
  1. Delete `_QUOTE_ENDORSEMENT_FOLLOWUP`; for `_PHYSICAL_STORE_CHANNEL_PATTERN` matches inside third-party reported quotes alongside an outside covered alternative, mask **only** when the outside context contains explicit rejection/contrast (`_ALTERNATIVE_NEG_PREFIX`, `_DECLARATIVE_CHANNEL_NEG_PREFIX`, `instead`, `rather`, `but`, `though`, `however`, `wrongly`, `mistake`, `joked`), instead of trying to enumerate every endorsement phrase. Keep UI-noun labels (`called|labeled|titled|button|tab|section|page|menu|option`) subject to `_QUOTE_FIRST_PERSON_OR_MODAL` (leaving only `instead of`/`rather than` as unconditional contrastive UI/alt waivers).
  2. Add `excluding|besides|save|barring` to `_NEG_CLAUSE_BOUNDARY_WORDS` (`L333`) for cohesion with `_ALTERNATIVE_NEG_PREFIX` (`L126`).
  3. Add `(?:(?:i'm|we're|(?:i|we)\s+(?:am|are))\s+(?:not|unable))` to `_ALT_CLAUSE_REJECTION` (`L378-L381`) matching `L388-L389`.

---

## 2. Verification Summary & Remaining Limits

- **Prior `6` B FAIL-OPEN Repros (`+1` `deliver`):** All `6` physical-store leaks now block pre-LLM with **`0` external LLM calls** on both `Engine` (`escalate(0)` with real `RetrievalAdapter` `return_product`, e.g. `b_orig_2` `['requires_authority', 'insufficient_evidence']`; `escalate(0) ['insufficient_evidence']` with wrong canonical intent `track_order` + injected `POL-RET-001/002`) and `PipelineRunner` (`escalate(0)` with real `RetrievalAdapter` `return_product`, `clarify(0) ['missing_order_id']` on `track_order`; non-canonical `order_status` stops at `manual_fallback(0) ['invalid_model_output']`). The 7th `deliver` probe hits real dense `no_match` (`eng=abstain(0)`, `run=escalate(0)`) on `RetrievalAdapter`, and `eng=escalate(0) ['insufficient_evidence']` when `POL-RET-001/002` is injected.
- **Bounded Contract & Laundering Probes (`43` fixed + `19` `must_not_draft` + mixed clauses):**
  - Fixed `43` cases: **`43/43` PASS (`[]` fails)**.
  - All `19` `must_not_draft` (`x2` intents `return_product` / `order_status` with injected `POL-RET-001/002`): **`0` LLM/draft leaks**.
  - Mixed-clause laundering & positive-control probes (`"Can I drop my return off at a physical store, or can I use a courier?"`, `"Instead of going to a physical store, use a courier — wait, actually can I return it at a retail shop?"`, `"I prefer courier pickup, or can I drop my return off in-person too?"`, `"I can't go to a physical store, book courier pickup, or can I drop by a retail shop?"`, `"Support told me 'drop it off at a retail store' when I called yesterday."`, and supported courier/quote counterexamples): **`OK`**.
- **Focused Tests, ReDoS & Hygiene:**
  - `.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q` -> **`127 passed in 20.20s`** (A's broader `427 passed, 1 xfailed` suite not repeated).
  - `4 x ~20k`-char ReDoS stress inputs: **`134.43 ms`**. Zero frozen case IDs or exact bench texts in `safety.py`. Typed reasons and `validate_analysis` contracts preserved.
- **Invariant SHA-256 Digests (All Confirmed Unchanged):**
  - `adapter.py` (`3bd797da...`), `approved_kb.v2.json` (`f8dcfbbb...`), `kb-release.json` (`cf450a72...`), `intent_policy.v2.json` (`8789ee26...`), `.local/training-cap-20261114.json` (`bc0445e0...`), `.local/ai.env` (`26d083c7...`), Fit2 `model.safetensors` (`f695b1fe...`) & `calibration_manifest.json` (`782c88db...`), serving `model.safetensors` (`dc7af8cf...`), `unseen_slice1_scope_gate_cases.jsonl` (`20bb9315...`), `unseen_slice1_negation_gate_cases.jsonl` (`c232bd6e...`).
  - Audited `safety.py` SHA-256: `d485d91b255575eaa7ace2970a817ee141d65e944323ef2186ad3b3938686f77`.
- **Documented Residual Non-Blocker Limits:**
  - Heuristic finite-vocabulary regex gates do not constitute universal semantic entailment coverage (novel reporting verbs, physical-venue synonyms, or post-predicate negation of alternatives like `"Courier pickup is unavailable, so without visiting a physical store, can I still return this?"` where no physical-store return is requested remain outside bounded scope, while ambiguous unqualified physical-store queries fail closed).
  - `s1ng-sup-03` remains a `<0.55` dense retrieval miss in untouched `RetrievalAdapter`; Gap 2 (authority) and Gap 3 (NER) remain open sequentially after Slice 1 clears.
