# Original fit2 Safety Negation Fix Audit (Worker A)

- **Date:** 2026-11-15
- **Branch:** `minh`
- **Base HEAD:** `3bbbe5ff60f9962b0acbe0808f1d1ab95c2940c7` (Worker C Slice 1 evaluation commit on top of Worker B PASS `faac0e72027627b7864a1f7d707ee79af1f8c442` and frozen Slice 1 `12d358d3b301680a5d1ab910d684a1102bcd509c`)
- **Upstream Blocker Addressed:** `docs/audits/2026-11-15-original-fit2-safety-slice1-evaluation-c.md` (**BLOCK** on `s1g-neg-sup-01` and `s1g-neg-sup-03`)
- **Modified Files:**
  - `apps/core_backend/safety.py`
  - `tests/unit/test_safety_slice1_gap1_a.py`
  - `docs/audits/2026-11-15-original-fit2-safety-negation-fix-a.md`
- **Untouched Adapter:** `apps/core_backend/retrieval/adapter.py` (`sha256: 3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f`)

---

## 1. Root Cause & Fix Summary

Worker C's 27-case Slice 1 scope gate reported two false escalations on supported courier-return queries that declined an unsupported physical retail branch channel:
- `s1g-neg-sup-01`: *"I do not want to go to a physical store; can I schedule courier pickup for my return instead?"*
- `s1g-neg-sup-03`: *"I cannot travel to a retail store branch — how does Tiki's free courier pickup work for defective items?"*

In `apps/core_backend/safety.py`, `_DECLARATIVE_CHANNEL_NEG_PREFIX` did not cover:
1. Modal/auxiliary negations such as `cannot`, `can not`, `can't`, `could not`, `couldn't`, `will not`, `won't`, `would not`, `wouldn't`, `do not`, `don't`, `did not`, `didn't`, `(I'm|we're|I am|we are) (not|unable)`, `(prefer not to|rather not)`, `no need (for|to)`, and `without`.
2. Intervening motion and channel-action verbs before the unsupported channel noun phrase (for example `want to go to a physical store` or `cannot travel to a retail store branch`).

### Implemented Changes (`apps/core_backend/safety.py`)
1. Added `_NEG_CHANNEL_MOTION_OR_ACTION` covering inflected motion/channel-action verbs (`go`, `travel`, `walk`, `head`, `drive`, `commute`, `come`, `visit`, `stop by`, `drop in`, `return`, `drop off`, `bring`, `take`, `print`, `download`, `generate`, `use`) and expanded `_DECLARATIVE_CHANNEL_NEG_PREFIX` using an anchored end-of-prefix match (`\s*$`) with optional attitude verb, optional `to`/`for`, optional `_NEG_CHANNEL_MOTION_OR_ACTION`, and optional trailing determiners/prepositions. Keeping the prefix tightly anchored preserves escalation on compound contradictions and negated wrong objects (e.g., *"I cannot visit today and want to return in store tomorrow"*, *"I cannot wait for a courier so I want to return in store"*, *"Why can't I..."*).
2. Updated `_is_negated_channel_alternative` so `_INSTEAD_OF_PREFIX` also suppresses bypass when a dash-split clause follows (`re.search(r"\s-\s|--", tail)`), keeping inputs like *"Instead of courier — physical store return please."* escalated.

No literal query/ID allowlists and no new NLP dependencies were added. `apps/core_backend/retrieval/adapter.py` was not modified.

---

## 2. Verification Results

### TDD Cycle (`tests/unit/test_safety_slice1_gap1_a.py`)
Added 17 new test cases across two parameterized tests:
- `test_gap1b_negated_modal_and_motion_declining_physical_channel_remains_allowed` (8 cases)
- `test_gap1b_compound_contradictions_and_negated_wrong_object_still_escalate` (9 cases)

| Stage | Command | Result |
| :--- | :--- | :--- |
| RED (before `safety.py` edit) | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -v --tb=line` | `7 failed, 77 passed in 11.94s` |
| GREEN (after `safety.py` edit) | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q` | `84 passed in 13.75s` |

### Focused Core Regression Suite
Command:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py tests/unit/test_supported_unsupported_boundary_b.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_mandatory_routing_b.py tests/unit/test_semantic_retrieval.py tests/unit/test_completion_retrieval.py tests/unit/test_system_components.py tests/application/ tests/integration/test_routing_retrieval.py tests/unit/test_guard_corrections_checks.py tests/unit/test_completion_knowledge.py -q
```
Observed result:
- `384 passed, 1 xfailed in 96.42s (0:01:36)`

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

---

## 4. Scope Notes & Downstream Handoff

- `s1g-neg-sup-01`, `s1g-neg-sup-03`, and their paraphrases in `tests/unit/test_safety_slice1_gap1_a.py` now constitute **regression coverage**, not an unseen evaluation pass.
- Worker C's frozen evaluation artifact (`20bb9315...`) was not modified or overwritten.
- Worker B code review and Worker C bounded re-evaluation of the frozen 27-case gate (plus any fresh unseen checks C chooses) remain pending after this commit.
- Remaining pre-existing gaps documented in Worker C's evaluation (Gap 2 and Gap 3) remain open outside this targeted fix.
