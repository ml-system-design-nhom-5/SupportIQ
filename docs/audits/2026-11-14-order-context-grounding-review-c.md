# Worker C Independent Review: Rank 1 `order_context` Grounding & Citation Fix (`013d1c4`)

- **Commit Under Review:** `013d1c4ab49eb83502711eec9bd4145e8e2721fc` (`fix(grounding): unify order_context allowlist and cite actual supplied fields`)
- **Parent Commit:** `4a2298dcb1b9c1ec4a9df85fe1193c57c726ab4a`
- **Reference Fix Note:** [2026-11-14-order-context-grounding-fix-b.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-14-order-context-grounding-fix-b.md)
- **Verdict:** **PASS for Rank 1 serving/runtime closure** — with **1 Important follow-up** in eval tooling (`pipeline/evaluation/flash_lite_acceptance.py`) and **3 Minor hardening/UI items** documented below. Zero privacy, grounding, or customer/auth boundary regressions found in the serving path.

---

## 1. Findings

### Important
1. **Un-updated sibling evaluation parser fails on multi-field `order_context` citations (`pipeline/evaluation/flash_lite_acceptance.py:617-632`):**
   - `013d1c4` updated [collect_final_acceptance_evidence.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/scripts/collect_final_acceptance_evidence.py#L678-L746) (`_verify_order_context_citation`), but `pipeline/evaluation/flash_lite_acceptance.py` (`_inspect_case_citations`, imported by `scripts/run_classifier_vs_serving_live_eval.py`) still reads `cit.get("field")` and `cit.get("value")` directly.
   - **Verified by probe:** passing a multi-field `013d1c4` citation (`fields: ["order_status", "shipping_cost"], values: {...}`) to `_inspect_case_citations` produces `{'source_type': 'order_context', 'field': None, 'value': None, 'field_present_in_executed_context': False, 'value_matches_executed_context': False, 'is_verified': False}` while `AcceptanceEvidenceCollector._verify_order_context_citation` returns `True`.
   - **Impact:** Does not affect production serving or `AcceptanceEvidenceCollector`, but will produce false citation verification failures if `flash_lite_acceptance.py` or `run_classifier_vs_serving_live_eval.py` runs on multi-field order drafts.

### Minor
2. **Mixed `[S1][S2]` paragraph silently drops `[S2]` on direct `Engine.draft` calls with legacy-only fields (`apps/ai_service/engine.py:290-301`):**
   - `prepare_llm_input` emits `S2` (`order_facts`) for `_PROMPT_SAFE_ORDER_FIELDS` (which includes `_LEGACY_SAFE_ORDER_FIELDS` such as `carrier`, plus `tracking: [IDENTIFIER]` when only `tracking_code` is supplied), while `Engine.draft` extracts `supplied_fields` strictly from `ORDER_CONTEXT_ALLOWED_SET`.
   - If `Engine.draft` is called directly in Python (bypassing `SuggestionRequest`) with `{"carrier": "VNPost"}` and the model cites `[S1][S2]` in one paragraph, `S1` populates `citation_ids = ["S1"]`, `elif supplied_fields:` skips `S2`, and `if source_ids and not citation_ids:` does not trigger — returning `draft_ready` with `[S2]` stripped from text instead of `grounding_failed` (verified by probe).
   - **Mitigation already in place on HTTP API:** `SuggestionRequest.check_context` (`apps/ai_service/main.py:38-42`) rejects any key outside `ORDER_CONTEXT_ALLOWED_SET` with `422`.
3. **Cross-check `"field"` vs `"fields"` in `SuggestionWorker` (`apps/backend/tickets/jobs.py:175-189`):**
   - `jobs.py` verifies every name in `fields` is in `payload["order_context"]` and hydrates `values`, and separately hydrates `citation["value"]` if `"field" in citation`. It does not reject a malformed AI payload where both `"fields"` and an unrelated `"field"` exist (unlike `_verify_order_context_citation`, which enforces `cit.get("field") in fields_list`). Low risk because `Engine.draft` only sets `"field"` when `len(supplied_fields) == 1`.
4. **Frontend tooltip formatting & `null` guard (`apps/frontend/src/features/console.tsx:41-48`):**
   - Statically compatible with `apps/frontend/src/types.ts:16` (`fields?: string[]; values?: Record<string, unknown>`) and preserves `0` / `false` via `??`.
   - Minor UX debt (same as pre-existing single-field `citation.value`): `typeof val === 'object'` treats `null` as `'object'` (`"null"`) and renders money objects (`{amount_minor, currency}`) as raw JSON in the `title` tooltip instead of formatting with `money()`. Native `title` tooltips remain hover-only (keyboard/touch users have `aria-label` and `OrderPopover` on click).

---

## 2. Verification Matrix (Scope Checked)

| Area | Files Checked | Result | Evidence |
| --- | --- | --- | --- |
| Unified 6/10 allowlist & zero/null handling | [gemini.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/core_backend/llm/gemini.py#L418-L667), [main.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/ai_service/main.py#L38-L43), [service.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L37-L43) | **PASS** | Single `ORDER_CONTEXT_ALLOWED_FIELDS` / `extract_order_facts` path; `0 VND` / `0.00 USD` & `False` preserved; `None` omitted; `order_id`/`tracking_code` stripped on LLM egress (`include_order_identifiers=False`). |
| Strict nested money/date & PII/injection filtering | [gemini.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/core_backend/llm/gemini.py#L456-L512) | **PASS** | Rejects extra dict keys, `bool`/`float`/negative `amount_minor`, invalid currency codes, non-ISO dates, non-ASCII Unicode digit dates (`٢٠٢٦-10-19`), invalid calendar dates (`2026-02-30`), trailing injection text, and empty strings (verified by probe). |
| `_ISO_DATE` regex & numeric grounding | [safety.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/core_backend/safety.py#L382), [safety.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/core_backend/safety.py#L507-L602) | **PASS** | `(?=\b|T\d{2}:\d{2})` grounds `2026-10-19` from `2026-10-19T07:00:00Z` while still stripping date tokens so fabricated `19 days` or `2026` fail grounding (verified by probe). |
| Source-level `S2` attribution & fail-closed | [engine.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/ai_service/engine.py#L270-L305) | **PASS** | Emits dynamic `"fields"` (plus `"field"` iff `len == 1`), preserves KB `S1..Sn` numbering and unknown-ID / empty-`order_context` `grounding_failed` fail-closed behavior. |
| Worker hydration & acceptance collector | [jobs.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L175-L192), [collect_final_acceptance_evidence.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/scripts/collect_final_acceptance_evidence.py#L678-L746) | **PASS** | Hydrates `values` exclusively from `payload["order_context"]` (never full `Order` records); verifies typed equality and backward compatibility for single-field citations. |
| Auth & customer boundaries | [service.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L20-L58) | **PASS** | Unchanged by `013d1c4`; no customer-view, ticket-ownership, or authority-gate changes. |
| Frontend citation UI | [types.ts](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/types.ts#L16), [console.tsx](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/features/console.tsx#L39-L50) | **Static PASS** | Type/prop shapes align; `tsc`/`vitest` execution **blocked** because `apps/frontend/node_modules/typescript` and `vitest` are broken junctions (`package.json` missing, targeting non-existent `supportiq-final-evidence` worktree). |

---

## 3. Checks Executed (Zero Live LLM Calls, Zero Code Edits)

1. **Focused Grounding, Privacy, Engine & Contract Pytest Suite:**
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_order_context_grounding.py tests/unit/test_ai_grounding.py tests/unit/test_gemini_llm.py tests/unit/test_llm_source_privacy.py tests/unit/test_llm_egress_safety_review.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_completion_grounding.py tests/unit/test_privacy_pii.py tests/unit/test_schema_constraints.py tests/unit/test_system_contracts.py tests/unit/test_input_snapshot_persistence.py tests/application/test_final_acceptance_collector.py tests/application/test_workflow_privacy.py tests/application/test_ai_boundary.py -v`
   - Result: **141 passed, 1 skipped** in `25.35s` (the 1 skipped test is `tests/unit/test_privacy_pii.py::test_live_spacy_free_form_ner_masking_integration`). All 13 new tests in [test_order_context_grounding.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/tests/unit/test_order_context_grounding.py) passed.
2. **Adversarial Python Probes:**
   - Verified `SuggestionRequest` rejects float/bool `amount_minor`, alphanumeric currency, Unicode-digit ISO dates, invalid calendar dates, date trailing injection text, and blank strings; verified `_sentence_has_unsupported_numbers` grounding on ISO timestamps vs fabricated numbers; verified `_inspect_case_citations` mismatch vs `_verify_order_context_citation`; verified direct `Engine.draft` mixed `[S1][S2]` drop on legacy-only `{"carrier": "VNPost"}`.
3. **Root-Cause Verification of B's 2 Pre-Existing Full-Suite Pytest Failures:**
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_fit2_independent_gate.py::test_novel_vs_all_prior_and_internal tests/unit/test_sealed_holdout_20261113.py::test_sealed_holdout_counts_kb_and_zero_overlap -q --tb=short` -> **2 failed in `14.54s`**.
   - `git diff 013d1c4^ 013d1c4` confirms neither test file nor `artifacts/evaluation/fit2_independent_gate_20261113/gate.py` changed in `013d1c4` (last touched in `4cfa8fc` / `16b01eb`):
     - `test_novel_vs_all_prior_and_internal` fails (`36` `exact_overlap` items starting `'g2-sup-01'`) because `gate.historical_corpus()` scans `artifacts/evaluation/` excluding only its own folder and hits later evaluation outputs in `artifacts/evaluation/fit2_v4p1_independent_20261114/predictions_*.jsonl`.
     - `test_sealed_holdout_counts_kb_and_zero_overlap` fails with `JSONDecodeError: Unexpected UTF-8 BOM` because `collect_historical_prompts()` reads `artifacts/evaluation/fit2_independent_gate_20261113/results/verdict_fit2-sibling-boundary-v2.json` (which starts with `\xef\xbb\xbf`) using `encoding="utf-8"`.
   - **Conclusion:** Both failures are pre-existing / evaluation-artifact environmental failures completely unrelated to `013d1c4`.

---

## 4. Not Checked / Residual Risk

- **Not checked:** `apps/frontend` TypeScript compilation (`tsc`) and `vitest` (blocked by broken `node_modules` junctions); PostgreSQL-backed `tests/application/test_backend_safety_closure.py`; live Gemini API calls (disallowed for read-only review).
- **Risk if shipped as-is:** Production serving flow is sound; running `pipeline/evaluation/flash_lite_acceptance.py` or `scripts/run_classifier_vs_serving_live_eval.py` against multi-field `order_context` drafts without updating `_inspect_case_citations` will falsely flag valid `S2` citations as `is_verified: False`.
