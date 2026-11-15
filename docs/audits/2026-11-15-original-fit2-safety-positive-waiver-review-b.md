# Worker B — Security Re-Review of Inverted Positive-Proof Quote Waiver Fix (`a316377a`)

- **Reviewer:** Worker B (`task_6b7abaa971e9`, `dispatch_id=ctx_320a83a049fa`, branch `minh`)
- **Reviewed Commit:** [`a316377abdb8d32a894efb161178a573cccf3473`](../../apps/core_backend/safety.py) ([`2026-11-15-original-fit2-safety-positive-waiver-fix-a.md`](2026-11-15-original-fit2-safety-positive-waiver-fix-a.md)) vs prior B `BLOCK` (`c1c2a76611f704b1358a9428c4007cadf2435da4`)
- **Upstream Adapter Invariant:** `git diff 717ac038..a316377abdb8d32a894efb161178a573cccf3473 -- apps/core_backend/retrieval/adapter.py` is **empty** (`sha256: 3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`, threshold `0.55` unchanged).
- **Verdict:** **`PASS`** — Commit `a316377a` performs a **genuine structural inversion** rather than renaming a phrase blacklist. Default behavior for physical-store quotes in [`_mask_attributed_quotes`](../../apps/core_backend/safety.py#L629-L651) is now **fail-closed retention**, isolating each quote pair independently ([`_collect_non_overlapping_quotes`](../../apps/core_backend/safety.py#L590-L602), [`_quote_bounds_and_prefix`](../../apps/core_backend/safety.py#L605-L626)), requiring positive local disavowal (`_CONTRASTIVE_QUOTE_PREFIX`, `_LOCAL_QUOTE_FALSITY`, or leading `_POST_QUOTE_DISAVOWAL_PREFIX`) and positive per-clause return-action coverage without unresolved pro-forms ([`_post_quote_is_exclusively_covered`](../../apps/core_backend/safety.py#L569-L587)), and disqualifying 3rd-person/gerund alternative negations via [`_is_covered_alt_clause_negated`](../../apps/core_backend/safety.py#L547-L566).

---

## 1. Structural Security Assessment

1. **Truly positive proof vs hidden absence check:**
   - `_is_ambiguous_or_endorsed_post_quote` and global `_QUOTE_REJECTION_SIGNAL.search(outside_quote)` are deleted.
   - Masking requires: (a) local contrastive or 3rd-person attribution with zero `_QUOTE_FIRST_PERSON_OR_MODAL` hits before the introducer (`UI` labels like `option`/`button`/`tab` share the identical modal guard); (b) explicit falsity or disavowal strictly scoped inside that quote's `(local_prefix, local_post)` bounds (preventing unrelated earlier quotes/clauses from unlocking a subsequent physical-store quote); and (c) every clause after the disavowal prefix (`_POST_QUOTE_CLAUSE_SPLIT`) affirmatively matching `_COVERED_RETURN_ALTERNATIVE_PATTERN` **plus** `_COVERED_ALT_RETURN_ACTION` while failing `_ALT_CLAUSE_REJECTION`, `_ALT_CLAUSE_POST_NEG`, and `_UNRESOLVED_QUOTE_REFERENCE`.
2. **Contractions & bounded quote complexity:**
   - `_SINGLE_QUOTED_SPAN` (`{1,240}` bounded quantifier with disjoint character classes) does not open or close on word-internal contractions/possessives (`won't`, `can't`, `I'll`). `4 x 20k`-char ReDoS stress inputs completed in **`128.13 ms`** (`0` catastrophic backtracking; Worker A also reported `15.36 ms` on 4 multi-hundred-token inputs).
   - Diff size is larger (`154 insertions(+), 47 deletions(-)` vs `717ac038`, `270 insertions(+), 20 deletions(-)` vs `12d358d3`), justified by the structural quote-partitioning helpers rather than unmaintainable phrase whitelists; zero frozen case IDs exist in `safety.py`.

---

## 2. Independent Pre-LLM End-to-End Verification (`0` External LLM Calls)

Tested end-to-end across **real `RetrievalAdapter`** (`approved_kb.v2.json` + `kb-release.json`), injected approved **`POL-RET-002`/`POL-RET-001`**, wrong canonical intent **`track_order`**, and **`_SpyLLM(configured=True)`** on both `Engine.analyse()` and `PipelineRunner.run()`:

- **Fixed bounded contract (`43` cases):** **`43/43` PASS (`FAILS=[]`)**.
- **All `19/19` `must_not_draft` cases (`POL-RET` end-to-end):** **`0` leaks** (`Engine='escalate'`, `Runner='escalate'`, `0` external LLM calls).
- **Prior `8/8` (`c1c2a766`) B FAIL-OPEN leaks:** **`0` failures** — `0` external LLM calls across `real RetrievalAdapter`, injected `POL-RET`, and wrong-intent `track_order` (`Engine=escalate(0)` / `Runner=escalate(0)` on `POL-RET` and on all 6 `real:success` rows; `real` returns `abstain(0)`/`escalate(0)` on the 2 dense-miss rows `"walk into a physical store ... along with the app"` and `"just walk into a retail store ... before booking courier"`, and `track_order` returns `Engine=escalate(0)` / `Runner=clarify(0)`).
- **Prior `9/9` (`04e63ba3`) B FAIL-OPEN leaks:** **`0` failures** (`Engine=escalate(0)`, `Runner=escalate(0)` on both `real RetrievalAdapter` `success` and injected `POL-RET`).
- **Original `6+1` (`9b4be434`) B repros (`+deliver`):** **`0` failures** (`Engine=escalate(0)`, `Runner=escalate(0)` across all `6` physical-store repros; `deliver` hits real `no_match` `abstain(0)`/`escalate(0)` and `escalate(0)` with `POL-RET` injected).
- **Structural / metamorphic probes:** Blocked cleanly (`escalate(0)`):
  - Multi-quote falsity propagation guard (`"Support wrongly told me 'return at a physical store' before a friend wrote 'bring it in-person', instead book courier pickup."`)
  - Extra non-action clause (`"...instead ship courier and also check my warranty."`)
  - Trailing/bare non-action mentions (`"...instead courier won't work."`, `"...instead let's check via the app."`, `"...instead book courier unless doing so fails."`)
  - Contraction paired with unquoted store ask (`"I won't ask 'why can't I return at a physical store', instead how do I book courier pickup?"`)
  - UI modal (`"Can I click the button 'return at a physical store' instead of booking courier?"`)
- **Positive supported controls (`Engine='draft'` allowed with `POL-RET`):** Wrongly/mistake/old-page/`instead of`/negated-store counterfactuals paired with courier/post-office/app (`5/5` allowed with `POL-RET` injected; courier/app/old-page/negated-store also reach `real:success/draft`, while `post office` without courier hits `<0.55` dense `no_evidence` on `RetrievalAdapter`). Contraction + valid quote + app (`"I don't mind — support wrongly said 'return at a physical store', instead how do I return in the Tiki app?"`) also stayed allowed cleanly.
- **Focused unit suite:** `.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q` -> **`181 passed in 33.29s`** (Worker A's broader `481 passed, 1 xfailed` suite not repeated).

---

## 3. Verified Invariants & Documented Residual Limits

- **Invariant SHA-256 Digests Confirmed Unchanged:**
  - `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f` (threshold `0.55`)
  - Audited `apps/core_backend/safety.py`: `45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000`
  - `approved_kb.v2.json` (`f8dcfbbb...`), `kb-release.json` (`cf450a72...`), `intent_policy.v2.json` (`8789ee26...`), `.local/training-cap-20261114.json` (`bc0445e0...`), `.local/ai.env` (`26d083c7...`), Fit2 `model.safetensors` (`f695b1fe...`) & `calibration_manifest.json` (`782c88db...`), serving `model.safetensors` (`dc7af8cf...`), `unseen_slice1_scope_gate_cases.jsonl` (`20bb9315...`), `unseen_slice1_negation_gate_cases.jsonl` (`c232bd6e...`).
- **Documented Conservative Coverage Cost & Finite-Grammar Limits (Non-Blockers):**
  - This guard enforces positive lexical/clause structure inside Slice 1 channels and does not claim universal NLU comprehension.
  - Multi-clause narratives after a valid quote disavowal that include any non-return clause conservatively escalate rather than risk partial masking; out-of-contract negative paraphrases remain conservative fail-closed.
  - **Minor finite-reference note:** `_UNRESOLVED_QUOTE_REFERENCE` includes `that`, `there`, `doing so`, and bare `this`, omitting `(?:do|try|follow)\s+it\b` so item-referential `pick it up`/`return it` stays supported; consequently, after both explicit falsity (`"wrongly told me"`) and `"instead ... with courier pickup"`, `"Support wrongly told me 'return at a physical store', instead can I still do it with courier pickup?"` resolves to `draft` (outside bounded contract; not treated as a blocker).
  - **Next (Closure & Sequential Gaps):** Hand off to Worker C for bounded `43 + historical` closure (`final >= 10`, `system >= 25`, `noise >= 260`), keeping untouched `s1ng-sup-03` (`<0.55` retrieval miss in `adapter.py`), before Worker A proceeds sequentially to **Gap 2 (authority)** and **Gap 3 (NER)**.
