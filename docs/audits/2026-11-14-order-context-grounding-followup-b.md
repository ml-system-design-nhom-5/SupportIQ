# Worker B Follow-Up Record: Eval Citation Parity, Optional Hardening & Frontend Repair

Follow-up to C's independent review ([2026-11-14-order-context-grounding-review-c.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-14-order-context-grounding-review-c.md) at `cc3230457bf8c09677b99600327040cab6aabf4d`) on top of `013d1c4ab49eb83502711eec9bd4145e8e2721fc`.

## Changes & Finding Dispositions

1. **Important Finding 1 — Shared eval citation verification (`pipeline/evaluation/flash_lite_acceptance.py`, `scripts/collect_final_acceptance_evidence.py`)**:
   - Updated `_inspect_case_citations` (`pipeline/evaluation/flash_lite_acceptance.py`) to delegate `order_context` / `order` citations directly to `AcceptanceEvidenceCollector._verify_order_context_citation(cit, executed_order_context)` instead of duplicating `cit.get("field")` / `cit.get("value")` logic, and to fail closed (`UNSUPPORTED_CITATION_SOURCE_TYPE`) on arbitrary unknown `source_type` values even when a real `document_id` is supplied.
   - Tightened `AcceptanceEvidenceCollector._verify_order_context_citation` (`scripts/collect_final_acceptance_evidence.py`): rejects non-dict citations/contexts, duplicate or disallowed/arbitrary IDs/fields outside `ORDER_CONTEXT_ALLOWED_SET`, and Python `bool`/`int` conflation (`False == 0` / `True == 1`) via `_values_strictly_equal`, while preserving legacy single-field compatibility.
2. **Optional Finding 2 (Implemented) — Direct `Engine.draft` mixed `[S1][S2]` fail-closed (`apps/ai_service/engine.py`)**:
   - Added fail-closed `else` (`grounding_failed` / `llm_unavailable`) when an `order_facts` source is cited alongside `S1` while `supplied_fields` is empty (e.g., direct Python call with legacy-only `{"carrier": "VNPost"}`), preventing silent `[S2]` stripping.
3. **Optional Finding 3 (Implemented) — `field` vs `fields` consistency (`apps/backend/tickets/jobs.py`)**:
   - Rejected malformed `order_context` citations where `"field"` is non-string or conflicts with `"fields"` (`field_name not in fields`), matching `AcceptanceEvidenceCollector._verify_order_context_citation`.
4. **Optional Finding 4 (Implemented) — Frontend tooltip formatting & `null` guard (`apps/frontend/src/features/console.tsx`, `apps/frontend/src/features/console.test.tsx`)**:
   - Filtered `val !== null` alongside `undefined` and formatted valid `Money` objects (`{amount_minor, currency}`) with `money()` instead of raw JSON in `CitationMarker`'s `title` tooltip (`export function CitationMarker` for unit testing). Pre-existing hover-only native `title` attribute retained (no UI restyle; `aria-label` and `OrderPopover` remain on click).
5. **Frontend Dependency Repair (`apps/frontend`, `node v24.18.0`, `pnpm v12.14.0`)**:
   - `apps/frontend/node_modules` top-level junctions previously targeted non-existent `C:\Users\PC\orca\workspaces\SupportIQ\supportiq-final-evidence`.
   - Repaired with existing lockfile via `pnpm --dir apps/frontend install --frozen-lockfile` (`F:\.pnpm-store\v11`, no lockfile/dependency changes).

## Modified Files & SHA-256 Hashes
| File | SHA-256 |
| --- | --- |
| `scripts/collect_final_acceptance_evidence.py` | `56b4fe484701ab5ad96de07ce13876ff7fd6d9e5017401dbb82a87e73bf53348` |
| `pipeline/evaluation/flash_lite_acceptance.py` | `664304480d4904e0e22acad19a8e51e9c45b5f3f348bec796507a7ff5ee54afa` |
| `apps/ai_service/engine.py` | `b04992ca19d26915ce346c1f392a14a5ba33586df5af457d969c1c1d9ae4348` |
| `apps/backend/tickets/jobs.py` | `c7cf0c99e3364d0db3afed78106d2f8915b9a81fbaed1f60feab4896d909dcd5` |
| `apps/frontend/src/features/console.tsx` | `846bc9ca3447a224b5c06a44b41afed35bd9dbc10dad2feae018cf12c9608383` |
| `apps/frontend/src/features/console.test.tsx` | `f3afea9d879706d75b382485485be4c846bdd8fbaec18ae0d2cc16539917d643` |
| `tests/unit/test_order_context_grounding.py` | `63a45b2b5aeb7a5c9f0ddddad4f98e412e5018f0792c867dadca2e9b21d2e2d0` |

## Verification Results (Post-Final-Edit)
- **Focused Grounding, Privacy, Eval & Contract Pytest Suite**:
  `.venv\Scripts\python -m pytest tests/unit/test_order_context_grounding.py tests/unit/test_flash_lite_acceptance_runner.py tests/unit/test_ai_grounding.py tests/unit/test_gemini_llm.py tests/unit/test_llm_source_privacy.py tests/unit/test_llm_egress_safety_review.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_completion_grounding.py tests/unit/test_privacy_pii.py tests/unit/test_schema_constraints.py tests/unit/test_system_contracts.py tests/unit/test_input_snapshot_persistence.py tests/application/test_final_acceptance_collector.py tests/application/test_workflow_privacy.py tests/application/test_ai_boundary.py -v`
  -> **152 passed, 1 skipped** in `31.64s` (`tests/unit/test_privacy_pii.py::test_live_spacy_free_form_ner_masking_integration` skipped; all 15 tests in `tests/unit/test_order_context_grounding.py` and 9 tests in `tests/unit/test_flash_lite_acceptance_runner.py` passed).
- **Frontend (`apps/frontend`)**:
  - `pnpm --dir apps/frontend run typecheck` (`tsc -b`): **passed** (exit code `0`).
  - `pnpm --dir apps/frontend test` (`vitest run`): **4 test files passed, 19 passed** in `1.67s` (including new `CitationMarker` test in `src/features/console.test.tsx`).
  - `pnpm --dir apps/frontend run build` (`tsc -b && vite build`): **passed** (`2177 modules transformed`, built in `423ms`).

## Residual Blockers / Not Run
- No live Gemini API calls, model training, live PostgreSQL-backed `test_backend_safety_closure.py`, Playwright e2e (`test:e2e`), or full-suite rerun of the 2 pre-existing evaluation-artifact overlap/BOM tests documented by C were performed.
- Worker A's unstaged edits, `.gitkeep` deletion, evaluation artifacts, and `*.pptx` files remain untouched.
