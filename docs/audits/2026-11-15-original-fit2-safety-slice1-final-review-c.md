# Original Fit2 System Safety Slice 1 Final Re-Review (Worker C)

**Verdict:** `BLOCK` *(scoped strictly to **System Safety Slice 1 / Gap 1**; NOT raw ML, NOT whole project)*  
**Branch / Reviewed HEAD:** `minh` @ `ebf6c72dfb42042eb81ed68ed3cb1f55b76b41a4` (Worker B PASS on Worker A source commit `34733574e738a7dc932efbf0b8870a68ac3dd4c4`)  
**Diff Scope Since `12d358d3` / `3bbbe5f`:** `git diff --name-only 12d358d3b301680a5d1ab910d684a1102bcd509c..HEAD -- apps/ data/` modifies **only** `apps/core_backend/safety.py` (`sha256: 2981a703641aed2af3ea40408768a821203226b69cfa53816271f15abe9b3aea`); `apps/core_backend/retrieval/adapter.py` (`3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`) is unchanged.  
**Execution Scope / Constraints:** `0` training/optimizer/calibrator/rejector edits, `0` paid/live LLM calls (`_MockNoCallLLM` / `_OfflineValidSpyLLM`), `cap=2/2`, `training_stopped=true`, `no_more_training_authorized=true`. Live current `Engine` & `PipelineRunner` executed across **`1,450` rows** (`27` frozen gate + `16` new unseen gate + `1,406` rows across all `12` prior suites + `bitext` `sample_031639`, `eval_seconds=111.87s`, `total_duration_seconds=130.69s`) plus `43` isolated gold-intent `Engine` & `Runner` probe runs.

---

## 1. Unchanged Invariants (SHA-256 Verified)

| Component | Verified SHA-256 |
|---|---|
| Active Orig Fit2 weights (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`) | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (`T=1.0`, `calibrated=true`, `selective_rejector_enabled=false`) |
| Orig Fit2 calibration (`calibration_manifest.json`) | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` |
| Pinned serving weights (`artifacts/models/trained/distilbert-supportiq/model.safetensors`) | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| `approved_kb.v2.json` / `kb-release.json` / `intent_policy.v2.json` | `f8dcfbbdbb...` / `cf450a7275...` / `8789ee26ac...` |
| `.local/training-cap-20261114.json` / `.local/ai.env` | `bc0445e07c...` (`2/2`, `STOP`) / `26d083c75a...` |
| Prior frozen 27-case gate (`unseen_slice1_scope_gate_cases.jsonl`) | `20bb9315c8d4be4670fd2e8157053eea29ee43eec6a7510029ccbb49a66b84d8` |
| New frozen 16-case gate (`unseen_slice1_negation_gate_cases.jsonl`) | `c232bd6e21db2c497bc566ddc9e668f5efa3ca11e638fa3e6f6ba67fcc825a3a` (`0` overlap vs 146 literals in `test_safety_slice1_gap1_a.py` & 7,587 prior rows) |
| Eval output bundle (`slice1_negation_paired_evaluation.json`) | `30047bc10940378e397eb3b00174c5af0b6d74e2dd9561918ef2b651956f9ced` |

---

## 2. Re-Run of Frozen `27`-Case Gate (`unseen_slice1_27`, `20bb9315...`) -> **`27/27` PASS**

- **Natural `Orig Fit2` (`Engine`, `Runner`, `priv_engine`, `priv_runner`):**
  - `11/11` `must_not_draft`: **`0` leaks** across all system surfaces.
  - `16/16` supported: **`0` false scope escalations vs `1bf9e6af` pre-Slice-1 baseline** (`s1g-neg-sup-01` & `s1g-neg-sup-03` flipped back `escalate -> manual_fallback` on `Engine` & `priv_engine`, dropping `insufficient_evidence`; non-draft status `14/16` is strictly classifier confidence `<0.65`, NOT Slice 1 rule interference).
- **Isolated Gold-Intent Override (`Engine` AND `PipelineRunner` + `policy_scope_requires_review`):**
  - **`11/11` `must_not_draft` blocked** (`scope_requires_review=True`, both `Engine` & `Runner` `='escalate'`, `0` leaks).
  - **`16/16` supported drafted** (`scope_requires_review=False`, both `Engine` & `Runner` `='retrieve_draft'`, `0` false blocks — `s1g-neg-sup-01` and `s1g-neg-sup-03` cleanly resolved).

---

## 3. Historical Regression Check (`1,406` Live Rows Across `12` Suites + `bitext sample_031639`) -> **PASS (`0` Diffs vs `3bbbe5f`)**

Every historical suite ran **live** on current `ebf6c72` / `34733574` `Engine` & `PipelineRunner` (except `bitext6690` raw DistilBERT 6,690-row loop, carried from `3bbbe5f` because model/KB/adapter are unchanged; `bitext` leak `sample_031639` executed live):

- **Zero diffs vs `3bbbe5f` across all `1,406` rows** (`historical_1406_nonempty_diffs = {}`).
- **Safety Closures Held (`11/11` Engine, `9/9` Runner -> `0`):** `unseen36` `0`, `fresh34` `0`, `ind36` `0`, `sealed72` `0`, `final24` `active_unans8` `0`, `sa156` `mand63_real` `0`, `oos80` `0`, `pos175` `esc34` `0`, `neg51` `0`, `cand_pos122`/`cand_neg39` `0`, and live `bitext` `sample_031639` (`"how to return an item in stroe"`) = `escalate ['insufficient_evidence']` on both `Engine` and `Runner` (`0` `priv_engine`/`priv_runner` leaks across all suites).
- **Exact Frozen C Utility Floors Held & Reconciled vs Worker B Replay:**
  - `final24`: `ans12_correct = 10/12` (`0` wrong, floor `>=10`; aligns with B's `11` total drafts incl. uninjected `final-case-21`).
  - `sa156`: `sup34_correct_draft = 25/34` (`3` wrong: `sup-refund_policy-05`, `ans-refund_policy-04`, `ans-refund_policy-07`; floor `>=25`; aligns with B's `66/48` on combined `sup+ans84`).
  - `noise420`: `runner.correct_draft = 260/420` (`>=260`, `wrong_draft=23`), `engine.correct_draft = 268` (`wrong_draft=23`); raw ML unchanged (`macro_f1_12 = 0.857307`, `bare = 267/420`).
  - `pos175`: `runner = 34` (`35 -> 34` pre->post Slice 1), `engine = 38` (`39 -> 38`) — `-1` borderline retrieval cost on `cls_dis_wrong_drop_0_841424c7a978` (`<0.55` unboosted) unchanged.
- **Contracts & Parity:** `0` `AI_REASONS` violations, `0` spy mismatches across `1,450` live executions, `0` post-privacy intent mismatches (`max_conf_diff <= 5e-7`), runtime parity & `engine_enforces_experimental_rejection=true` pass.

---

## 4. New Independent Unseen Gate (`unseen_slice1_negation_16`, `c232bd6e...`, Frozen Before Run) -> **BLOCK**

### 4.1 Adversarial Must-Not-Draft (`8/8` PASS — `0` System Leaks)
All `8/8` negative traps (`s1ng-esc-01..08`) escalate cleanly on both natural (`Engine`/`Runner`/`priv_*`, closing raw-ML leak `s1ng-esc-06`) and isolated `Engine` & `Runner` (`8/8` `scope_requires_review=True`):
- Temporal contrast (`s1ng-esc-01`: *"I'm unable to stop by today, but could I drop off ... at a physical store tomorrow?"*), dash-split contrast (`s1ng-esc-02` `--`, `s1ng-esc-05` em-dash), negated wrong object (`s1ng-esc-03`: *"Without a home printer ..., may I bring ... to a local storefront?"*), negative question (`s1ng-esc-04`: *"Shouldn't shoppers ... physical outlet ... exchange?"*), attributed quote + demand (`s1ng-esc-06`: *"FAQ claims ..., yet ... brick-and-mortar store"*), multi-channel history (`s1ng-esc-07`: *"not only ORD-1001 ... all historical orders"*), and negated post office + label portal (`s1ng-esc-08`: *"won't visit a post office counter ... download a prepaid return label"*).

### 4.2 Supported Counterexamples (`5/8` Clean, `1` Retrieval `<0.55`, **`2` Genuine `safety.py` False Positives**)
- **`5/8` PASS (`s1ng-sup-01/02/05/06/08`):** `scope_requires_review=False`, isolated `Engine` & `Runner` = `retrieve_draft` (`s1ng-sup-08` also drafts naturally; `s1ng-sup-06` passes post-pseudonymize with `0912345678` & `ORD-1001`).
- **`1/8` Dense Retrieval `<0.55` Miss Only (`s1ng-sup-03`):** *"I would prefer not to drive to a brick-and-mortar outlet — where in Order Management do I upload defect photos?"* -> `scope_requires_review=False` (with retrieved AND `POL-RET` KB docs; A's negation fix passes!), `manual_fallback` at gold intent solely because `retr.retrieve` returned `[]` (`<0.55` cosine). **Not a Slice 1 rule failure.**
- **Genuine `safety.py` False Positives Blocking Release:**
  1. **`s1ng-sup-04` (End-to-end Natural Engine AND Isolated `Engine`/`Runner` FP Block with `[POL-RET-002, POL-RET-001, POL-RET-003]` retrieved):**
     - Text: *"We will not bring the faulty headset into a local store; instead, please explain the 1-2 business day courier pickup process."*
     - **Root cause (`apps/core_backend/safety.py:313-324`):** `_DECLARATIVE_CHANNEL_NEG_PREFIX` anchors `\s*$` directly after `_NEG_CHANNEL_MOTION_OR_ACTION` (`bring|take|return|drop off`) + `(?:to|into|at|for|with|any|a|an|the|my|your)*`. A short transitive object NP (`the faulty headset`, `my parcel`, `this item`) between `bring` and `into a local store` breaks `$`, triggering `policy_scope_requires_review=True` -> natural `Engine` `escalate ['low_confidence', 'out_of_scope_intent', 'insufficient_evidence']` and isolated `Engine`/`Runner` `escalate ['requires_authority', 'insufficient_evidence']`.
  2. **`s1ng-sup-07` (`policy_scope_requires_review=True` even with `POL-RET` docs supplied; also `docs=[]` in dense retrieval):**
     - Text: *"A friend joked 'just walk into a retail store', though I actually plan to drop the box at a designated partner post office."*
     - **Root cause (`apps/core_backend/safety.py:279-284`):** `_QUOTE_ATTRIBUTION_PREFIX` omits informal speech verbs (`joked|claimed|suggested|replied|advised`), leaving the attributed single-quoted clause unmasked (`scope=True`).

### Targeted Fix Handoff (If Coordinator Requires Strict Clearance Before Gap 2)
1. Allow an optional short object NP (e.g. up to 4 non-clause words `(?:\s+[\w-]+){0,4}`) between transitive return/drop/bring verbs and `(?:to|into|at)` inside `_DECLARATIVE_CHANNEL_NEG_PREFIX` (still clause-anchored `$` and keeping negative-object/contrast traps `s1ng-esc-02/03/05` blocked).
2. Add casual speech attribution verbs (`joked|claimed|suggested|replied|advised`) to `_QUOTE_ATTRIBUTION_PREFIX`.

---

## 5. Remaining Limits Outside Gap 1 (Still OPEN)

- **Gap 2 (Authority / Personal-Account Outage):** Remains OPEN for sequential Worker A handoff once coordinator clears or waives Slice 1.
- **Gap 3 (NER / Slot Extraction Mis-triggers):** Remains OPEN.
- **Residual ML / Retrieval:** Raw ML (`macroF1=0.857307`), non-transposition typos, and `<0.55` dense retrieval phrasing misses (e.g. `s1ng-sup-03`) remain (`cap 2/2`, `STOP` — no training restart).
