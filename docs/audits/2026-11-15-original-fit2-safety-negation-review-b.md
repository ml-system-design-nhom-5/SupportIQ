# Worker B — Targeted Code Review of Slice 1 Negation Fix (`34733574`)

- **Reviewer:** Worker B (`task_aca4c12b9cd9`, `dispatch_id=ctx_a1a0752db717`, branch `minh`)
- **Reviewed Commit:** [`34733574e738a7dc932efbf0b8870a68ac3dd4c4`](../../apps/core_backend/safety.py) ([`2026-11-15-original-fit2-safety-negation-fix-a.md`](2026-11-15-original-fit2-safety-negation-fix-a.md)), addressing Worker C's `BLOCK` (`3bbbe5ff60f9962b0acbe0808f1d1ab95c2940c7`)
- **Upstream Adapter Invariant:** `git diff 03eb1231a9552fb22cf755a448d4fe6bd1225363..34733574e738a7dc932efbf0b8870a68ac3dd4c4 -- apps/core_backend/retrieval/adapter.py` is **empty** (`sha256: 3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`).
- **Verdict:** **`PASS`** — **Ready for Worker C bounded re-evaluation (`27`-case scope gate + new unseen check + historical regression check).** Local modal/motion negation works strictly within clause bounds without creating any global bypass, dash/semicolon/contrast positive actions stay blocked, all prior `11` Engine / `9` Runner closures hold, and `noise420 >= 260` / `sa156 >= 25` / `final24 >= 10` remain preserved.

---

## 1. Diff & Clause-Locality Audit (`apps/core_backend/safety.py`)

Inspected full diff `faac0e72..34733574` (`24 +-` lines in [`safety.py#L307-L435`](../../apps/core_backend/safety.py#L307-L435), `69 +` lines in [`test_safety_slice1_gap1_a.py`](../../tests/unit/test_safety_slice1_gap1_a.py)):

1. **Clause-Anchored Motion + Modal Negation (`_NEG_CHANNEL_MOTION_OR_ACTION` & `_DECLARATIVE_CHANNEL_NEG_PREFIX`):**
   - `_DECLARATIVE_CHANNEL_NEG_PREFIX` remains anchored at `\s*$` immediately before the matched channel/capability span in `_local_clause_prefix()` (`[.,;?!:\n]|\b(?:but|however|actually|yet|though)\b`), adding `cannot|can not|can't|couldn't|won't|wouldn't|unable|prefer not to|rather not` plus one optional attitude verb, optional `to|for`, one optional `_NEG_CHANNEL_MOTION_OR_ACTION` (`go|travel|walk|head|drive|commute|come|visit|stop by|drop in|return|drop off|bring|take|print|download|generate|use`), and trailing determiners/prepositions.
   - **No global bypass:** Any intervening text breaks the `$` anchor, so negated wrong objects (*"I cannot print a label so I want to take it back to a retail shop"*), compound shifts (*"I cannot wait for a courier — let me drop it off at a physical shop"*), and negative questions (*"Why can't I drop off my return at one of your shops?"*, *"Can't I just take this back to a retail store?"*) continue to escalate (`True`).
2. **Dash-Split Guard (`_is_negated_channel_alternative`):**
   - Checking `re.search(r"\s-\s|--", tail)` after normalized `\u2014 -> -` (`_QUOTE_TRANSLATION`) blocks inheritance when a dash separates `"Instead of ..."` from a positive unsupported request (*"Instead of courier — physical store return please."*, *"Instead of courier -- take it back at a retail storefront."*).
3. **Zero Benchmark Hacking or Drift & Safe Regex Complexity:**
   - Zero case IDs (`s1g-*`, `uns-*`, `contrast_auth_pos_eval*`, `sup-return_product-03`) or hardcoded C gate sentences appear in `safety.py`.
   - `4 x ~20k`-char adversarial strings with repeated optional words (`"I do not want " + "to a the my " * 2000`, etc.) ran `_DECLARATIVE_CHANNEL_NEG_PREFIX.search` + `policy_scope_requires_review` in **`175.04 ms` total** (no catastrophic backtracking).
   - Emits only existing `AI_REASONS` (`"no_valid_document"`, `"insufficient_evidence"`).

---

## 2. Independent Verification Results on `34733574`

> All checks below ran read-only on `34733574e738a7dc932efbf0b8870a68ac3dd4c4` with `0` training runs, `0` model/KB/config edits, and `0` paid LLM calls. Raw Original Fit2 metrics (`noise420 macro_f1_12=0.857307`, `bare=267/420`) remain untouched.

- **Frozen `27`-Case Gate ([`unseen_slice1_scope_gate_cases.jsonl`](../../artifacts/evaluation/original_fit2_safety_slice1_c_20261115/unseen_slice1_scope_gate_cases.jsonl), `20bb9315...`, untouched):**
  - Direct `policy_scope_requires_review()` against KB policy docs: **`27/27` (`fails=[]`)** — all `11/11` must-escalate return `True` and all `16/16` supported counterexamples return `False` (specifically closing Worker C's prior failures `s1g-neg-sup-01` and `s1g-neg-sup-03`).
  - Production `Engine(intent_override=gold for supported)` & `PipelineRunner` pre-LLM scope gate replay: **`0` leaks across `11/11` `must_escalate` cases** and **`16/16` supported (`Engine='draft'`, `evaluate_evidence_scope=None`)**.
- **Focused Pytest Suite:**
  - `.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py ... -q` -> **`384 passed, 1 xfailed in 93.95s`** (pre-existing `test_engine_should_not_draft_track_order_without_order_id` `xfailed`).
- **Independent Adversarial & Counterexample Battery (`28/28` passed: `0` allow failures, `0` escalate failures):**
  - **Preserved Supported (`13/13` `False`):** modal/motion negations (`"I do not want to go to a physical store; can I schedule courier pickup instead?"`, `"I cannot travel to a retail store branch — how does Tiki's free courier pickup work..."`, `"I can't walk to a retail shop..."`, `"We won't head into a local shop..."`, `"We're unable to drive to a physical store branch..."`, `"I'd prefer not to visit a storefront counter..."`, `"Without visiting a retail shop..."`, `"I don't want to return my item at a physical shop — send a courier."`, `"I do not need to print a prepaid return label — courier pickup is fine."`, `"I cannot download a printable label..."`), partner post office drop-off, courier shipping label (`ORD-1005`), and single-order history (`ORD-1005`).
  - **Blocked Positive Actions (`15/15` `True`):** dash/semicolon contrast clauses (`"Instead of courier — physical store return please."`, `"Instead of courier -- take it back..."`, `"Instead of waiting for courier; can I drop off..."`, `"I do not want to wait for courier; return in store please."`, `"I cannot wait for a courier — let me drop it off at a physical shop."`, `"I cannot travel to a retail store today — can I drop it off at a local shop tomorrow?"`, `"I cannot wait for courier pickup, but want to return at a retail storefront."`), negated wrong object (`"I cannot print a label so I want to take it back to a retail shop."`), negative questions (`"Why can't I drop off my return at one of your shops?"`, `"Can't I just take this back to a retail store?"`), mixed digital+physical + attributed/direct quotes (`"I bought this on the online store website — don't redirect me there, I want to drop it off at a physical store."`, `"Can a customer 'go to a physical store' to return an item?"`, `"Someone wrote 'online app pickup works', yet I want to bring this jacket into a physical outlet."`).
- **Frozen `1,245`-Row Replay Continuity Check (No Regressions):**
  - Pre-LLM Runner gate leaks: **`9 -> 0`**; `Engine` leaks: **`11 -> 0`**.
  - Supported gold-matched retention: `noise420` **`260 -> 260`** (`>= 260`), `sa156` **`66 -> 66`** (within C's `sup34=25`), `final24` **`11 -> 11`** (`>= 10`), `pos175` **`35 -> 34`** (`cls_dis_wrong_drop_0_841424c7a978` `<0.55` unboosted threshold).

---

## 3. Invariants Verified & Remaining Open Limits

- **SHA-256 Checksums Unchanged:**
  - `apps/core_backend/retrieval/adapter.py`: `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`
  - `apps/core_backend/safety.py`: `2981a703641aed2af3ea40408768a821203226b69cfa53816271f15abe9b3aea`
  - `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
  - `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
  - `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
  - `.local/training-cap-20261114.json`: `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`
  - `.local/ai.env`: `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87`
  - `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`
  - `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json`: `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39`
  - `artifacts/models/trained/distilbert-supportiq/model.safetensors`: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`
  - `artifacts/evaluation/original_fit2_safety_slice1_c_20261115/unseen_slice1_scope_gate_cases.jsonl`: `20bb9315c8d4be4670fd2e8157053eea29ee43eec6a7510029ccbb49a66b84d8`
- **Remaining Limits & Sequential Plan:**
  - Worker C now holds the bounded re-evaluation of the frozen `27`-case gate (plus any fresh unseen negation/channel probes) and historical regression confirmation on `34733574`.
  - Non-transposition typos (`"in storr"` / `"lbel"`) and fluent retail-adjacent OOD (`>= 0.55` aligned cosine) remain residual (`training-cap` `2/2` exhausted, `STOP`).
  - **Gap 2** (`Engine`/backend authority & `track_order` slot parity) and **Gap 3** (NER fail-closed privacy guard) remain **OPEN** for sequential implementation after Slice 1 clears Worker C.
