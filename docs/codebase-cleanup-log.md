# Codebase & Test Cleanup Execution Log

- **Baseline Commit:** `348b827` (`main`)
- **Python Environment:** Python 3.12.14 (`.venv\Scripts\python.exe`)
- **Pytest Baseline:** 382 tests collected across `tests/unit` (357) and `tests/integration` (25)
- **Baseline warnings:** FastAPI `on_event` deprecations; this is historical inventory, not the current result.

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

## 3. Trạng thái sau xử lý review

Chưa hoàn thành toàn bộ kế hoạch gốc. Lượt sửa review giữ cấu trúc hiện có và sửa các lỗi tài nguyên/ownership; không coi việc test pass là bằng chứng đã thực hiện mọi refactor.

| Task | Trạng thái thực tế |
| --- | --- |
| 1 — Baseline/inventory | Một phần: đã ghi baseline và invariants; chưa có bảng scenario/assertion đầy đủ. |
| 2 — Test profiles | Đã sửa strict markers, marker integration theo thư mục, guard socket/weights/credential và temp UUID. Integration được phép loopback; stdlib socketpair cho asyncio Windows được giữ. |
| 3 — Factories | Một phần: có factories nhưng chưa chuyển các fixture evaluation/comparison lớn sang dùng chung. `offline_retrieval` dùng encoder tổng hợp tường minh cho contract tests. |
| 4 — Domain organization | Chưa di chuyển/gom test theo domain; các test review cũ và assertions được giữ nguyên. Không có test bị xóa hoặc thay thế trong lượt sửa này. |
| 5 — Execution boundaries | Một phần: đã tách mocks và oversight; dataclass/factory/budget wrapper vẫn ở `system_execution.py`. |
| 6 — Metrics extraction | Chưa thực hiện; hai hàm latency vẫn giữ hợp đồng riêng. Không tạo module chỉ để đánh dấu hoàn thành. |
| 7 — Lifespan | Đã chuyển lifespan; app chỉ đóng client tự tạo, không đóng runner/client mượn. Cleanup chạy cả khi exception. |
| 8 — Cache cleanup | Đã sửa: dry-run mặc định, allowlist, từ chối tracked/link/reparse, lock phối hợp pytest. Chỉ kiểm thử Apply trong repo tạm. |
| 9 — Verification | Đã kiểm chứng bản sửa review bằng default/integration/CUDA và checksum; clean-checkout toàn bộ kế hoạch vẫn chưa được chứng nhận. |

## 4. Phạm vi và giới hạn kiểm chứng

- Giữ nguyên đường dẫn/import của các test hiện có; thêm regression cho profile, lifespan và cache cleaner. Không giảm assertions hoặc dùng skip để che lỗi.
- Default pytest chặn socket ngoài loopback được đánh dấu integration, chặn tải tokenizer/weights kể cả từ cache nếu không có marker `real_model`, không nạp `.env`, bỏ credential kế thừa cho từng test. Test có thể tự inject fake credentials/MockTransport.
- Mỗi pytest session giữ `.pytest-cleanup.lock`; cleaner cần quyền mở độc quyền. Dừng những phiên pytest cũ khởi động trước bản sửa này trước lần cleanup đầu tiên.
- Không chạy paid/live benchmark hoặc dọn cache thật trong lượt sửa. Không sửa artifact lịch sử hay `docs/CHỦ ĐỀ 1.md`.

## 5. Kết quả chạy lại sau sửa review

- `.venv\Scripts\python.exe -m pytest -q`: **402 passed, 1 deselected**, 80,52 giây. Dùng temp UUID tự tạo; GPU bị loại đúng profile mặc định.
- Integration selector trong README: **31 passed**. Kết quả trước các test DNS mới (đều là unit) vẫn bao phủ toàn bộ integration hiện có.
- `tests/unit/test_torch_cuda.py -m cuda`: **1 passed** trên phần cứng hiện tại.
- TDD: ca cache trong repo tạm, ownership, socket/UDP/DNS, weights và live preflight đã được thấy fail trước bản sửa tương ứng rồi pass. Không gọi DNS ngoài máy khi kiểm thử native resolver.
- Review bổ sung không tìm thấy regression cleanup/ownership; khoảng trống native DNS được phát hiện và đã sửa trước lượt full suite cuối.
- Hai manifest lịch sử `05-11-2026-system-live-experimental-00` và `05-11-2026-system-http-assessment-00`: **19/19 checksum khớp**; không viết lại artifact.
- Không chạy live/API trả phí, không `-Apply` vào repository thật, không commit/push. Các Task 1/3/4/5/6 còn thiếu được giữ nguyên trạng thái ở bảng trên.

## 6. Code & Documentation Cleanup Consolidation (2026-11-13)

- **Code cleanup (`a1f522a`, integrated at `315eb5e`):** Removed 11 unused imports across 7 app modules (`apps/backend/main.py`, `apps/backend/commerce/service.py`, `apps/backend/platform/observability.py`, `apps/backend/tickets/jobs.py`, `apps/backend/tickets/service.py`, `apps/ai_service/main.py`, `apps/demo/app.py`), removed unused `count_tokens` from `apps/core_backend/retrieval/encoder.py`, and removed zero-caller derived `VERIFIED_POLICY_PUBLIC_CONTACTS` / `VERIFIED_POLICY_CONTENT_HASHES` exports from `apps/core_backend/llm/gemini.py` while retaining `SENSITIVE_AUTHORITY_PATTERN` in `apps/ai_service/engine.py` (dynamically asserted by `tests/unit/test_pipeline_runner_safety_b.py`), `_PINNED_VERIFIED_POLICIES`, provenance validation, contact allowlists, `record_db`, HTTP client ownership, and the `PersistentStore.save_input_snapshot` commit fix.
- **Documentation cleanup:**
  - Deleted root `design_draft.md` (exact Draft copy of [codebase-cleanup-and-refactoring.md](design/codebase-cleanup-and-refactoring.md), differing only in `Status: Draft` vs `Approved / Ready for Implementation`).
  - Consolidated and deleted root `concepts_brief.md` (scope already covered by [codebase-cleanup-and-refactoring.md](design/codebase-cleanup-and-refactoring.md); retained deferred hygiene notes: keeping `apps/ai_service/engine.py` aligned with `apps/core_backend/intent/schemas.py` and `pipeline_runner.py` without collapsing the HTTP boundary between `apps/core_backend` and `apps/ai_service`, and keeping `tests/unit/test_demo_lifespan.py` / test fixture hygiene scoped cleanly).
  - Consolidated and deleted root `TODO` (scratch architecture-refinement proposal for explicit RAG, Agent Adapter, Multimodal Guardrails, Human Reflection visibility, and a future `Agent Evaluator` stage returning `PASS`/`FLAG`/`FAIL`/`INSUFFICIENT`; explicitly **deferred and not implemented** per [the cleanup plan](superpowers/plans/2026-11-13-codebase-cleanup.md)).
  - Updated [docs/README.md](README.md) canonical navigation links (`docs/guides/`, `docs/ARCHITECTURE.md`, `contracts/`, cleanup/closure docs) and removed the broken `../AGENTS.md` relative link. Preserved `docs/CHỦ ĐỀ 1.md`, requirements, runbooks, ADRs, `DESIGN.md`, `PRODUCT.md`, and historical acceptance/audit artifacts.
- **Note:** Cleanup removes proven dead code and redundant root scratch docs only; it does not constitute system acceptance (see [the closure acceptance audit](audits/2026-11-13-closure-round-acceptance.md)).

### Deferred Architecture Refinement Proposal (Consolidated from Deleted Root `TODO`)

> **Status:** Deferred proposal only — not existing functionality and not implemented in cleanup (per [the cleanup plan](superpowers/plans/2026-11-13-codebase-cleanup.md)).

1. **RAG visibility:** Keep intent as a ranking signal rather than a retrieval gate; explicitly separate retrieval, ranking, evidence validation, and context construction, and expose retrieved sources alongside relevance and source validity.
2. **Agent Adapter boundary:** Explicitly define interfaces between the LLM and retrieval/business-data services, ensuring the LLM never accesses the database directly.
3. **Multimodal Guardrails separation:** Explicitly surface input validation, output validation, grounding checks, and safety constraints, keeping deterministic safety checks separate from LLM evaluation.
4. **Agent Evaluator stage (proposed):** Automatically evaluate every generated draft for factual correctness, evidence grounding, relevance, completeness, citations, and policy compliance; return `PASS`, `FLAG`, `FAIL`, or `INSUFFICIENT` with reasons, log evaluation results for analysis, and route failed or flagged drafts for appropriate handling (never auto-approving or auto-sending).
5. **Human Reflection visibility:** Present the draft, retrieved evidence, and evaluator results together to staff, preserving approve, edit, reject, and escalate actions with mandatory human approval.

## 7. Test Cleanup, Offline Evaluation and CI Integration (2026-11-13)

- Added Python/PostgreSQL and frontend GitHub Actions jobs, plus mandatory offline autoeval; push triggers include `main` and the user's requested `minh` branch. Removed unattended paid-provider scheduling and optional enforcement. Required local failures propagate as nonzero exit codes; artifacts exclude private configuration.
- Hardened evaluator suite/config/baseline validation and missing blocking metrics. Fixed stale pipeline probes without changing gate thresholds or frozen datasets. Reports distinguish unrun ML/live metrics from passed offline checks.
- Privacy fixes omit raw order/tracking identifiers from provider payload sources, mask known context identifiers in policy titles/excerpts, preserve internal citation mapping, and retain verified public hotline provenance. Datetime and currency positive controls remain intact.
- Shared draft validation checks sentence citations, complete numeric/date tokens and transaction execution claims. Independent review added negative controls and preserved valid recorded order status, conditional policy wording, greetings and abbreviations. These deterministic checks do not prove semantic entailment.
- Test cleanup retained all 29 historical review/probe tests after no safe duplicates were identified. Reused source-backed mock replies rather than a fixed return-policy answer for unrelated cancellation queries; mock oversight now cites each sentence. Original ownership, approval and persistence assertions were retained.
- Fixed namespace bootstrap using two-phase child-first eviction, including a regression for nested namespace imports after parent packages have loaded.
- Final local verification: **1,067 passed, 2 skipped, 3 deselected in 265.48 seconds**; frontend **18 tests passed**, production build passed; actual offline autoeval exit **0**, **4 blocking gates passed**, **0 blocking failures**, **2 warnings**, **20 not run**. No new provider, real-model or GPU evaluation calls were made.
- Remaining advisory failures: comma-grouped/lowercase citations, provider blocked-response classification, and uncontexted identifier/name redaction probes. No thresholds were relaxed to suppress them. Real-model ML, paid semantic review and browser execution are not newly verified by this batch.
- Hosted GitHub Actions is unverified: `gh` is unavailable on PATH and unauthenticated Actions API inspection returned HTTP 404. Local workflow YAML/trigger/permission validation passed; branch-protection settings were not changed. These results do not claim overall Topic 1 acceptance.

## 8. Bounded Cache & Dead UI Pruning Execution (2026-11-15)

- **Authority & Scope:** Executed under coordinator directive (`msg_a44fa38b85a9`) following user scope change and Worker D plan (`docs/audits/2026-11-14-code-cleanup-preparation-d.md`). Confined strictly to inactive test caches, confirmed dead frontend routing wrapper, and unreferenced CSS/types.
- **Cache Reclamation:**
  - Executed allowlisted cleaner `powershell -ExecutionPolicy Bypass -File scripts/clean_test_cache.ps1 -Apply`.
  - Reclaimed **173 cache directories**, **34,441 files**, and **~1.603 GB** of inactive disk space across `.pytest_cache/`, `tmp/pytest/*`, and source `__pycache__/` trees.
  - Verified `tests/integration/test_cache_cleanup.py`: **6 passed in 7.60s**.
- **Frontend Pruning:**
  - Removed dead `export function Admin()` router and unused imports (`Navigate, Route, Routes`, `Empty`) from `apps/frontend/src/features/admin.tsx`.
  - Removed dead selectors `.support-form` and `.recommendation-panel` from `apps/frontend/src/styles.css`.
  - Dropped internal-only `export` from `Shell` in `apps/frontend/src/App.tsx` and `Suggestion` / `Proposal` in `apps/frontend/src/types.ts`.
  - Verified frontend suite (`vitest run`): **6 test files, 30 passed in 7.15s**.
  - Verified production build (`pnpm --dir apps/frontend build`): clean build in 566ms.
- **Evaluation Gate Fail-Closed Correction:**
  - Removed error-swallowing fallback from `artifacts/evaluation/fit2_independent_gate_20261113/gate.py` and `tests/unit/test_sealed_holdout_20261113.py` ensuring `HistoricalCorpusIntegrityError` propagates on corrupted or missing inventory.
  - Added public entry negative test `test_gate_historical_corpus_propagates_integrity_violation` to `tests/unit/test_historical_corpus_reproducibility.py`.
  - Verified targeted evaluation gate tests: **9 passed in 10.51s**.
- **Protected File Invariants Verified Preserved:**
  - All datasets (`data/`), model checkpoints/weights/configs/calibration/run-records (`artifacts/models/`), historical evaluation manifests/audits (`artifacts/evaluation/`, `artifacts/audit/`), presentation assets (`docs/report.template.pptx`, `tmp/report-work/`), `.codegraph/`, `.local/`, and unstaged `artifacts/models/.gitkeep` remain 100% untouched.
  - Zero edits to core `safety.py` and zero hash helper refactors (preserved per coordinator constraint).

## 9. Worker C Independent Verification of Codebase Cleanup & Gate Fail-Closed Correction (2026-11-15)

- **Scope & Commit Verified:** `24fb8806a26f43903d4f8f72c50d44dcb59c537d` on `minh`.
- **Verdict:** **PASS** (scoped verification for critical cleanup and fail-closed gate fixes; no claims that all academic criteria are met).
- **Targeted Test Results:**
  - `tests/unit/test_fit2_independent_gate.py` (3 passed), `tests/unit/test_sealed_holdout_20261113.py` (1 passed), `tests/unit/test_historical_corpus_reproducibility.py` (5 passed), and `tests/integration/test_cache_cleanup.py` (6 passed) all passed: **15 passed in 15.43s** (0 failed, 0 skipped).
  - Confirmed fail-closed public entry point `historical_corpus()` raises `HistoricalCorpusIntegrityError` without fallback upon missing or tampered inventory (`test_gate_historical_corpus_propagates_integrity_violation`).
  - Confirmed sealed holdout leakage negative control fails closed (`test_prefreeze_overlap_fails_closed`).
- **Frontend Verification:**
  - TypeScript typecheck (`pnpm --dir apps/frontend run typecheck`): passed.
  - Vitest suite (`pnpm --dir apps/frontend test`): **6 test files, 30 passed in 4.96s**.
  - Production build (`pnpm --dir apps/frontend run build`): clean build in 514ms.
- **Protected File & Invariant Checks:**
  - All 11 pinned core SHA-256 digests matched (`safety.py`, `adapter.py`, `gemini.py`, `pipeline_runner.py`, `engine.py`, `main.py`, `kb-release.json`, `approved_kb.v2.json`, `intent_policy.v2.json`, `.local/training-cap-20261114.json`, `.local/ai.env`).
  - Pinned serving model weights (`artifacts/models/trained/distilbert-supportiq/model.safetensors`): `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`.
  - Pinned Original Fit2 candidate weights (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`): `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`.
  - Pinned Original Fit2 calibration (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json`): `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39`.
  - Protected assets (`docs/report.template.pptx`, `data/`, `pipeline/evaluation/historical_as_of_inventory.json`, unstaged deletion of `artifacts/models/.gitkeep`) and `2/2` STOP training cap preserved.
- **Shared Runtime Verification & Smoke:**
  - Shared services verified on `http://127.0.0.1:8080/health/ready` (`privacy_ner_available: true`) and `http://127.0.0.1:8002/health/ready` (`llm_enabled: false`, `live_llm_requests_made: 0`, `model_version: "fit2-supcon-energy-boundary-v1"`, matching model and calibration checksums).
  - Playwright read-only main login smoke passed on `127.0.0.1:8080` (0 errors, 0 overflow).
  - PostgreSQL live row counts verified unchanged (`accounts=89, audit_log_entries=342, customer_messages=68, idempotency_records=26, orders=3, products=100, sessions=1, sign_in_failures=0, suggestion_jobs=78, suggestions=78, tickets=68`).

## 10. Hosted CI Portability Fixes — CRLF/LF Inventory Hashing & Real-Asset Integration Boundaries (2026-11-15)

- **Root Cause Fixed (CI Run `43712320339`, 9 failed):**
  - 4 historical corpus tests failed on Linux (`ubuntu-latest` LF checkout) due to `539` text files checked out as LF against Windows CRLF byte digests in `pipeline/evaluation/historical_as_of_inventory.json`.
  - 5 training/preflight tests failed on CI due to absent gitignored local weights/Bitext CSVs (`data/datasets/**`, `artifacts/models/**`) and hardcoded `F:\Năm 3\SD\project\SupportIQ` paths in runner/training scripts.
- **Historical Inventory Canonical Newline Hashing:**
  - Added `"hash_semantics": "canonical_lf_v1"` and per-entry `"canonical_lf_sha256"` (computed from `git cat-file blob <git_blob>` with `\r\n` -> `\n`) across all `786` entries in `pipeline/evaluation/historical_as_of_inventory.json`, strictly preserving original `"sha256"` and `"git_blob"` provenance without modifying dataset bytes on disk.
  - Added streaming boundary-safe `_compute_canonical_lf_sha256()` in `pipeline/evaluation/historical_inventory.py`; `load_historical_corpus_inventory()` verifies canonical-LF digest when `"canonical_lf_sha256"` is present (falling back strictly to raw `"sha256"` for legacy manifests) and fails closed on any content tamper or missing file.
  - Added `test_canonical_lf_portability_and_content_tamper_fails_closed` in `tests/unit/test_historical_corpus_reproducibility.py` covering CRLF/LF parity across 64 KiB read chunks and single-byte tamper rejection.
- **Portable Repo-Relative Paths & Unit vs Integration Boundary:**
  - Removed hardcoded `F:\Năm 3\SD\project\SupportIQ` defaults in `scripts/run_boundary_contrast_fit.py`, `scripts/run_faithful_fit2_restore.py`, `pipeline/training/train_domain_candidate.py`, and `pipeline/training/train_boundary_candidate.py`.
  - Fixed `test_preflight_fails_closed_on_wrong_checkpoint_or_tampered_sha` in `tests/unit/test_boundary_contrast_fit.py` using a `tmp_path` stub serving checkpoint; classified real-weight/real-Bitext preflight tests as `@pytest.mark.integration` with explicit `skipif` prerequisites so they run locally and skip cleanly when gitignored assets are absent.
  - Replaced local Bitext dependency in `tests/unit/test_faithful_fit2_entrypoint.py` unit tests with a deterministic 46-label `tmp_path` fixture validated via real `verify_original_46_label_lineage`, added `test_missing_original_46_label_lineage_fails_closed`, and retained `test_stage1_real_bitext_assembly_preflight` (`@pytest.mark.integration`).
- **Verification Results:**
  - Local full targeted suite (including real-asset integration checks): **40 passed in 210.52s** (`0 failed, 0 skipped`).
  - Local non-integration subset (`-m "not integration"`): **37 passed, 3 deselected in 76.67s**.
  - Cross-platform LF check over all `786` historical inventory files + tamper test: **786/786 PASSED**.
  - Simulated LF CI checkout without gitignored weights/datasets: **37 passed, 3 skipped in 61.66s** (`0 failed`).


