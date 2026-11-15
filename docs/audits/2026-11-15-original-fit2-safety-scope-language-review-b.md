# Worker B — Targeted Code Review of Slice 1 Scope-Language Fix (`6f5fb995`)

- **Reviewer:** Worker B (`task_e604121d2c94`, `dispatch_id=ctx_c8fdd6b80b75`, branch `minh`)
- **Reviewed Commit:** [`6f5fb995c57c1265b41f15f35a4cbbca3d3d4add`](../../apps/core_backend/safety.py) ([`2026-11-15-original-fit2-safety-scope-language-fix-a.md`](2026-11-15-original-fit2-safety-scope-language-fix-a.md)), addressing Worker C's `BLOCK` (`1325a240efdf50deb25e1105a8108e4dc1cf5ad0`)
- **Upstream Adapter Invariant:** `git diff 03eb1231a9552fb22cf755a448d4fe6bd1225363..6f5fb995c57c1265b41f15f35a4cbbca3d3d4add -- apps/core_backend/retrieval/adapter.py` is **empty** (`sha256: 3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`, threshold `0.55` unchanged).
- **Verdict:** **`BLOCK`** — Although `6f5fb995` resolves the fixed `43`-case gate (`s1ng-sup-04`, `s1ng-sup-07`, `43/43` `policy_scope_requires_review` pass) and preserves historical continuity, the `+31/-3` changes in [`apps/core_backend/safety.py`](../../apps/core_backend/safety.py#L279-L350) introduce **`6` concrete end-to-end FAIL-OPEN bypasses** (`Engine='draft'`, `evaluate_evidence_scope=None`, real KB `POL-RET-*` retrieved) where **actual physical-store return requests are permitted**.

---

## 1. Explicit FAIL-OPEN Findings on Changed Lines (`safety.py:279-350`)

All 6 verified end-to-end leak rows below retrieve `ret=success` (`POL-RET-*`), pass `evaluate_evidence_scope() -> None`, and output **`Engine='draft'`** on `6f5fb995` (while `PipelineRunner` only stops at `OfflineGroundedSpyLLM` `grounding_failed`, NOT scope gating):

1. **Missing exception/contrast/verb stop-tokens in `_NEG_OBJECT_NP_WORD` ([L319-L330](../../apps/core_backend/safety.py#L319-L330)) -> FAIL-OPEN:**
   - **Verified leak:** `"I can't return this item except at a physical store"` -> `ev_scope=None`, `Engine='draft'` (`except`, `only`, `without`, `instead`, `rather`, `just`, `stop`/`stopping`, `head`/`heading`, `leave`/`leaving`, `print`/`printing`, `download`/`downloading`, `ask`/`asking`, `deliver`/`delivering` are omitted from `_NEG_OBJECT_NP_WORD`'s negative lookahead — note `deliver` is even in `_NEG_CHANNEL_TRANSITIVE_ACTION` at `L317` yet absent from `L327-L328`!).
   - **Verified leak:** `"I cannot return the opened TV without stopping by a physical store"` -> `ev_scope=None`, `Engine='draft'` (`opened TV without stopping` fits `{1,5}` object tokens before `by a physical store`).
   - **Verified leak:** `"I won't return my item instead head to a retail shop"` -> `ev_scope=None`, `Engine='draft'` (`my item instead head` fits `{1,5}` object tokens; `"I cannot ship my parcel home deliver it at a physical shop"` also returns `policy_scope_requires_review=False`).
2. **`without` unexpectedly chains into `{1,5}` transitive object NPs ([L333-L346](../../apps/core_backend/safety.py#L333-L346)) -> FAIL-OPEN & Doc Discrepancy:**
   - [`fix-a.md:22`](2026-11-15-original-fit2-safety-scope-language-fix-a.md#L22) states `{1,5}` NP tokens apply *"not after without"*, yet `(?:\s+{_NEG_CHANNEL_ACTION_CLAUSE})?` sits outside `|without...` at `L345`.
   - **Verified leak:** `"Without bringing the box to a physical store, can I still return my headphones?"` -> `ev_scope=None`, `Engine='draft'` (explicit physical-store return condition question is masked because `the box` matches `{1,5}` NP tokens).
3. **First-person & base-modal quote masking in `_QUOTE_ATTRIBUTION_PREFIX` ([L279-L284](../../apps/core_backend/safety.py#L279-L284)) -> FAIL-OPEN:**
   - **Verified leak:** `"I asked, 'can I walk into a physical shop to return this?'"` -> `ev_scope=None`, `Engine='draft'` (`[:,\-]?` plus `ask(?:s|ed)?` blanks the customer's own quoted direct request!).
   - **Verified leak:** `"Could support advise, 'bring it to a physical shop', and can I do that now?"` -> `ev_scope=None`, `Engine='draft'` (present/base `"advise, '...'"` blanks the quoted action despite the permissive follow-up request).

*(Separate non-fail-open residual noted transparently: `s1ng-sup-03` still hits `<0.55` dense retrieval `no_evidence` in `RetrievalAdapter`, which is unchanged classifier/embedding behavior rather than a `safety.py` scope false positive; `_NEG_CHANNEL_TRANSITIVE_ACTION` / `_QUOTE_ATTRIBUTION_PREFIX` remain bounded syntactic helpers with conservative escalation outside covered phrasing.)*

---

## 2. What Already Passed Cleanly on `6f5fb995`

- **Fixed `43`-Case Contract (`27` + `16`):**
  - Direct `policy_scope_requires_review()` against KB policy docs: **`43/43` (`fails=[]`)**.
  - Both prior C blockers **`s1ng-sup-04`** (`Engine='draft'`, `ev_scope=None`) and **`s1ng-sup-07`** (`policy_scope_requires_review=False`, `ev_scope=None`, dense `<0.55` without `POL-RET` match cleanly separated) are resolved; **`19/19`** `must_not_draft` (`11` + `8`) stay blocked (`0` leaks); dash/semicolon/contrast traps (`--`, `;`, `I cannot print a return label to bring...`, `joked + yet can I...`) all remain `True`.
  - Targeted `policy_scope_requires_review()` checks also passed on `neg_obj_bring_faulty_headset`, `neg_obj_4words`, `neg_obj_5words`, `neg_we_arent_trailing`, `joked_no_comma`, `joked_with_comma`, `suggested_colon`, `replied_comma` (`8/8` `False`).
- **Focused Tests, ReDoS, Case-ID Check & Continuity:**
  - `.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q` -> **`109 passed in 17.34s`** (Worker A also reported `409 passed, 1 xfailed` focused suite; not repeated verbatim).
  - `4 x ~20k`-char adversarial strings (`faulty * 3000`, `a the my heavy broken item * 1000`, `'word * 3000`, etc.): **`154.36 ms`** (no catastrophic backtracking). Zero frozen case IDs/sentences in `safety.py`.
  - Frozen `1,245`-row continuity replay unchanged: Runner gate leaks **`9 -> 0`**, Engine leaks **`11 -> 0`**, `noise420` **`260 -> 260`** (`>= 260`), `sa156` **`66 -> 66`**, `final24` **`11 -> 11`** (`>= 10`), `pos175` **`35 -> 34`** (`cls_dis_wrong_drop_0_841424c7a978` `<0.55` threshold). Raw Fit2 (`f695b1fe`, `macro_f1_12=0.857307`, `bare=267/420`) unchanged.
- **Invariant SHA-256 Checksums Verified Unchanged:**
  - `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
  - `apps/core_backend/safety.py`: `be54b31d3f95534bc164b104efd5ed4ee998947e6cd1d949d3fa2dc7f4152543`
  - `approved_kb.v2.json` (`f8dcfbbb...`), `kb-release.json` (`cf450a72...`), `intent_policy.v2.json` (`8789ee26...`), `.local/training-cap-20261114.json` (`bc0445e0...`), `.local/ai.env` (`26d083c7...`), Fit2 `model.safetensors` (`f695b1fe...`) & `calibration_manifest.json` (`782c88db...`), serving `model.safetensors` (`dc7af8cf...`), `unseen_slice1_scope_gate_cases.jsonl` (`20bb9315...`), `unseen_slice1_negation_gate_cases.jsonl` (`c232bd6e...`).

---

## 3. Minimal Required Fix Before B `PASS` -> C Bounded `43`-Case Closure

1. **Tighten `_NEG_OBJECT_NP_WORD` (`safety.py:319-330`):** Add contrast/exception/action exclusions (`except`, `without`, `only`, `just`, `instead`, `rather`, `not`, `never`, `head`, `heading`, `stop`, `stopping`, `deliver`, `delivering`, `leave`, `leaving`, `keep`, `keeping`, `print`, `printing`, `download`, `downloading`, `ask`, `asking`, `mail`, `mailing`, `wait`, `waiting`, `stay`, `staying`).
2. **Fix `without` + `{1,5}` NP scoping (`safety.py:338-346`):** Align code with `fix-a.md:22` or require an explicit allowed-channel ask when `without <transitive> <NP>` precedes a question so `"Without bringing the box to a physical store, can I still return my headphones?"` fails closed (`True`), while `"Without bringing the faulty headset into a local store, how do I book courier pickup?"` stays allowed (`False`).
3. **Prevent self/modal quote masking (`safety.py:279-284`):** Require non-first-person/non-modal reporting context for `ask(?:s|ed)?` / `advis(?:e[ds]?|ing)` / `suggest(?:s|ed)?` (e.g., disallow `(?<!\bi\s)(?<!\bwe\s)` on `asked` and restrict `advise`/`suggest` to declarative past/3rd-person `advised`/`suggested`/`suggests` unless an allowed channel follows, or keep base `advise` excluded) so `"I asked, 'can I walk into a physical shop to return this?'"` and `"Could support advise, 'bring it to a physical shop', and can I do that now?"` fail closed (`True`).
4. **Open Sequential Slices Remaining:** Gap 2 (authority/personal-account outage) and Gap 3 (NER privacy fail-closed) remain **pending** until Slice 1 clears cleanly.
