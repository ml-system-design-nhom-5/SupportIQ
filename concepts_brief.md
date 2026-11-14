# Complete Codebase Cleanup, Infrastructure Consolidation, and Multi-Stage Refactoring

* **Author:** FatPandaC8
* **Date:** 2026-11-13
* **Target Branch:** `refactor/optimization-and-cleanup`

## Overview

SupportIQ is a production-grade AI Customer Support Copilot with a green test baseline (470+ passing tests across unit, integration, e2e, and frontend suites). However, rapid iterative development and metric-tuning fixes have introduced systemic dead code, utility duplication, redundant hot-path queries, unstandardized HTTP/DB client lifecycles, and verbose procedural boilerplate.

This initiative executes a repository-wide cleanup and refactoring across every subsystem (`apps/backend`, `apps/core_backend`, `apps/ai_service`, `apps/demo`, `apps/ml_inference`, `pipeline`, and `scripts`), prioritizing simplicity, reliability, performance, and maintainability without altering existing API contracts, database schemas, or system invariants. Documentation cleanup is explicitly out of scope.

## Repository Inspection Findings & Issue Prioritization

Following a comprehensive static and dynamic audit of the entire codebase against the established test baseline, the identified issues are categorized and prioritized below by severity and impact:

| Priority | Dimension | Subsystem / Location | Issue Description | Severity / Impact |
|:---:|:---|:---|:---|:---|
| **P1** | **Reliability & Performance** | `apps/core_backend/orchestration/store.py` | `save_input_snapshot` executes `CREATE TABLE IF NOT EXISTS llm_inputs` on every single invocation instead of in `_init_db`. Connections lack busy timeout and WAL configuration, risking lock contention under concurrency. | **High** — Redundant DDL and lock risk on every ticket ingress. |
| **P1** | **Infrastructure Consolidation** | `apps/core_backend/llm/gemini.py`, `apps/core_backend/intent/client.py`, `apps/backend/tickets/jobs.py` | Disparate and uncoordinated `httpx.Client` instances. Ad-hoc ownership flags (`self._owns_http`), inline `import hashlib` inside inner functions, and unclosed client instances during exception edges. | **High** — Connection leak and resource management risks. |
| **P2** | **Dead Code & Duplication** | `scripts/run_benchmarks.py`, `pipeline/preparation/utils.py`, `apps/ml_inference/app.py` | The 150-line `INTENT_KEYWORDS` regex dictionary in `scripts/run_benchmarks.py` duplicates `apps/ml_inference/app.py`. Redundant `compute_sha256` functions exist across 5 independent files. | **Medium** — Code bloat, divergence risk when updating intent patterns. |
| **P2** | **Implementation Simplification** | `apps/core_backend/retrieval/adapter.py`, `apps/ai_service/engine.py` | Over-nested loops for document serialization and provenance extraction. Redundant set allocations and manual type introspection (`getattr(error, 'code', ...)`). | **Medium** — Increased cognitive load and maintenance friction. |
| **P2** | **Performance & Memory** | `apps/core_backend/llm/gemini.py`, `apps/backend/tickets/privacy.py` | Uncompiled regexes in `redact_contacts()` with nested helper functions re-declared on every call. `TokenVault` re-instantiates pattern matchers on each text chunk. | **Medium** — Avoidable CPU overhead in high-throughput sanitization. |
| **P3** | **Architecture & Boundary Hygiene** | `apps/ai_service/engine.py` vs `apps/core_backend/orchestration/pipeline_runner.py` | Parallel routing logic reimplemented in `apps/ai_service/engine.py` instead of consuming canonical schemas from `apps/core_backend/intent/schemas.py`. | **Low/Medium** — Architectural drift between demo/evaluation harness and production backend. |
| **P3** | **Testing Quality** | `tests/unit/test_demo_lifespan.py`, redundant test fixtures in `tests/fixtures/` | Duplicate mock setups across integration and unit tests, deprecated loop scoping warnings, and obsolete cleanup artifacts. | **Low** — Test suite hygiene and execution speed. |

## Goals vs. Non-Goals

### In-Scope Goals
1. **Dead Code Elimination:** Remove duplicate functions (`compute_sha256`), redundant regex dictionaries, unused imports, dead constants, and obsolete test helpers.
2. **Infrastructure Consolidation:** Standardize HTTP client instantiation, connection pooling, and lifecycle cleanup across `IntentClient`, `GeminiDraftClient`, and background jobs. Configure SQLite WAL mode and busy timeouts in `PersistentStore`.
3. **Implementation Simplification:** Extract DDL from `save_input_snapshot` to `_init_db`. Compile regexes at the module level. Flatten nested loops in retrieval and routing adapters.
4. **Reliability Hardening:** Ensure complete resource closure on exception paths. Unify error code mapping across HTTP and ML boundaries.
5. **Incremental Verification:** Execute full test suites (`pytest tests/unit`, `pytest tests/integration`, `pytest tests/e2e/test_full_pipeline.py`, and Vitest frontend tests) at the end of each stage.

### Out-of-Scope Non-Goals
* **No Documentation Changes:** No files in `docs/` or `.md` references will be modified, deleted, archived, or reorganized.
* **No Breaking Schema or Contract Changes:** Zero alterations to SQLite/PostgreSQL table schemas, OpenAPI specifications, or frontend API shapes.
* **No Algorithmic or Model Changes:** Pinned DistilBERT weights, BGE-small-en embedding logic, Temperature Scaling parameters ($T=1.25$), and routing thresholds remain strictly untouched.
* **No Unnecessary Abstractions:** No introduction of generic interfaces, factory wrappers, or design patterns that do not directly eliminate proven duplication.

## Incremental Staging Plan

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Shared Utilities & Dead Code Deduplication        │
│ - Centralize `compute_sha256` into a shared utility        │
│ - Deduplicate `INTENT_KEYWORDS` across ML inference/scripts │
│ - Remove unused imports and dead constants                 │
│ - Gate: All 403 unit tests PASS                            │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Storage & Concurrency Optimization                 │
│ - Move `llm_inputs` DDL from `save_input_snapshot` to init  │
│ - Apply WAL mode & busy timeout to `PersistentStore`        │
│ - Gate: Integration tests (25 tests) & e2e (29 tests) PASS  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: HTTP Client & Resource Lifecycle Standardization   │
│ - Standardize pooled HTTP client lifecycle in Intent & LLM  │
│ - Ensure explicit context management on error edges         │
│ - Gate: `test_demo_lifespan.py` & AI boundary tests PASS    │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: Hot-Path Simplification & Regex Performance        │
│ - Pre-compile regexes in `redact_contacts` and `TokenVault` │
│ - Simplify nested document mappings in retrieval adapter   │
│ - Gate: Regression evaluator (`evaluate_regression.py`) PASS│
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 5: Final Comprehensive Verification                   │
│ - Full run of unit, integration, application, e2e, frontend │
│ - Validate zero diff in public API signatures & outputs     │
│ - Clean git tree on `refactor/optimization-and-cleanup`     │
└─────────────────────────────────────────────────────────────┘
```

## Alternatives Weighed

* **Unifying `apps/core_backend` and `apps/ai_service` into a Single Service:**
  - *Status:* Rejected.
  - *Reason:* `apps/core_backend` is the monolithic internal engine consumed by offline benchmarks, evaluation harnesses, and tests; `apps/ai_service` is an HTTP microservice boundary consumed by `apps/backend`. Merging them would break the architectural separation between offline pipeline benchmarks and the HTTP application tier.
* **Replacing SQLite with PostgreSQL in Local Development:**
  - *Status:* Rejected.
  - *Reason:* SQLite is required for zero-infrastructure self-contained execution within 5 GB RAM on consumer hardware.

## Key Decisions & Invariants
1. **Preserve Pinned Releases:** Checksums for `EXPECTED_MANIFEST` (model weights, tokenizers) must not be altered.
2. **Strict Non-Regressive Verification:** Any stage that fails even a single unit or integration test will be immediately reverted before progressing.
