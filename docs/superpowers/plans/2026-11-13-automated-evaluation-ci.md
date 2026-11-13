# Automated Evaluation and CI Implementation Plan

> **For agentic workers:** Execute assigned tasks using existing Orca orchestration, Ponytail ultra and focused regression checks. No helper agents. The user explicitly authorized implementation.

**Goal:** Run reproducible test and evaluation checks on pull requests and main pushes, with failures blocking the relevant job and useful retained evidence.

**Architecture:** Extend existing pytest/Vitest/Playwright and `pipeline.evaluation.autoeval`; do not build a second evaluator. Separate mandatory offline CI from optional real-model and paid-provider experiments. This deploys CI configuration and evaluation tooling, not a new production hosting environment.

**Tech Stack:** GitHub Actions, Python 3.12, CPU torch, native pytest dependencies, disposable PostgreSQL service, pnpm with lockfile, Vitest and existing evaluation CLI.

**Spec:** User request to plan and implement automatic evaluation and CI, alongside [test cleanup](2026-11-13-test-suite-cleanup.md). Existing requirements and frozen benchmarks remain authoritative.

## Design decisions and constraints

- Prefer extending `.github/workflows/autoeval.yml` and adding a general test workflow over a new orchestration framework or report aggregator.
- PR/main checks must include full default Python tests with isolated PostgreSQL configuration, frontend tests/build, and deterministic offline LLM validator/privacy/fault evaluation. Upload JUnit, evaluation JSON/Markdown and build evidence on failure as applicable.
- Required jobs must propagate actual exit codes, including evaluation failures and setup errors. No default `continue-on-error`, opt-out enforcement, or missing required metrics reported as pass.
- The offline suite tests validators, contracts and faults with synthetic dependencies. It does not measure real LLM semantic grounding, model F1 or full system acceptance.
- Model weights are not assumed present on GitHub runners. An explicitly requested ML evaluation must fail clearly if weights cannot be provisioned and verified; ordinary offline CI must label ML as not evaluated. Do not silently claim a full ML+LLM pass.
- Remove unattended scheduled paid calls. No new provider calls, key provisioning, GPU or training in this implementation. Paid evaluation remains explicitly invoked and bounded separately; do not deploy an unreviewed live workflow with an ineffective HTTP-attempt cap.
- Never upload `.env`, `.local`, database credentials, raw user data or entire unrelated artifact directories. CI DB credentials are disposable synthetic values, passed only to disposable test resources.
- Minimal `contents: read` token permissions, concurrency, bounded job timeouts and trusted events. No `pull_request_target` execution of untrusted checkout with secrets. Use lockfile frontend installs and supported action/runtime versions checked against official documentation.
- No threshold relaxation, benchmark regeneration, candidate promotion, app behavior changes or generalized fixture rewrites to make CI green.
- Keep local Windows commands usable. CI Linux PostgreSQL service complements native Windows checks; it does not prove Windows startup or browser success.
- Preserve user PPTX, model/data artifacts, historical reports, current running services and private configuration.

## A — Reliable evaluator CLI (Worker A)

**Files:** `pipeline/evaluation/autoeval/cli.py`, `gates.py`, `report.py` only as needed; `tests/unit/test_autoeval.py` or focused adjacent evaluator CLI tests.

- [ ] Inspect current suite validation, config/manifest handling, exit codes and missing comparison behavior. Preserve existing gate thresholds.
- [ ] Reject empty/unknown suite selections. Return documented code 2 for setup/evaluation errors without leaking credentials; preserve usable failure evidence where possible. A requested baseline that is missing or malformed must not silently bypass comparison.
- [ ] Make selected blocking metrics fail closed when absent, except explicit legitimate offline/live scope exclusions; distinguish not-run from passed. Preserve optional advisory metrics and existing offline scope.
- [ ] Add focused tests for invalid suite, missing required comparison, malformed/changed manifest, missing blocking metric and runtime failure. Use temporary output/config and mocked evaluator dependencies, no model/provider.
- [ ] Run focused tests plus actual offline CLI into a fresh temporary output path; record any real gate failure honestly instead of rewriting data or weakening thresholds. Commit only owned code/tests. Do not edit workflow/config/docs owned by B/C.

## B — CI workflows (Worker B)

**Files:** `.github/workflows/autoeval.yml`, new `.github/workflows/ci.yml`, minimal CI dependency/config helper only if existing requirements cannot be reused.

- [ ] Merge local main in worker first. Implement PR, push-main and manual triggers covering code, tests, frontend, configuration and workflow changes. Avoid path-filtered required jobs that leave checks pending.
- [ ] Python job: Python 3.12, CPU dependencies from existing requirement sets, pytest/asyncio test dependencies, disposable PostgreSQL service with health check, temporary application secrets file pointing to service; run default suite with JUnit and bounded duration reporting. Ensure DB tests actually execute rather than all skip. Never use root private files.
- [ ] Frontend job: install pnpm, use frozen lockfile, run tests and production build. Retain useful artifacts only; do not upload dependency caches or credentials as evidence.
- [ ] Offline autoeval job: actual `--suite llm --llm-mode offline`, enforce CLI exit code unconditionally and upload fresh reports with `if: always()`. No model download needed for this scope and no use of stale latest.txt after failed run. Reuse A's unchanged CLI command contract.
- [ ] Remove schedule-triggered paid calls and misleading optional enforcement. If preserving an optional model-only manual mode, require verified model inputs and fail on missing assets; do not implement arbitrary unsafe model archive extraction. It is acceptable to document real-model CI as pending provisioning rather than add this mode now.
- [ ] Validate workflow syntax with an available established validator and inspect expressions/events/permissions. Verify dependency and PostgreSQL assumptions locally where possible; clearly distinguish static validation from a hosted GitHub run. Commit only owned files.

## C — Test cleanup first batch and operating guide (Worker C)

**Files:** `tests/README.md`, `docs/autoeval.md`, `docs/guides/application-verification.md`; test code only in a small independently justified group from the test-cleanup plan, excluding A's evaluator tests and global fixture/config ownership.

- [ ] Merge local main; read both plans. Record actual collection/profile prerequisites, including PostgreSQL-backed application tests and current skip behavior. Correct commands and stale claims in current guidance without rewriting historical observations.
- [ ] Build a concise behavior map in tests/README, preserving regression ownership and explaining offline versus real-model/live scope.
- [ ] Review historical review/probe tests and propose exact source/destination mappings. Implement at most one proven equivalent consolidation group initially; if no safe duplication is established, keep the tests and report the finding. Do not delete merely by age, filename or test count.
- [ ] Document CI jobs, local equivalent commands, interpretation of gates, evidence retention, and explicitly manual paid evaluation. Do not describe structural citation validation as semantic grounding or AI judgments as real human study.
- [ ] Run changed test groups and relative-link checks. Commit owned files and evidence of any old-to-new test mapping; zero provider calls.

## Coordinator integration and verification

- [ ] Review B's completed online experiment separately; preserve raw outputs and remaining global budget (21/24 already used, 3 remain). No extra calls for CI setup.
- [ ] Integrate selective owned commits, check conflicting assumptions between workflow, evaluator and docs, and run the final default Python suite with PostgreSQL plus frontend tests/build and actual offline evaluator. Each failure gets fixed by its owner or reported honestly.
- [ ] Run workflow validation and inspect dependencies from clean-runner perspective. Do not claim Linux/hosted CI passed based only on Windows tests.
- [ ] Commit and push reviewed changes to `minh` under the user's latest branch instruction. Inspect the resulting GitHub Actions runs when authenticated tooling permits; report remote pass/fail or exact access/billing/environment blocker.
- [ ] Update existing cleanup log and plan status. Required-check branch-protection settings are a separate repository setting: inspect available access and report any configuration not applied. No invented production deployment target.

## Acceptance

Required local verification succeeds; CI executes meaningful backend/PG and frontend checks plus offline evaluation with failure propagation and retained evidence; no automatic paid calls or secret artifacts; docs accurately state unmeasured model/live/browser scope. Hosted execution is recorded separately and no full product acceptance is implied.

## Integration status, 2026-11-13

- Workflow and operating guide integrated at `5c5be81`; evaluator failure handling and corrected fault probes at `667f54f`; source-egress privacy at `4f194f2` on `minh`.
- Independent review required follow-up fixes for policy-text egress, source mapping, numeric token matching, sentence boundaries and transaction statements. Current combined verification includes those fixes; no thresholds or frozen benchmark labels were relaxed.
- Combined offline LLM evaluation: exit 0, four blocking gates passed, zero blocking failures, two warnings (validator probe pass rate 15/18; redaction probe pass rate 8/11), twenty metrics not run. This does not evaluate real-model ML or semantic entailment.
- Frontend: 18 tests passed across four files; production build passed. First combined Python verification exposed six failures. After A's namespace bootstrap fix, C's source-backed privacy controls and coordinator corrections to stale mock responses, final default Python verification passed: **1,067 passed, 2 skipped, 3 deselected in 265.48 seconds**. The coordinator handled the final two fixture failures after both B and C hit provider quota; no safety assertion or validator was weakened.
- Push triggers cover `main` and the user's requested `minh` branch. Workflow YAML and trigger/permission checks pass locally; no hosted-run result is asserted.
- Hosted inspection is currently limited: `gh` is unavailable on PATH, and unauthenticated GitHub Actions API inspection returned HTTP 404. This does not prove the repository or workflows are missing.
- Test cleanup first batch retained all 29 reviewed historical probes because no safe duplicate pair was established. Wider test restructuring and real-model CI provisioning remain separate unfinished tasks.
