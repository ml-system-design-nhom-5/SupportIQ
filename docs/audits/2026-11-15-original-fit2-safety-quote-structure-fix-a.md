# Original Fit2 Safety Slice 1 Quote & Exclusion Structure Fix (Worker A)

- **Date:** 2026-11-15
- **Base commit (Worker A prior fix):** `c466ffaa87b3b1d160657715e14f3a9323037797`
- **Review target resolved:** `docs/audits/2026-11-15-original-fit2-safety-waiver-review-b.md` (Worker B **BLOCK**, commit `04e63ba32f90a237c03a3c79d3bcf89acab0b63a`)
- **Diff stat (`apps/core_backend/safety.py`):**
  - vs `c466ffaa`: `48 insertions(+), 35 deletions(-)` (`83` changed lines total)
  - vs `12d358d3`: `161 insertions(+), 18 deletions(-)` (`179` changed lines total)

## 1. Structural Root-Cause Fixes in `apps/core_backend/safety.py`

1. **Deleted closed 7-phrase endorsement whitelist (`_QUOTE_ENDORSEMENT_FOLLOWUP`) in favor of structural disavowal + ambiguity guards:**
   - Replaced `_UI_OR_CONTRAST_QUOTE_PREFIX`, `_REPORTED_SPEECH_QUOTE_PREFIX`, and `_QUOTE_ENDORSEMENT_FOLLOWUP` with `_CONTRASTIVE_QUOTE_PREFIX` (L279), `_UI_OR_SPEECH_QUOTE_PREFIX` (L280-285), `_QUOTE_FIRST_PERSON_OR_MODAL` (L286-290), `_QUOTE_REJECTION_SIGNAL` (L291-295), and `_is_ambiguous_or_endorsed_post_quote` (L499-517).
   - Non-contrastive third-party speech and UI-noun quotes containing `_PHYSICAL_STORE_CHANNEL_PATTERN` now require all four conditions before masking:
     1. Non-first-person and non-modal attribution (`_QUOTE_FIRST_PERSON_OR_MODAL` absent before the quote introducer);
     2. An affirmative covered return alternative request outside the quote (`_has_covered_return_alternative_request(outside_quote)`);
     3. Explicit disavowal/mistake/contrast outside the quote (`_QUOTE_REJECTION_SIGNAL`: `instead`, `rather than`, `wrongly`, `erroneous(ly)`, `mistaken(ly)`, `by mistake`, `false(ly)`, `incorrect(ly)`, `joke(d/s)/joking` — bare `but` or `however` alone is no longer sufficient);
     4. Absence of open-choice (`or <alt>`) or anaphoric question endorsement (`?` paired with `that`/`this`/`it`/`doing so`) in `_is_ambiguous_or_endorsed_post_quote(text[m.end():])`.
2. **Removed unguarded UI-label `continue` bypass in `_mask_attributed_quotes` (L520-544):**
   - Only contrastive prefixes (`_CONTRASTIVE_QUOTE_PREFIX`: `instead of` / `rather than`) bypass `_QUOTE_REJECTION_SIGNAL`; UI-noun quotes (`button`, `tab`, `option`, `menu`, `page`, etc.) go through the exact same first-person/modal, disavowal, covered-alternative, and post-quote ambiguity checks as reported speech.
3. **Aligned exclusion conjunctions (`excluding|besides|save|barring`):**
   - Added `excluding|besides|save|barring` alongside `except|without|unless` in both `_ALTERNATIVE_NEG_PREFIX` (L125-128) and `_NEG_CLAUSE_BOUNDARY_WORDS` (L328-338) so `"I won't return this excluding/besides/save/barring at a physical store, can I use a courier?"` fails closed pre-LLM.
4. **Eliminated duplicate negation stem between `_ALT_CLAUSE_REJECTION` and `_DECLARATIVE_CHANNEL_NEG_PREFIX`:**
   - Extracted shared `_DECLARATIVE_NEGATION_STEM` (L375-382) so both patterns stay synchronized on `am not`, `are not`, `'m not`, `'re not`, `aren't`, `unable`, and modal/contraction forms (`"I am not using the app, and without visiting a physical store..."` and `"We are unable to use courier pickup..."` both fail closed).

## 2. TDD RED -> GREEN & End-to-End Pre-LLM Verification

- **RED baseline (`c466ffaa` before `safety.py` edits):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -k test_gap1e -v --tb=line`
  - Result: **`14 failed, 6 passed, 110 deselected in 10.13s`** (all 9 exact Worker B FAIL-OPEN leaks failed open + 5 metamorphic structural traps).
- **GREEN slice suite (after `safety.py` edits + fixing `test_gap1d` parametrize placement & switching `test_gap1e` allowed case 4 from first-person `"I see the option..."` to third-person `"An old page shows the option..."`):**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q`
  - Result: **`148 passed in 26.59s`**
  - End-to-end pre-LLM proof (`test_gap1e_b_nine_leaks_and_structural_traps_block_pre_llm_with_real_retrieval`): Uses real `RetrievalAdapter` (`approved_kb.v2.json` + release allowlist when `status == "success"`, `StaticScopeRetriever` otherwise), runs both `Engine.analyse` and `PipelineRunner.run` with `_PreLLMSpy`, and asserts `recommendation == "escalate"`, `"insufficient_evidence"` in `reason_codes`, and `calls == []` (provider LLM never invoked).
  - Positive controls (`test_gap1e_valid_third_party_quote_rejections_and_contrastive_ui_remain_allowed`): Third-party mistaken seller/support quotes paired with explicit rejection + approved alternative and `instead of 'return in store'` UI contrasts still allow drafting (`4/4` passed).

## 3. Focused Regression, Frozen Gates & ReDoS Timing

- **Focused core safety + retrieval regression suite:**
  - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py tests/unit/test_supported_unsupported_boundary_b.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_mandatory_routing_b.py tests/unit/test_semantic_retrieval.py tests/unit/test_completion_retrieval.py tests/unit/test_system_components.py tests/application/ tests/integration/test_routing_retrieval.py tests/unit/test_guard_corrections_checks.py tests/unit/test_completion_knowledge.py -q`
  - Result: **`448 passed, 1 xfailed in 105.70s`**
- **Frozen C scope & negation gates (`policy_scope_requires_review`):**
  - `scope_c`: **`27/27`** (`fails=[]`)
  - `negation_c`: **`16/16`** (`fails=[]`)
  - Combined: **`43/43`**
- **ReDoS stress check:** `5.49 ms` total across 3 adversarial 400+ token strings.

## 4. Invariant SHA-256 Verification (Unchanged)

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

## 5. Honest Scope & Remaining Limits

- **Not universal natural-language understanding:** The deterministic pre-LLM guard remains a finite lexical/structural analyzer tailored to Slice 1 unsupported channels (`physical_store`, `prepaid_return_label`, `full_order_history`). Novel phrasing outside these patterns may trigger conservative fail-closed escalation (e.g., first-person UI sightings such as `"I see the option 'return at a physical store'..."` conservatively escalate rather than risk masking a first-person intent).
- **Out of scope / still pending in broader project:** `s1ng-sup-03` retrieval recall `< 0.55` in `apps/core_backend/retrieval/adapter.py` (untouched per task scope), Safety Slice 1 Gaps 2/3, and independent Worker B re-review on this commit.
