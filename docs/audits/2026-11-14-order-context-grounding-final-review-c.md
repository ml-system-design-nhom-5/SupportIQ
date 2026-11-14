# Worker C Final Scoped Re-Review: `order_context` Grounding & Citation Closure (`62949237`)

- **Follow-Up Commit Reviewed:** `62949237fca5ff1da71c142f0ebc6158e4afae1b` (`fix(eval,citations): unify flash_lite citation check, harden contracts, format UI tooltip`)
- **Prior Review / Base Fix:** `cc3230457bf8c09677b99600327040cab6aabf4d` ([2026-11-14-order-context-grounding-review-c.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-14-order-context-grounding-review-c.md)) on top of `013d1c4ab49eb83502711eec9bd4145e8e2721fc`
- **Follow-Up Record:** [2026-11-14-order-context-grounding-followup-b.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-14-order-context-grounding-followup-b.md)
- **Verdict:** **PASS** — Rank 1 `order_context` grounding, citation parity, and offline frontend/backend checks are **closed for offline code/test scope** (no blanket system acceptance claimed).
- **Recommended Next Sequential Non-Model Repair:** **Rank 2 (Reliability & `p95 <= 12s` SLA)** per [2026-11-14-non-model-bottlenecks-c.md](file:///F:/N%C4%83m%203/SD/project/SupportIQ/docs/audits/2026-11-14-non-model-bottlenecks-c.md#L33-L41) — bounded `SuggestionWorker` concurrency, HTTP client pooling, eliminating duplicate `Engine._analyse()` on `/v1/drafts`, and circuit-breaker fast-fail on repeated timeouts/`503`s.

---

## 1. Findings & Verification Summary

- **No Blocking or Important Findings Remain.**
- **Minor Non-Blocking Parity Note:** [flash_lite_acceptance.py:618-634](file:///F:/N%C4%83m%203/SD/project/SupportIQ/pipeline/evaluation/flash_lite_acceptance.py#L618-L634) now rejects unsupported citation `source_type` values with `UNSUPPORTED_CITATION_SOURCE_TYPE`, whereas [collect_final_acceptance_evidence.py:1357-1384](file:///F:/N%C4%83m%203/SD/project/SupportIQ/scripts/collect_final_acceptance_evidence.py#L1357-L1384) still falls through to KB document lookup on any `src_type` other than `"order_context"`/`"order"`. Production `Engine.draft` only emits `"kb_document"` and `"order_context"`.

| Verification Target | Locations Reviewed | Outcome | Observed Evidence |
| --- | --- | --- | --- |
| Shared eval citation checker & fail-closed checks | [collect_final_acceptance_evidence.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/scripts/collect_final_acceptance_evidence.py#L679-L801), [flash_lite_acceptance.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/pipeline/evaluation/flash_lite_acceptance.py#L615-L633) | **PASS** | `_inspect_case_citations` delegates `"order_context"`/`"order"` directly to `_verify_order_context_citation` and fails closed on unknown `source_type`. Rejects non-dict citations/contexts, empty/duplicate/disallowed fields outside `ORDER_CONTEXT_ALLOWED_SET` (e.g., `order_id`, `tracking_code`), `bool`/`int` conflation (`False == 0` / `True == 1`) via `_values_strictly_equal`, and legacy/multi-field mismatches while preserving valid single-field backward compatibility. |
| Import graph, side effects & deployment boundaries | [flash_lite_acceptance.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/pipeline/evaluation/flash_lite_acceptance.py#L57), [collect_final_acceptance_evidence.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/scripts/collect_final_acceptance_evidence.py#L66), [collect_final_acceptance_evidence.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/scripts/collect_final_acceptance_evidence.py#L670) | **PASS** | `flash_lite_acceptance.py` already imported `scripts.collect_final_acceptance_evidence` prior to `62949237`; `collect_final_acceptance_evidence.py` only lazily imports `MockPolicyEncoder` inside `_get_encoder` and imports `ORDER_CONTEXT_ALLOWED_SET` from `apps.core_backend.llm.gemini` (stdlib/`httpx`/`pydantic`). No circular import, no import-time side effects, and `apps/` has zero dependency on `scripts/` or `pipeline/evaluation/`. |
| `Engine.draft` mixed `[S1][S2]` behavior | [engine.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/ai_service/engine.py#L283-L305) | **PASS** | `else:` fails closed with `grounding_failed` (`llm_unavailable`) when `[S2]` (`order_facts`) cannot be cited (e.g., direct call with legacy-only `carrier` or `tracking_code` only) instead of silently dropping `[S2]`, while keeping both `[S1]` and `[S2]` for legitimate 10-field `order_context` drafts (probe-verified). |
| `SuggestionWorker` `field`/`fields` consistency | [jobs.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L175-L192) | **PASS** | Rejects non-string `field` or `field not in fields` and hydrates `values`/`value` strictly from `payload["order_context"]`; no privacy/ID leakage from citations or order context. |
| Frontend `CitationMarker` tooltip & lockfile parity | [console.tsx](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/features/console.tsx#L39-L63), [console.test.tsx](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/src/features/console.test.tsx#L74-L110), [pnpm-lock.yaml](file:///F:/N%C4%83m%203/SD/project/SupportIQ/apps/frontend/pnpm-lock.yaml#L1), [ci.yml](file:///F:/N%C4%83m%203/SD/project/SupportIQ/.github/workflows/ci.yml#L141-L160) | **PASS** | `isMoneyValue` + `val !== undefined && val !== null` renders `money()` (`₫0`, `$19.99`) and omits `null` while preserving `0`/`false`. `package.json` and `pnpm-lock.yaml` (`lockfileVersion: '9.0'`) have zero git diff; local `pnpm 12.14.0` (`node v24.18.0`) vs CI `pnpm` v10 introduces zero uncommitted lockfile or working-tree changes. |

---

## 2. Independent Verification Results (Post-`62949237`, Zero Code Edits)

1. **Focused Grounding, Privacy, Eval & Contract Pytest Suite (15 files):**
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_order_context_grounding.py tests/unit/test_flash_lite_acceptance_runner.py tests/unit/test_ai_grounding.py tests/unit/test_gemini_llm.py tests/unit/test_llm_source_privacy.py tests/unit/test_llm_egress_safety_review.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_completion_grounding.py tests/unit/test_privacy_pii.py tests/unit/test_schema_constraints.py tests/unit/test_system_contracts.py tests/unit/test_input_snapshot_persistence.py tests/application/test_final_acceptance_collector.py tests/application/test_workflow_privacy.py tests/application/test_ai_boundary.py -v`
   - Result: **`152 passed, 1 skipped` in `33.83s`** (`tests/unit/test_privacy_pii.py::test_live_spacy_free_form_ner_masking_integration` skipped; all `15` tests in `test_order_context_grounding.py` and `9` tests in `test_flash_lite_acceptance_runner.py` passed).
2. **Frontend Verification (`apps/frontend`, `pnpm 12.14.0`):**
   - `pnpm --dir apps/frontend run typecheck` (`tsc -b`): **passed** (`exit 0`).
   - `pnpm --dir apps/frontend test` (`vitest run`): **`4` test files passed, `19` tests passed** in `1.96s` (`console.test.tsx`: `9` tests).
   - `pnpm --dir apps/frontend run build` (`tsc -b && vite build`): **passed** (`2177` modules transformed, built in `558ms`).
   - `git status --short apps/frontend/` after runs: empty (zero uncommitted lockfile or build mutations).
3. **Deterministic Adversarial Python Probes (`0` live Gemini calls):**
   - Verified `Engine.draft` preserves legitimate `[S1][S2]` with `placed_at` + `0.00 USD` `shipping_cost`, fails closed on direct `Engine.draft` `[S1][S2]` with `tracking_code` only, `_inspect_case_citations` rejects `source_type: "custom"` even with valid `doc_id`/`version`, and `_verify_order_context_citation` rejects non-dict citations and `amount_minor: False` vs `0`.
4. **Known Full-Suite Failures:** Not re-run (unchanged pre-existing `artifacts/evaluation/` overlap/BOM issues in `test_fit2_independent_gate.py` and `test_sealed_holdout_20261113.py` already established at `cc323045`).

---

## 3. Remaining Coverage Limits

- Not exercised in this offline re-review: live PostgreSQL-backed `tests/application/test_backend_safety_closure.py`, Playwright browser E2E (`pnpm --dir apps/frontend run test:e2e`), live Gemini API requests, and Ubuntu CI `pnpm` v10 environment execution.
