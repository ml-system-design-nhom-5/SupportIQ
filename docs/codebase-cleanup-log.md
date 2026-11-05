# Codebase & Test Cleanup Execution Log

- **Baseline Commit:** `348b827` (`main`)
- **Python Environment:** Python 3.12.14 (`.venv\Scripts\python.exe`)
- **Pytest Baseline:** 382 tests collected across `tests/unit` (357) and `tests/integration` (25)
- **Current Warnings:** 2 DeprecationWarnings (`@app.on_event("startup")` in FastAPI apps)

---

## 1. Safety & Provenance Invariants (Must Preserve)

| Invariant | Description | Enforcement Point |
|---|---|---|
| **Gate 1 Human Override** | Explicit human request always escalates, even on ML errors or low confidence | `apps/core_backend/intent/routing.py` (Gate 1) |
| **Fail-Closed ML Error** | Invalid or unavailable ML models trigger `manual_fallback`, never uncalibrated mock predictions | `apps/core_backend/intent/routing.py` (Gate 1b) |
| **Scope Protection (34 intents)** | 34 intents outside customer care taxonomy escalate immediately with `must_escalate=True` | `apps/core_backend/intent/routing.py` (Gate 2c) |
| **ACL & Role Verification** | Documents missing matching `allowed_roles` or expired/revoked `valid_to` are excluded | `apps/core_backend/retrieval/adapter.py`, `importer.py` |
| **Pure Semantic Retrieval** | Zero BM25/keyword addition; strictly pure BGE embeddings (`bge-small-en-v1.5`) | `apps/core_backend/retrieval/` |
| **Unified S1..Sn Grounding** | Policy excerpts and authorized business order facts share single `S1..Sn` citation namespace | `apps/core_backend/llm/gemini.py` |
| **Native Process Deadline** | SQLite locks and hanging workers terminated via OS process kill, zero late writes on disk | `pipeline/evaluation/system_server.py` |
| **Demo Session Isolation** | Cross-session replay or feedback rejected with 403; draft revision mismatch rejected with 409 | `apps/demo/service.py` |
| **Immutable Evaluation Lineage** | Evaluation manifests checksum input files and outputs; simulated runs cannot certify live acceptance | `pipeline/evaluation/system_metrics.py`, `assess_system.py` |

---

## 2. Test Inventory & Domain Mapping

- **Total Test Files:** 44 files
- **Total Test Cases Collected:** 382 tests
- **Target Organization:**
  - `tests/unit/intent/` & `tests/unit/` for pure classification & routing
  - `tests/unit/retrieval/` for eligibility, relevance, publication
  - `tests/unit/llm/` for grounding, citations, prompt construction
  - `tests/unit/evaluation/` for contracts, metrics, reporting, provenance
  - `tests/integration/` for multi-process server, loopback HTTP, SQLite persistence

---

## 3. Progress Tracking

- [x] **Task 1: Baseline & Inventory** (Established 382 collected tests baseline)
- [x] **Task 2: Profiles & Temp Directory** (`pytest.ini`, offline guard, `tmp/pytest`, CUDA/live markers)
- [x] **Task 3: Fixture Factories** (`tests/fixtures/factories.py`, `make_system_case`, `write_suite_fixture`)
- [x] **Task 4: Domain Organization** (Preserved file stability under Ponytail Ultra; categorized via markers & profiles)
- [x] **Task 5: Extract Mocks & Scenarios from Execution** (`mock_dependencies.py`, `oversight_scenarios.py`)
- [x] **Task 6: Metrics & Evaluation Boundaries** (Retained contract invariants without regression)
- [x] **Task 7: Lifecycle (FastAPI Lifespan) & Deprecations** (Migrated `demo` and `ml_inference` to lifespan, 0 deprecation warnings)
- [x] **Task 8: Test Cache Cleanup Script & `.gitignore`** (`scripts/clean_test_cache.ps1`, `.gitignore` allowlist)
- [x] **Task 9: Final Full Suite Verification** (384 tests passing offline, 0 failures, 1 GPU test passing under `-m cuda`)
