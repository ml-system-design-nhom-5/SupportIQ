# Test Suite Cleanup Implementation Plan

> **For agentic workers:** Execute task-by-task in assigned Orca workspaces using Ponytail ultra. Use the existing orchestration workflow; no helper agents. This document is a plan, not authorization to remove unreviewed tests.

**Goal:** Make tests easier to understand, run and maintain while preserving assertions for required behavior and past regressions.

**Architecture:** Keep pytest, Vitest and Playwright. Organize tests by behavior and resource needs, reuse small existing factories, and consolidate only after comparing assertions and failure modes. Make each cleanup independently reviewable.

**Tech Stack:** Python/pytest, PostgreSQL/SQLite, TypeScript/Vitest, Playwright; existing dependencies only.

**Spec:** User request to plan cleanup of the whole test suite, extending [the codebase cleanup plan](2026-11-13-codebase-cleanup.md). Planning only in this turn; no test deletion or product changes.

## Evidence and approach

Inventory at `a9a49b4`, 2026-11-13:

- 88 tracked Python test modules: 67 unit, 9 integration, 11 application, 1 e2e. These are file counts, not executed test counts.
- Frontend: 4 Vitest files and `apps/frontend/e2e/application.spec.ts`, configured for four viewport projects.
- An AST scan found no identical test function bodies and no repeated pytest fixture names in the scanned test modules and root conftest. This does not rule out semantic duplication or repeated non-fixture setup.
- Large review targets: `test_accounting_guardrails_b.py` (1,868 lines), `test_model_comparison.py` (1,053), `test_evaluation_ml.py` (884), `test_training.py` (859), `test_model_runtime_parity_b.py` (760), `test_retrieval_grounding_b2.py` (751).
- Historical names such as `test_review_eight_fixes.py`, `test_system_review_probes.py`, `test_system_review_probes_v2.py` mix responsibilities. Their age/name is not proof of redundancy.
- `tests/conftest.py` already provides offline network/model guards, resource markers and cleanup locks. `tests/fixtures/factories.py` and `tests/annotation_fixtures.py` already provide reusable setup.
- Application tests may require native PostgreSQL and private local configuration, while the README's default profile description emphasizes CPU/loopback/SQLite. Documentation must distinguish these prerequisites and skips accurately.
- Latest historical full root verification: 1,020 passed, 2 skipped, 3 deselected before the latest cleanup. Latest targeted portability/collector verification: 20 passed. Neither is a fresh whole-suite baseline for this plan.

Approaches considered: wholesale directory reorganization would create broad import churn; deleting by name/age or count would risk lost regressions. Recommended: staged behavior-based consolidation, keeping existing directories unless a specific resource classification or ownership problem warrants a move. This is the coordinator's recommendation under the user's delegated stakeholder authority.

## Global constraints

- Do not change product code, API contracts, model weights, thresholds, KB, frozen benchmark data or historical audit outputs to make tests pass.
- Keep mandatory escalation, no automatic sending, privacy/authorization, source validation, persistence, client ownership, deadline behavior and provider budget checks.
- No API/provider calls, model training or GPU work for cleanup. Real-model/live profiles remain explicit opt-ins; the separate B experiment does not authorize more cleanup calls.
- No new framework, dependency, generic test builder, blanket autouse fixture or cosmetic mass rename.
- Preserve test isolation: temporary paths, independent DB schemas and cleanup in failure paths. Never operate on production schemas or shared basetemp directories.
- Preserve the existing default marker selection until an explicit reviewed change proves equivalent required coverage. A skip, deselection or empty collection is not a pass.
- Do not delete frozen fixtures or real-model/CUDA/live tests merely because default execution excludes them.
- Preserve user files and private credentials. Use the project's virtual environment; never log secret configuration values.

## Review focus

1. Moving/merging tests must retain distinct Engine, PipelineRunner and HTTP behavior assertions; matching inputs do not make surfaces equivalent.
2. Global monkeypatches, import caches, environment variables and event loops must be restored even after failure.
3. Fixture consolidation must retain ownership, authorization, model provenance and calibration differences.
4. DB/schema/process cleanup must happen on both success and exceptions; application requirements must not be concealed by new skips.
5. Frontend consolidation must retain role permissions, accessible interactions, draft review actions and all configured viewport projects.

## Task 1 — Baseline and behavior map (coordinator, before edits)

**Files:** `tests/README.md`, this plan; inspect `pytest.ini`, `tests/conftest.py`, frontend test configuration.

- [ ] Run `.venv/Scripts/python.exe -m pytest --collect-only -q`; retain collected node IDs outside immutable evaluation directories, grouped by resource profile.
- [ ] Run the current default suite with native PostgreSQL configured and `--durations=20`; record passed/skipped/deselected and skip reasons. On Windows use `PSYCOPG_IMPL=python` and PostgreSQL's bin directory on PATH. Do not print credentials.
- [ ] Run `pnpm.cmd --dir apps/frontend test` and `pnpm.cmd --dir apps/frontend build`. List Playwright tests with `pnpm.cmd --dir apps/frontend exec playwright test --list`; listing does not count as browser execution.
- [ ] Add a compact behavior map to the existing `tests/README.md`: domain, owning modules, resource prerequisites and checks that must survive consolidation. Include network/model/budget guards and PG persistence regression.
- [ ] Record exact before/after node-ID mappings for every subsequent removed or moved test in this plan. Do not create another permanent report hierarchy.

## Task 2 — Profiles, fixtures and isolation (Worker A)

**Files:** `tests/conftest.py`, `pytest.ini`, `tests/fixtures/factories.py`, `tests/annotation_fixtures.py`, `tests/unit/test_test_profiles.py`, `tests/unit/test_demo_lifespan.py`, `tests/application/test_application.py`; edit other consumers only when the behavior map proves shared setup.

- [ ] Compare repeated setup by values and teardown semantics, not function names. Reuse existing factories only where equivalent setup has at least two consumers; keep domain-specific fixture logic local.
- [ ] Document PostgreSQL prerequisites and current skip behavior. Inspect all application/e2e resource use; apply existing integration markers only where actual loopback/process/SQLite work requires them. Do not broadly mark all tests to bypass network guards.
- [ ] Preserve function-scoped async fixture policy. Verify environment/sys.modules restoration and injected versus owned clients, including exception teardown. Add a focused regression only for a demonstrated gap.
- [ ] Run `tests/unit/test_test_profiles.py`, `test_factories.py`, `test_demo_lifespan.py`, `test_input_snapshot_persistence.py`, `test_portable_evaluation_paths.py` and affected consumers; compare collection and skip reasons with baseline. Commit scoped changes.

## Task 3 — Backend and evaluation test consolidation (Worker B, after live experiment review)

**Files:** `tests/unit/test_accounting_guardrails_b.py`, `test_model_comparison.py`, `test_evaluation_ml.py`, `test_training.py`, `test_model_runtime_parity_b.py`, `test_retrieval_grounding_b2.py`, `test_review_eight_fixes.py`, `test_system_review_probes.py`, `test_system_review_probes_v2.py` and existing domain owners identified in Task 1.

- [ ] Inventory each target's scenarios, assertions, dependencies and current callers/imports. Group by behavior: accounting/provenance, routing/faults, grounding/retrieval, training/evaluation and client lifecycle.
- [ ] Start with the mixed historical review files. Move a test to an existing domain owner only if it improves discoverability; preserve its assertion semantics. Keep descriptive regression names, or map old names explicitly.
- [ ] Parameterize cases only when setup, action and assertion structure match. Keep differing safety, permission and fault behavior explicit. Delete a test only with a named surviving equivalent and recorded unique-assertion comparison.
- [ ] Split a large file only where it owns independent domains; size alone is not a deletion/split criterion. Reuse local helpers before creating new shared modules.
- [ ] Run each source and destination suite together after every group; compare case counts and mapping. Verify no lost wrong-intent, mandatory escalation, cross-customer, budget, missing-thinking-usage, source tampering or persistence scenarios. Commit each coherent group.

## Task 4 — Application, frontend and browser hygiene (Worker C)

**Files:** `tests/application/`, `tests/integration/`, `tests/e2e/test_full_pipeline.py`, `apps/frontend/src/components/reply-rules.test.ts`, `apps/frontend/src/features/console-permissions.test.tsx`, `console.test.tsx`, `support.test.tsx`, `apps/frontend/e2e/application.spec.ts`, `apps/frontend/playwright.config.ts`.

- [ ] Find repeated login/seed/transport setup and compare roles, owner IDs, time/as_of and schema teardown before sharing it. Keep schema and HTTP client lifetimes explicit; avoid a global mutable app fixture.
- [ ] Review frontend setup duplication and prefer assertions about visible behavior, roles and user interactions. Preserve viewport and accessibility checks; do not replace them with snapshots of implementation details.
- [ ] Review browser fixtures for unique account/session/data isolation and cleanup on failures. Retain all four viewport projects; no arbitrary timeout increases or retry-based masking.
- [ ] Run changed Python suites and frontend tests/build. Execute changed browser scenarios against an isolated app with LLM mocked/disabled; no external calls and no writes to the running user app. If unavailable, report browser execution as blocked, not passed. Commit scoped changes.

## Task 5 — Integration and completion (coordinator)

- [ ] Review and integrate only owned files. Serialize shared fixture/config changes before merging consumer edits; resolve collection/import conflicts against Task 1's mapping.
- [ ] Run the final default pytest suite with `--durations=20`, frontend tests/build, and affected isolated Playwright scenarios. Recheck collection and exact skip/deselection reasons; explain every removed node ID.
- [ ] Compare runtime under the same environment. Report observations without a fixed speed target or assertions that fewer tests means better coverage.
- [ ] Update `tests/README.md` with the final runnable profiles and append the result to `docs/codebase-cleanup-log.md`. Record unchanged required safety scenarios and any checks not run.
- [ ] Commit and push reviewed cleanup according to the user's existing main-branch authorization, without force push. No claim of product acceptance solely because tests pass.

## Completion criteria

Every deleted/merged test has a reviewed equivalent; unique required regressions remain; default guards and resource opt-ins remain effective; changed suites and final integration checks pass with disclosed skips; docs match actual commands and prerequisites. No numerical test-removal quota. If evidence shows no safe consolidation in a group, keep it and record why.

## Execution status

Planning complete; Tasks 1–5 not executed. No tests removed or renamed by this planning change. A/B/C allocation is proposed and has not been dispatched for implementation.
