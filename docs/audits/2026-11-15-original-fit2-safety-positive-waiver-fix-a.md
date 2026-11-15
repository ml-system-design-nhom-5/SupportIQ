# Original Fit2 Safety Slice 1 Inverted Positive-Proof Quote Waiver Fix (Worker A)

- **Date:** 2026-11-15
- **Reviewed Blockers Resolved:** Worker B `BLOCK` commit `c1c2a76611f704b1358a9428c4007cadf2435da4` ([`docs/audits/2026-11-15-original-fit2-safety-quote-structure-review-b.md`](2026-11-15-original-fit2-safety-quote-structure-review-b.md)) on top of `717ac0382fbaf9d4eebc059724346c6fa503484a`
- **Diff stat (`apps/core_backend/safety.py`):**
  - vs `717ac038`: `154 insertions(+), 47 deletions(-)` (`201` lines changed)
  - vs `12d358d3`: `270 insertions(+), 20 deletions(-)` (`290` lines changed)

## 1. Helper Removals & Positive-Proof Algorithm

1. **Removed absence-based & global helpers:**
   - **Deleted** `_is_ambiguous_or_endorsed_post_quote` (prior absence-based `?` and closed anaphora heuristic).
   - **Deleted** `_QUOTE_REJECTION_SIGNAL` and global `outside_quote = f"{text[:m.start()]} {text[m.end():]}"` scanning.
   - Casual reporting verbs (`joked`, `said`, `wrote`, `claims`, etc.) and UI labels (`option`, `button`, `tab`) no longer authorize masking by themselves.
2. **Inverted `_mask_attributed_quotes` ([`apps/core_backend/safety.py:629-651`](../../apps/core_backend/safety.py#L629-L651)):**
   - Default for any quote containing `_PHYSICAL_STORE_CHANNEL_PATTERN` is **RETAIN** for downstream safety escalation.
   - Quotes are first partitioned into sorted non-overlapping spans via `_collect_non_overlapping_quotes` (L590-602), and `_quote_bounds_and_prefix` (L605-626) isolates each quote `m`'s `(local_prefix, local_post)` window from preceding/subsequent quotes.
   - A physical-store quote is masked **only** if all positive checks hold:
     1. **Non-first-person/non-modal local attribution:** Either `_CONTRASTIVE_QUOTE_PREFIX` (`instead of` / `rather than`) directly precedes the quote, or `_UI_OR_SPEECH_QUOTE_PREFIX` matches with zero `_QUOTE_FIRST_PERSON_OR_MODAL` hits in `pre_attr`.
     2. **Locally scoped explicit disavowal (`has_prefix_disavowal` or `_POST_QUOTE_DISAVOWAL_PREFIX`):** Explicit falsity (`_LOCAL_QUOTE_FALSITY`: `wrongly|erroneously|mistakenly|by mistake|falsely|incorrectly`) in `local_prefix`, OR `_CONTRASTIVE_QUOTE_PREFIX`, OR immediate leading post-quote disavowal (`_POST_QUOTE_DISAVOWAL_PREFIX`, L295-304). Unrelated rejections in earlier clauses or surrounding quotes cannot grant a waiver.
     3. **Exclusive unnegated covered return alternative (`_post_quote_is_exclusively_covered`, L569-587):** After stripping the single leading disavowal prefix (or optional leading `and|but` when prefix-disavowed), the remaining text MUST be non-empty, contain zero unresolved anaphora/store-action references (`_UNRESOLVED_QUOTE_REFERENCE`, L311-319: `that`, `there`, `doing so`, `also`, `too`, `alongside`, `visiting`, `going`, `walking`, bare `this`, etc.), and **every** clause split by `_POST_QUOTE_CLAUSE_SPLIT` (L320-323) MUST affirmatively satisfy `_has_covered_return_alternative_request(c, require_return_action=True)`.
3. **Shared clause-negation classifier & action requirement (`_is_covered_alt_clause_negated`, L547-566):**
   - Extended `_ALT_CLAUSE_REJECTION` (L411-417) beyond first-person stems (`_DECLARATIVE_NEGATION_STEM`) to gerund/3rd-person negative prefixes (`instead of waiting for / using`, `rather than ...`, `no available/free ...`, `not/without/never waiting for / using / ...`).
   - Added `_clause_after` (L533-544) + `_ALT_CLAUSE_POST_NEG` (L418-427) so trailing predicates (`courier isn't available`, `courier pickup is unavailable`, `doesn't work`, `offline/closed/down`) disqualify the alternative in the same clause.
   - Added `_COVERED_ALT_RETURN_ACTION` (L305-310) when validating post-quote alternatives (`require_return_action=True`) so bare topic mentions (`"let's check via the app"`) do not satisfy return-action exclusivity.

## 2. TDD RED -> GREEN & Property Verification

- **TDD RED baseline (`717ac038` before `safety.py` edits):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -k test_gap1f -v --tb=line`
  - Result: **`21 failed, 12 passed, 148 deselected in 14.37s`** (all `8/8` Worker B FAIL-OPEN leaks failed open, plus declarative, unrelated-clause, negated-alternative, and multi-quote traps).
- **TDD GREEN (`tests/unit/test_safety_slice1_gap1_a.py`):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q`
  - Result: **`181 passed in 35.07s`**
  - Verified both `Engine.analyse` and `PipelineRunner.run` escalate pre-LLM with `_PreLLMSpy.calls == []` across:
    - All `8/8` Worker B leaks (`test_gap1f_worker_b_eight_leaks_and_structural_traps_block_pre_llm`)
    - Prior `9/9` + `6+1` repros (`test_gap1d`, `test_gap1e`)
    - Property/metamorphic invariants (`test_gap1f_property_declarative_without_question_mark_never_unlocks`, `test_gap1f_property_unrelated_rejection_elsewhere_never_authorizes_quote`, `test_gap1f_property_negating_covered_alternative_never_unlocks`, `test_gap1f_property_multiple_quotes_evaluated_independently`)
    - Positive controls (`test_gap1f_positive_local_rejection_with_exclusive_courier_and_safe_ui_allowed` + all `test_gap1b`/`1c`/`1e` valid controls)
- **Focused core safety & retrieval suite:**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py tests/unit/test_supported_unsupported_boundary_b.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_mandatory_routing_b.py tests/unit/test_semantic_retrieval.py tests/unit/test_completion_retrieval.py tests/unit/test_system_components.py tests/application/ tests/integration/test_routing_retrieval.py tests/unit/test_guard_corrections_checks.py tests/unit/test_completion_knowledge.py -q`
  - Result: **`481 passed, 1 xfailed in 107.93s`**
- **Frozen C gates (`policy_scope_requires_review` against real KB `evidence` & `eligible_versions`):**
  - `scope_c`: **`27/27`** (`fails=[]`)
  - `negation_c`: **`16/16`** (`fails=[]`)
  - Combined: **`43/43`** (no regressions on the bounded 43-case contract)
- **ReDoS stress check:** **`15.36 ms`** across 4 adversarial multi-hundred-token strings.

## 3. Invariant SHA-256 Digests (Unchanged)

| Artifact | SHA-256 |
|---|---|
| `apps/core_backend/retrieval/adapter.py` | `3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f` |
| `data/knowledge/approved_kb.v2.json` | `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec` |
| `apps/ai_service/kb-release.json` | `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804` |
| `apps/core_backend/config/policies/intent_policy.v2.json` | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors` | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` |
| `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json` | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` |
| `artifacts/models/trained/distilbert-supportiq/model.safetensors` | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |
| `.local/training-cap-20261114.json` | `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` |
| `.local/ai.env` | `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87` |
| `artifacts/evaluation/original_fit2_safety_slice1_c_20261115/unseen_slice1_scope_gate_cases.jsonl` | `20bb9315c8d4be4670fd2e8157053eea29ee43eec6a7510029ccbb49a66b84d8` |
| `artifacts/evaluation/original_fit2_safety_slice1_negation_c_20261115/unseen_slice1_negation_gate_cases.jsonl` | `c232bd6e21db2c497bc566ddc9e668f5efa3ca11e638fa3e6f6ba67fcc825a3a` |

## 4. Conservative Coverage Cost & Remaining Limits

- **Conservative fail-closed trade-off:** Any quoted physical-store mention followed by a multi-clause narrative containing a non-return-action clause (e.g., `"thanks for explaining packing"` paired with `"and book a courier"`), casual `"joked"` without explicit contrast/disavowal (`instead` / `though I actually` / `by mistake`), or unresolved pronouns (`that`, `there`, unqualified `this`) conservatively retains the quote and escalates rather than risking a fail-open waiver.
- **Not claimed as universal NLU:** The deterministic pre-LLM scope guard enforces strict positive local evidence inside Slice 1 channels rather than unrestricted semantic parsing.
- **Pending out-of-scope items:** Independent Worker B re-review and Worker C bounded closure on this commit, `s1ng-sup-03` dense retrieval `<0.55` in untouched `apps/core_backend/retrieval/adapter.py`, and sequential Safety Slice 1 Gap 2 (authority) / Gap 3 (NER).
