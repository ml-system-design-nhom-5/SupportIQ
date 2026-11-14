# Code Cleanup Preparation Plan (Read-Only Inventory — Worker D)

> **Status:** Active · **Owner:** Worker D (read-only preparation) · **Last reviewed:** 2026-11-14
> **Branch:** `minh` · **Scope:** Read-only dead-code, duplicate-helper, stale-doc, and scoped-cache cleanup inventory. **Zero files deleted, edited, moved, or executed in this pass.**

---

## 1. Executive Summary & Top 3 High-Confidence Wins

| Priority | Candidate / Scope | Action Proposed | Savings / Impact | Risk | Minimal Verification (After Execution) |
|---|---|---|---|---|---|
| **Win 1** | Allowlisted pytest caches (`tmp/pytest/*`, `.pytest_cache/`, source `__pycache__/`) + 2 eval `__pycache__/` dirs + `.playwright-mcp/` | `DELETE_PROPOSED` (path-scoped inside `MAIN`) | **~1,181.80 MB+** across `22,860+` untracked cache files | **Low** (must preserve `.pytest-cleanup.lock` and `tmp/report-work/`) | `powershell -ExecutionPolicy Bypass -File scripts/clean_test_cache.ps1` (dry-run) -> `-Apply`; `.venv\Scripts\python.exe -m pytest tests/integration/test_cache_cleanup.py -q` |
| **Win 2** | Dead `export function Admin()` + unused imports (`apps/frontend/src/features/admin.tsx:2,7,32`) + 2 unused CSS classes (`styles.css:57,126,167`) + 3 internal-only `export` keywords (`App.tsx:33`, `types.ts:18,25`) | `DELETE_PROPOSED` (edit/prune in 1 small PR) | Removes obsolete pre-unification wrapper after `4c18e9a` | **Low** (zero callers verified by CodeGraph + repo grep) | `pnpm --dir apps/frontend test` and `pnpm --dir apps/frontend build` |
| **Win 3** | Duplicate `compute_sha256` definitions (`7` copies outside canonical `pipeline/preparation/utils.py:144`) + dead `is_safe_uncited_paragraph` (`apps/core_backend/safety.py:579`) | `DELETE_PROPOSED` (consolidate `compute_sha256`; remove dead safety wrapper) | Eliminates drift across eval/scripts/tests; completes unfinished item from `docs/design/codebase-cleanup-and-refactoring.md` | **Low** (test each caller module after import swap) | `.venv\Scripts\python.exe -m pytest tests/unit/test_ai_grounding.py tests/unit/test_supported_unsupported_boundary_b.py tests/unit/test_autoeval.py tests/unit/test_backend_evaluation_guardrails.py tests/application/test_final_acceptance_suite.py tests/unit/test_isolated_browser_e2e_cleanup.py tests/unit/test_factories.py -q` |

> **CodeGraph Caveat Observed:** All CodeGraph MCP queries (`codegraph_explore` on `F:/Năm 3/SD/project/SupportIQ`) ran against `.codegraph/` without modifying or reindexing it. Because CodeGraph reported live auto-sync disabled (file lock held by another writer), every dead-symbol and caller claim below was cross-checked directly against current on-disk source and `git grep` (excluding Worker A's 4 active mutable files).

---

## 2. Protected Explicit Inventory (`KEEP` — Do Not Delete or Modify in Cleanup)

All items below were verified on disk / in git status and MUST remain untouched:

- **Datasets & Provenance (`data/`):** All raw, cleaned, split, TRAIN, CAL, test, benchmark (`data/benchmarks/autoeval/v1/`, `v3/acceptance/`), approved KB (`data/knowledge/approved_kb.v2.json`), and provenance manifests.
- **All Model Artifacts (`artifacts/models/`, including unstaged `D artifacts/models/.gitkeep`):**
  - Baseline serving model (`artifacts/models/trained/distilbert-supportiq`), pretrained init (`artifacts/models/pretrained/distilbert-base-uncased`), finetuned (`artifacts/models/finetuned/supportpilot-distilbert`), Original Fit2 (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113`), and every candidate/rejected/control checkpoint, calibration state, tokenizer, config, log, and `run-records-*` archive under `artifacts/models/candidates/`.
  - Pre-existing `D artifacts/models/.gitkeep` working-tree deletion: preserve as-is.
- **Evaluation, Preparation & Training Records (`artifacts/preparation/`, `artifacts/training/`, `artifacts/evaluation/`, `artifacts/audit/`):** All run records, hashes, preps, reports, browser acceptance evidence (`artifacts/browser/`), plus untracked `artifacts/evaluation/boundary_contrast_20261114/` and `artifacts/evaluation/fit2_orig_ret_channel_20261114/`.
- **PPTX Presentation Assets:** `report.pptx`, `docs/report.pptx`, untracked `docs/report.template.pptx`, and **`tmp/report-work/`** (`601` files, `33.12 MB` — contains `build_report.py`, `template.pptx`, `report.full-57.pptx`, fonts, and slide previews).
- **Course Reference & Tooling Infrastructure:** `ai-for-production.zip` (`41.96 MB`, cited in `docs/data-quality.md`, `pipeline/README.md`, cleanup plans), `.codegraph/`, `.env`, `.local/`, `.venv/`, `apps/frontend/node_modules/`, `.pytest-cleanup.lock`.
- **Deployment / Compatibility & Preserved Subsystems:**
  - `apps/frontend/functions/{api,health,v1}/[[path]].js` and `apps/frontend/public/_redirects` (Cloudflare Pages backend proxy routes).
  - `apps/demo/` & `apps/ml_inference/` (`KEEP`: imported by CI workflows `.github/workflows/{ci,autoeval}.yml`, `apps/ai_service/main.py`, `pipeline/evaluation/`, `scripts/`, and unit/integration tests).
  - Legacy `manager` role support (`types.ts`, `ui.tsx`, `App.tsx`, `admin.tsx`, `console.tsx`, `styles.css:198` `.avatar.manager`) and dynamic shell selectors (`.console-app`, `.shop-app` built via `` `app ${area}-app` `` in `App.tsx:45`).
- **Active Runtime / Governance / Workspaces:** Active Original Fit2 serving config, port bindings (`8080`, `8002`, `5432`/native PG), LLM budget limits, and any external worker branches/worktrees.

---

## 3. Validated Cleanup Candidates (Path-by-Path)

### 3.1 Frontend (`apps/frontend/`)

| Path / Symbol | Decision | Reason Unused / Issue | CodeGraph & On-Disk / Grep Evidence | Risk | Minimal Verification |
|---|---|---|---|---|---|
| `apps/frontend/src/features/admin.tsx:32` (`export function Admin`) + unused imports `Navigate, Route, Routes` (`:2`) & `Empty` (`:7`) | `DELETE_PROPOSED` | Obsolete router wrapper from pre-unification `/admin/*` app shell; `App.tsx` now mounts `Accounts` and `AssetVersions` directly under `/console/*`. | `codegraph_explore` (`Apps/App.tsx`, `features/admin.tsx`) shows `App.tsx:12` imports `{ Accounts, AssetVersions }` only; `git grep` confirms `Admin(` has `0` callers across `apps/frontend/`. (`Empty` in `components/ui.tsx` remains `KEEP`, used in `shop.tsx` & `console.tsx`.) | Low | `pnpm --dir apps/frontend test` & `pnpm --dir apps/frontend build` |
| `apps/frontend/src/styles.css:167` (`.recommendation-panel ...`) & `:57,:126` (`.support-form ...`) | `DELETE_PROPOSED` | Dead CSS selectors left over from earlier mockup iterations. | Repo-wide `git grep -n -E "recommendation-panel\|support-form"` returned `0` hits outside `styles.css` (`index.html`, `src/`, `tests/`, `e2e/`). | Low | `pnpm --dir apps/frontend build` |
| `apps/frontend/src/App.tsx:33` (`export function Shell`) & `apps/frontend/src/types.ts:18,25` (`export interface Suggestion`, `Proposal`) | `DELETE_PROPOSED` (drop `export` only, keep symbols) | Only referenced inside their own files (`App.tsx` and `types.ts:26` `Workspace`). | Frontend AST/regex export scan + `git grep` confirm `0` external importers in `apps/frontend/`. | Low | `pnpm --dir apps/frontend test` & `pnpm --dir apps/frontend build` |

### 3.2 Backend & Core AI (`apps/backend/`, `apps/core_backend/`, `apps/ai_service/`)

| Path / Symbol | Decision | Reason Unused / Issue | CodeGraph & On-Disk / Grep Evidence | Risk | Minimal Verification |
|---|---|---|---|---|---|
| `apps/core_backend/safety.py:579-585` (`is_safe_uncited_paragraph`) | `DELETE_PROPOSED` | Superseded wrapper; grounding enforcement moved to sentence granularity via `_is_safe_uncited_sentence` directly. | `codegraph_explore` + AST scan + `git grep -n "is_safe_uncited_paragraph"` confirm `0` callers in code or tests (only mentioned in historical audit `2026-11-14-polite-framing-grounding-review-c.md`). Call sites at `safety.py:808, 839, 899` invoke `_is_safe_uncited_sentence` directly. | Low | `.venv\Scripts\python.exe -m pytest tests/unit/test_ai_grounding.py tests/unit/test_supported_unsupported_boundary_b.py -q` |

### 3.3 Duplicated Helpers Across Pipeline, Scripts & Tests

| Canonical Target | Duplicate Paths (`DELETE_PROPOSED` — replace with import) | Reason & Evidence | Risk | Minimal Verification |
|---|---|---|---|---|
| `pipeline/preparation/utils.py:144` (`compute_sha256`) | 1. `pipeline/evaluation/application_acceptance.py:40`<br>2. `pipeline/evaluation/ml_provenance_audit.py:32`<br>3. `scripts/collect_final_acceptance_evidence.py:71`<br>4. `scripts/evaluate_regression.py:73`<br>5. `scripts/run_isolated_browser_e2e.py:54`<br>6. `tests/application/test_final_acceptance_suite.py:25`<br>7. `tests/fixtures/factories.py:22` | `git grep -n "def compute_sha256"` found 8 copies of the exact chunked SHA-256 helper. Consolidating fulfills the unfinished Item 1 in `docs/design/codebase-cleanup-and-refactoring.md:75`. (Keep `sha256_file` in `pipeline/evaluation/autoeval/backends.py:22` standalone so `autoeval -Light` remains dependency-minimal.) | Low (ensure `REPO_ROOT` is on `sys.path` before importing `pipeline.preparation.utils` in standalone `scripts/*`) | Run CLI `--help` on edited `scripts/*` + `pytest` on `test_autoeval.py`, `test_backend_evaluation_guardrails.py`, `test_final_acceptance_suite.py`, `test_isolated_browser_e2e_cleanup.py`, `test_factories.py` |

### 3.4 Scripts & Ops Config (`scripts/`, `monitoring/`)

| Path | Decision | Reason & Evidence | Risk | Minimal Verification |
|---|---|---|---|---|
| `scripts/run_live_ff0e147_verification.py` | `DELETE_PROPOSED` (or `MOVE` to historical archive if desired) | Point-in-time bounded live probe hardcoded to candidate commit `ff0e147`; `0` inbound refs in code, tests, CI, or non-audit docs (`git grep`). Keep only if coordinator needs replay of `ff0e147`. | Low | Verify `git grep run_live_ff0e147_verification` stays `0` outside audit docs |
| `scripts/clean_test_cache.ps1` | `KEEP` (minor cleanup: drop nonexistent `'services'` from `$sourceRoots:7`) | Active tested cache cleaner (`tests/integration/test_cache_cleanup.py`), `services/` directory does not exist in repo. | Low | `pytest tests/integration/test_cache_cleanup.py -q` |
| `scripts/run_autoeval.ps1` | `KEEP` | `0` code grep hits only because it is a human/local Windows entrypoint mirroring `.github/workflows/autoeval.yml`. | — | — |
| `scripts/inspect_application.mjs` | `KEEP` (dev-only helper) | Authenticated CDP helper (`0` code refs) wrapping local `.agents/skills/design-taste-frontend/scripts/inspect.mjs`. Remove only if skill-based visual inspection is retired. | — | — |
| `scripts/start-local.sh`, `scripts/stop-local.sh`, `scripts/validate-local.sh`, `scripts/init_db.py` | `KEEP` (POSIX/historical parity) | Windows primary flow uses `start-app.ps1`/`stop-app.ps1`; `.sh` scripts remain cited by `docs/FINAL_CHANGE_EXPLANATION.md`, `docs/AI_PIPELINE_METRIC_IMPROVEMENTS.md`, `ARCHITECTURE_COMPLIANCE_AUDIT.md`, and `non-model-bottlenecks-c.md`. Do not remove without dropping POSIX compatibility. | — | — |
| `monitoring/prometheus.yml` | `KEEP` | Standalone local scrape config targeting `127.0.0.1:8080/metrics` (`apps/backend/main.py:316`). `0` code refs because Prometheus runs externally when desired. | — | — |

### 3.5 Documentation (`docs/`, `README.md`)

| Path | Decision | Inbound Links / Verification Evidence | Risk | Action Note |
|---|---|---|---|---|
| `docs/README.md`, `docs/codebase-cleanup-log.md`, `docs/review-eight-fixes.md`, `docs/core-backend-runbook.md`, `docs/core-backend-verification.md`, `docs/autoeval.md`, `docs/CHỦ ĐỀ 1.md`, `docs/design/assets/*`, `docs/audits/*`, `docs/superpowers/*` | `KEEP` | Verified inbound references from `docs/README.md`, `docs/system-evaluation-report.md`, `docs/superpowers/*`, `README.md`, `PRODUCT.md`, or `tests/README.md`, or active audit/course brief artifacts. | — | Preserved intact |
| `docs/FINAL_CHANGE_EXPLANATION.md`, `docs/AI_PIPELINE_METRIC_IMPROVEMENTS.md`, `docs/playwright-intent-report.md` | `MOVE` or `KEEP` (NOT delete) | Tracked-repo `git grep` shows `0` inbound links to these 3 root `docs/` snapshots from `2026-11-05`/`2026-11-06` (which cite older `429`-test/SQLite/pre-v4 snapshots). Archive under `docs/audits/` or add a historical-snapshot banner; do not delete narrative reports silently. | Low | Check `git grep` for filenames after any move |
| `README.md:3,15,25` (role wording) | `KEEP` (flag for doc text update) | Still describes a separate `manager-1` / Manager role UI after unified staff+admin console (`4c18e9a`). | Low | Docs-only follow-up |

### 3.6 Generated & Ignored Caches (Path-Scoped Proposals Within `MAIN` Only)

| Path | Tracked? | Observed Size / Files | Decision | Verification / Guard Before Future Removal |
|---|---|---|---|---|
| `tmp/pytest/*`, `.pytest_cache/` | `0` tracked (`git ls-files`) | `22,806` files (`1,181.41 MB`) + `5` files (`0.15 MB`) | `DELETE_PROPOSED` (via `scripts/clean_test_cache.ps1 -Apply`) | Ensure no pytest process is running; `.pytest-cleanup.lock` respected automatically by script |
| `artifacts/evaluation/fit2_independent_gate_20261113/__pycache__`, `artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114/__pycache__` | `0` tracked | Bytecode `.pyc` only | `DELETE_PROPOSED` (explicit path removal or add `artifacts/evaluation/**/__pycache__` carefully without touching artifacts) | Verify path is non-reparse inside `MAIN` and `git ls-files <path>` is empty |
| `.playwright-mcp/` | `0` tracked | `49` files (`0.24 MB`) | `DELETE_PROPOSED` | Only when no Playwright MCP session is active |
| `.supercov/` | `0` tracked (NOT in `.gitignore`) | `208` files (`36.08 MB`) | `KEEP` / `DEFER` | Created by external `.supercov` harness (`locks/`, `workspaces/`); inspect owner lock or add `.supercov/` to `.gitignore` instead of blind deletion |
| `tmp/report-work/` | `0` tracked | `601` files (`33.12 MB`) | **`KEEP` (Protected)** | Active PPTX deck assembly (`build_report.py`, `report.full-57.pptx`, `template.pptx`) |
| Remaining `tmp/` files (`tmp/*.png`, `tmp/*.sqlite3`, `tmp/*.log`, `tmp/acceptance-preflight/`, `tmp/ci-integration-eval/`, `tmp/tmpudxh8xh2`, `tmp/udp-guard-snippet.txt`) | `0` tracked | `~3.40 MB` combined | `DEFER` (per-item triage) | Match `2026-11-14-fit2-abc-integration-and-cleanup-manifest.md:59`: keep unless explicitly cleared by run owners |

---

## 4. Suspected / Deferred Cleanup Pending Frozen Worker A Completion

The items below were **intentionally NOT read, audited as dead, or modified** because Worker A is actively working in the training/contrast area on `minh`:

1. `pipeline/training/train_boundary_candidate.py` (Worker A active mutable file)
2. `scripts/run_orig_fit2_return_contrast_fit.py` (Worker A active mutable file)
3. `scripts/run_orig_fit2_return_contrast_prep.py` (Worker A active mutable file)
4. `tests/unit/test_orig_fit2_return_contrast_prep.py` (Worker A active mutable file)
5. Related contrast-fit/curriculum scripts (`pipeline/training/orig_fit2_return_contrast_data.py`, `pipeline/training/boundary_contrast_data.py`, `pipeline/training/boundary_curriculum_data.py`, `scripts/run_boundary_contrast_fit.py`) and one-off probe/audit scripts (`scripts/run_classifier_acceptance_gate.py`, `scripts/run_fault_boundary_checks.py`, `scripts/run_flash_lite_acceptance.py`, `scripts/run_guard_corrections_checks.py`, `scripts/run_provider_resilience_eval.py`, `scripts/run_closure_candidate_audit.py`) — defer any pruning until Worker A freezes and coordinator confirms which reproducibility entrypoints remain needed.

---

## 5. Proposed Reviewable Implementation Batches (Not Yet Executed)

1. **Batch 1 — Path-Scoped Cache Hygiene (Zero Code Risk):**
   - Run `powershell -ExecutionPolicy Bypass -File scripts/clean_test_cache.ps1` (dry-run review) then `-Apply` when no pytest session holds `.pytest-cleanup.lock`.
   - Remove the 2 untracked `__pycache__` folders under `artifacts/evaluation/` and `.playwright-mcp/` using path-scoped literal deletion (never touching `tmp/report-work/`, `.pytest-cleanup.lock`, or `artifacts/models/`).
   - **Verify:** `git status --short` unchanged for tracked files; `.venv\Scripts\python.exe -m pytest tests/integration/test_cache_cleanup.py -q`.
   - **Rollback:** Regenerated automatically on next pytest/evaluation run.
2. **Batch 2 — Dead Code Removal (Frontend + Safety):**
   - Remove unused `export function Admin()` and unused `Navigate, Route, Routes, Empty` imports in `apps/frontend/src/features/admin.tsx`; remove `.recommendation-panel` and `.support-form` rules in `apps/frontend/src/styles.css`; drop unnecessary `export` on `Shell` (`App.tsx`) and `Suggestion`/`Proposal` (`types.ts`).
   - Remove dead `is_safe_uncited_paragraph` in `apps/core_backend/safety.py`.
   - **Verify:** `pnpm --dir apps/frontend test && pnpm --dir apps/frontend build` + `.venv\Scripts\python.exe -m pytest tests/unit/test_ai_grounding.py tests/unit/test_supported_unsupported_boundary_b.py -q`.
   - **Rollback:** Standard single-commit `git revert`.
3. **Batch 3 — Deduplicate `compute_sha256` & Docs Sync (After Worker A Freeze):**
   - Replace the 7 duplicate `compute_sha256` definitions with imports of `pipeline.preparation.utils.compute_sha256` (ensuring `sys.path` setup in `scripts/*`).
   - Update `README.md` role wording to reflect unified staff+admin console; decide archive vs banner for the 3 unlinked root `docs/` historical reports and `scripts/run_live_ff0e147_verification.py`.
   - **Verify:** Relevant unit/application pytest slice + `--help` checks on modified `scripts/*`.
4. **Batch 4 — Post-Freeze Worker A Training/Script Review:**
   - Re-evaluate Section 4 only after Worker A completes and freezes `train_boundary_candidate.py` & `run_orig_fit2_return_contrast_*.py`.
