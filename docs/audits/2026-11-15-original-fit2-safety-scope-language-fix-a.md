# Original fit2 Safety Scope Language Fix Audit (Worker A)

- **Date:** 2026-11-15
- **Branch:** `minh`
- **Base HEAD:** `1325a240efdf50deb25e1105a8108e4dc1cf5ad0` (Worker C Slice 1 final review commit on top of Worker B PASS `ebf6c72dfb42042eb81ed68ed3cb1f55b76b41a4` / Worker A `34733574e738a7dc932efbf0b8870a68ac3dd4c4`)
- **Upstream Blocker Addressed:** `docs/audits/2026-11-15-original-fit2-safety-slice1-final-review-c.md` (**BLOCK** strictly on the 2 genuine `safety.py` false positives `s1ng-sup-04` and `s1ng-sup-07` in `unseen_slice1_negation_16`)
- **Modified Files:**
  - `apps/core_backend/safety.py` (`+31/-3` lines)
  - `tests/unit/test_safety_slice1_gap1_a.py` (`+108` lines)
  - `docs/audits/2026-11-15-original-fit2-safety-scope-language-fix-a.md`
- **Untouched Adapter & Thresholds:** `apps/core_backend/retrieval/adapter.py` (`sha256: 3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`) is unchanged. Retrieval similarity threshold (`0.55`) was **not** lowered (`s1ng-sup-03` was a dense-retrieval miss, not a Slice 1 scope false positive).

---

## 1. Root Cause & Minimal Patch (`apps/core_backend/safety.py`)

Worker C's frozen 16-case gate (`c232bd6e...`) surfaced two genuine `safety.py` false positives while holding `8/8` must-not-draft escalations (`0` leaks) and confirming `1,406` historical rows (`0` diffs):

1. **Transitive negated action with intervening object NP (`s1ng-sup-04`):**
   - Query: *"We will not bring the faulty headset into a local store; instead, please explain the 1-2 business day courier pickup process."*
   - Previously, `_DECLARATIVE_CHANNEL_NEG_PREFIX` ended `\s*$` right after `_NEG_CHANNEL_MOTION_OR_ACTION` + trailing determiners/prepositions, so an intervening object NP (`the faulty headset`) between `bring` and `into a local store` prevented a match.
   - **Fix:** Added `_NEG_CHANNEL_TRANSITIVE_ACTION` (`return`, `bring`, `take`, `drop`, `hand`, `send`, `ship`, `carry`, `deliver`, `exchange`, `swap` plus optional particle `back`/`off`/`in`), `_NEG_OBJECT_NP_WORD` (alphanumeric/apostrophe/internal-hyphen tokens excluding standalone `-`/`--`, clause connectors, modals, auxiliaries, subject pronouns, and finite/action verbs), and `_NEG_CHANNEL_ACTION_CLAUSE` allowing `{1,5}` NP tokens (+ optional trailing `back|off|in`) **only** on transitive return/transfer verbs (not after `without`, `print`, `download`, `generate`, `use`, or unrelated verbs). Also added `we aren't` alongside existing `we're not` / `we are not`. Negated unrelated clauses and compound/dash-split contrasts remain fail-closed (`escalate`).

2. **Casual speech reporting verb in `_QUOTE_ATTRIBUTION_PREFIX` (`s1ng-sup-07`):**
   - Query: *"A friend joked 'just walk into a retail store', though I actually plan to drop the box at a designated partner post office."*
   - Previously, `_QUOTE_ATTRIBUTION_PREFIX` omitted casual speech reporting verbs (`joked`, `claimed`, `suggested`, `replied`, `advised`) and optional comma before the quote.
   - **Fix:** Extended the existing `_QUOTE_ATTRIBUTION_PREFIX` regex with `jok(?:e[ds]?|ing)|claim(?:s|ed)?|suggest(?:s|ed)?|repl(?:y|ies|ied)|advis(?:e[ds]?|ing)` and optional `,` (`[:,\-]?`) immediately before the quote boundary. `_mask_attributed_quotes` continues to blank **only** the attributed quoted span (`m.start():m.end()`), so any unquoted or subsequent positive physical-store request (e.g., *"I joked before, but now I want to go to a physical store."*) still blocks cleanly.

No literal query/ID allowlists, no new NLP dependencies, and no retrieval/threshold edits were introduced.

---

## 2. Verification Results

### TDD Cycle (`tests/unit/test_safety_slice1_gap1_a.py`)
Added `25` regression tests covering transitive negated object NPs, casual quoted speech attribution, nested/contrast/positive unsupported request controls, unrelated-negation traps, and multichannel history:
- `test_gap1c_transitive_negated_action_and_quoted_speech_remain_allowed` (`12` cases)
- `test_gap1c_quote_positive_controls_and_unrelated_negation_still_escalate` (`12` cases)
- `test_gap1c_multichannel_negated_single_order_plus_full_history_escalates` (`1` case)

| Stage | Command | Result |
| :--- | :--- | :--- |
| RED (before `safety.py` edit) | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -v --tb=line` | `11 failed, 98 passed in 12.48s` (`10` genuine Bug 1/2 failures + `1` helper intent label alignment to `track_order`) |
| GREEN (after `safety.py` edit) | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q` | `109 passed in 16.82s` |

### Focused Core Regression Suite
Command:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py tests/unit/test_supported_unsupported_boundary_b.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_mandatory_routing_b.py tests/unit/test_semantic_retrieval.py tests/unit/test_completion_retrieval.py tests/unit/test_system_components.py tests/application/ tests/integration/test_routing_retrieval.py tests/unit/test_guard_corrections_checks.py tests/unit/test_completion_knowledge.py -q
```
Observed result:
- `409 passed, 1 xfailed in 98.03s (0:01:38)`

---

## 3. Invariant Verification (SHA-256)

| Artifact | SHA-256 | Status |
| :--- | :--- | :--- |
| `apps/core_backend/retrieval/adapter.py` | `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f` | Unchanged |
| `data/knowledge/approved_kb.v2.json` | `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec` | Unchanged |
| `apps/ai_service/kb-release.json` | `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804` | Unchanged |
| `apps/core_backend/config/policies/intent_policy.v2.json` | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` | Unchanged |
| `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors` | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` | Unchanged |
| `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json` | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` | Unchanged |
| `artifacts/models/trained/distilbert-supportiq/model.safetensors` | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` | Unchanged |
| `.local/training-cap-20261114.json` | `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` | Unchanged |
| `.local/ai.env` | `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87` | Unchanged |
| `artifacts/evaluation/original_fit2_safety_slice1_negation_c_20261115/unseen_slice1_negation_gate_cases.jsonl` | `c232bd6e21db2c497bc566ddc9e668f5efa3ca11e638fa3e6f6ba67fcc825a3a` | Unchanged |

---

## 4. Remaining Limits & Consolidated Downstream Handoff

- **Regression Contract Status:** `s1ng-sup-04`, `s1ng-sup-07`, and representative paraphrases are now fixed **regression coverage** in `tests/unit/test_safety_slice1_gap1_a.py` (consolidated alongside the `27` + `16` + prior cases), not unseen validation evidence; frozen C evaluation files were not altered.
- **Explicit Coverage Costs / Limits (No Universal-NL Claim):**
  - `_DECLARATIVE_CHANNEL_NEG_PREFIX` handles syntax over `1-5` non-boundary object tokens on transitive return verbs; a standalone negated wrong object inside a single bare clause with no follow-up request clause (e.g., *"I won't bring a receipt to a local store"* with no punctuation or positive clause) cannot be distinguished from a returned item without world-noun semantics, whereas separated or followed requests (*"Without a printer, may I..."*, *"I cannot print a label to bring this headset into a local store"*) fail closed (`escalate`).
  - `_QUOTE_ATTRIBUTION_PREFIX` intentionally remains a small fail-closed list; novel reporting verbs outside the prefix remain escalated rather than risking false negatives.
  - Dense retrieval `<0.55` misses (`s1ng-sup-03`), Gap 2 (authority/personal-account outage), Gap 3 (NER/slot extraction), and raw ML `macroF1` remain out of scope for this patch (`retrieval threshold unchanged`).
- **Next:** Worker B review on this frozen fix, followed by **one** bounded Worker C closure check over the frozen `43` cases (`27 + 16`) and historical floors (moving focus to **Gap 2** after verified closure).
