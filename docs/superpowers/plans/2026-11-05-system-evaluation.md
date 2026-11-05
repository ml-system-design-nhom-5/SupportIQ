# System Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bổ sung benchmark và đánh giá toàn hệ thống SupportIQ có truy vết, chấm thủ công grounding và đối chiếu tiêu chí đề bài.

**Architecture:** Giữ nguyên ML/comparison runners. Thêm system runner tái sử dụng backend qua dependency injection, tách component probes khỏi E2E; profile mock và live có bằng chứng riêng. Human assessment tạo artifact mới gắn checksum run gốc.

**Tech Stack:** Python .venv, Pydantic, pytest, FastAPI/httpx, SQLite, NumPy; dùng sklearn/torch/transformers hiện có, không thêm framework evaluation.

**Spec:** [2026-11-05-system-evaluation-design.md](../specs/2026-11-05-system-evaluation-design.md). Kế hoạch để review, chưa thực thi.

## Global Constraints

- Không sửa `docs/CHỦ ĐỀ 1.md`; semantic retrieval duy nhất; taxonomy 46 nhãn và 12 intent sản phẩm.
- CV Macro-F1 ≥ 0.85; Recall@3 ≥ 0.80; human-grounded claims ≥ 0.90; guardrail dùng số đếm 100%; live warm API p95 ≤ 12 giây.
- Mock không network, không API key, không chứng minh chất lượng live. Live không vector giả, template fallback hoặc tự đổi model.
- Profile mặc định mock; live explicit, seed=42, concurrency=1, warmup=5, latency_requests=100, max_llm_calls=200, cost cap đề xuất USD1.00 khi có pricing/cận token hợp lệ.
- Chỉ dữ liệu giả lập; SHA-256 bắt buộc, kiểm tra trước/sau; path resolve trong repo; refuse existing run; không dùng SQLite demo thật.
- Tổng deadline 30 giây/case, ML timeout3 giây, LLM timeout15 giây; timeout không bị loại khỏi báo cáo.
- Mọi lệnh test dùng `.venv\Scripts\python.exe -m pytest ... --basetemp=.pytest-system-<task> -q`. Không paid call trong test.

## Review Focus

1. KB chưa đủ phủ 12 intent: golden labels không được bịa, live report phải chỉ ra coverage thiếu (Task 1, 4).
2. Input đổi/symlink/thiếu checksum: chặn publish, không load artifact chưa xác minh (Task 1, 7).
3. ID lặp/cache/retry làm latency tốt giả hoặc escalation trùng: ID riêng mỗi attempt, test side effect (Task 3, 5, 6).
4. Budget hết, timeout, usage thiếu: không bỏ case, không tính chi phí unknown bằng zero (Task 3, 6).
5. Annotation hash cũ, ít draft, zero claims: grounding không được pass; session khác không được approve (Task 2, 5).

## File map

| Create/modify | Trách nhiệm |
| --- | --- |
| Create `pipeline/evaluation/system_contracts.py` | Typed suite/config/case/result; checksum/coverage/provenance |
| Create `pipeline/evaluation/system_execution.py` | Factory profile, probes, case/deadline execution, normalize records |
| Create `pipeline/evaluation/system_server.py` | Managed loopback demo process, handshake, deadline/restart/cleanup |
| Create `pipeline/evaluation/system_metrics.py` | Pure aggregators và gates |
| Create `pipeline/evaluation/assess_system.py` | Import annotations/product sessions, assessment version |
| Create `pipeline/evaluation/system_reporting.py` | Artifact/report/requirements matrix |
| Create `pipeline/evaluation/run_system_evaluation.py` | CLI orchestrator |
| Modify `pipeline/evaluation/run_evaluation.py` | Dispatch --mode system, giữ ml tương thích |
| Modify `pipeline/evaluation/evaluate_routing.py`, `evaluate_retrieval.py` | Strict ID/schema validation, adapters cho record mới |
| Modify `apps/core_backend/orchestration/pipeline_runner.py` | Optional clock/timing, role/as_of forwarding, route ban đầu và cuối |
| Create `pipeline/configs/system_evaluation.json`, `data/benchmarks/system/v1/` | Config, manifest, cases, coverage và snapshot pointers |
| Modify demo/service/store/static và backend khi regression chứng minh lỗi | Sửa đúng ownership/hash/eligibility/idempotency, không làm lại UI |
| Create `tests/unit/test_system_*.py`, `tests/integration/test_system_evaluation.py`, `tests/fixtures/system_evaluation/` | Fixture nhỏ explicit và test contracts/runner/report |
| Modify `pipeline/evaluation/README.md` | Hướng dẫn mock/live/annotation/user study, đọc gates |

## Task 1: Contracts và benchmark có provenance

**Files:** Create `pipeline/evaluation/system_contracts.py`, `pipeline/configs/system_evaluation.json`, `data/benchmarks/system/v1/{README.md,suite_manifest.json,cases.jsonl,coverage_matrix.csv}`, `tests/fixtures/system_evaluation/`; test `tests/unit/test_system_contracts.py`.

**Interfaces:** `load_system_inputs(repo_root: Path, suite_path: Path, config_path: Path, profile: str) -> VerifiedSystemInputs`; dataclass gồm `cases: list[SystemCase]`, `config: SystemConfig`, `source_paths: dict[str, Path]`, `input_hashes: dict[str,str]`, `as_of: datetime`, `coverage: dict`. `SystemCase` và `CaseResult` dùng đúng fields tại §5/6 spec, forbid unknown fields. `verify_input_snapshot(inputs: VerifiedSystemInputs) -> None` dùng trước/sau chạy.

- [ ] Viết test RED: duplicate IDs/invalid intent/nonfinite/missing checksum/path escape/symlink/expired gold đều raise `EvaluationError`; OOD null hợp lệ; suite draft không thể có acceptance-ready; KB thiếu vùng nghiệp vụ được báo coverage gap.
- [ ] Chạy `test_system_contracts.py` với basetemp Task1; xác nhận lỗi vì chưa có implementation.
- [ ] Implement typed schema, SHA-256, resolved containment, gold validation với snapshot/as_of/ACL; config strict và mandatory gate list. Dùng taxonomy từ `pipeline.preparation.utils`.
- [ ] Soạn 156 case theo quota spec và coverage matrix; các case chờ nguồn/duyệt giữ trạng thái draft có lý do, không ký thay giảng viên. Fixture nhỏ có taxonomy override explicit chỉ dùng tests.
- [ ] Chạy GREEN và kiểm tra mọi ID duy nhất, quotas đủ; reviewer dữ liệu người thật là bước độc lập trước acceptance.
- [ ] Commit riêng contracts/benchmark: `feat(evaluation): define versioned system benchmark contracts`.

## Task 2: Metrics nghiêm ngặt và human assessment

**Files:** Create `system_metrics.py`, `assess_system.py`; modify hai scorer hiện có; tests `test_system_metrics.py`, `test_system_assessment.py`, `test_routing_evaluation.py`, `test_retrieval_evaluation.py` trong `tests/unit/`.

**Interfaces:** `aggregate_system_metrics(cases: list[SystemCase], results: list[CaseResult]) -> dict`; `evaluate_system_gates(metrics: dict, config: SystemConfig, evidence_kind: str) -> dict`; `assess_run(run_dir: Path, annotations_path: Path, assessment_id: str, product_sessions_path: Path | None = None) -> Path`. Input run phải xác minh checksum trước đọc draft; assessment immutable.

- [ ] RED: thiếu decision vẫn nằm denominator escalation; duplicate/extra outputs raise; 20000/20001 không đạt100%; wrong source version không được hit; zero samples N/A; action trước LLM và final draft yield khác nhau.
- [ ] RED: human supported 89/100 fail,90/100 pass khi annotation đầy đủ; missing draft/annotation/zero-claims không được pass; hash cũ hoặc omitted claim review fail; `unknown` tính unsupported. Mock không pass live gates.
- [ ] RED: user study thiếu paired task/người thật thì insufficient evidence; duration âm/nonfinite bị reject; approval rate không gọi là time saved.
- [ ] Chạy RED, implement pure formulas và numerator/denominator/status; nhập annotation có reviewer và claim coverage attestation, tính paired product metrics, Wilson chỉ cho nhị thức.
- [ ] Chạy GREEN toàn bộ scorer/assessment tests; commit `feat(evaluation): add strict system metrics and human assessment`.

## Task 3: Execution adapter và tracing đúng runtime

**Files:** Create `system_execution.py`, `system_server.py`; modify `pipeline_runner.py`; test `tests/unit/test_system_execution.py`, `tests/integration/test_system_server.py`.

**Interfaces:** `build_system_dependencies(inputs: VerifiedSystemInputs, profile: str, runtime_dir: Path) -> SystemDependencies`; `execute_system_case(case: SystemCase, deps: SystemDependencies, attempt_id: str, scope: str) -> CaseResult`. `SystemDependencies` chứa runner/retrieval/demo app/budget ledger và close(); live factory pin releases; mock factory chỉ fixtures explicit. `ManagedDemoServer.start(inputs: VerifiedSystemInputs, runtime_dir: Path, ledger_path: Path) -> str` trả base URL; `.restart() -> str`, `.close() -> None`; handshake run nonce và fingerprint bắt buộc. Optional trace collector ghi stage elapsed và raw safe result, không chứa secret.

- [ ] RED: pipeline vẫn chạy clarify/escalate khi encoder unavailable; never template fallback; retrieval probe dùng gold intent, E2E dùng predicted intent; role/as_of thống nhất; DB nằm runtime_dir; missing release/incorrect readiness dừng live preflight.
- [ ] RED: một request treo bị deadline kết thúc và tạo timeout record; còn case tiếp tục; spy chứng minh mock không network và không đọc môi trường key; model/encoder load không tính vào warm requests.
- [ ] Run RED; implement factory và managed server theo spec §6.2: evaluator sở hữu demo server riêng cho run, service ML ngoài được pin; giữ server warm qua nhiều case. Deadline terminate/join server thực sự, không chỉ HTTP client; ghi side effects/provider usage unknown, restart với DB/ledger cũ, warm-up lại có budget, không retry case timeout. Mock dùng controlled fault, không spawn/download ngoài ý muốn.
- [ ] Test server lạ chiếm port bị từ chối handshake; timeout handler không chạy nền sau kill; restart giữ ledger/reservation và record timeout, re-warm/cold recovery không trộn warm p95; cleanup cuối run giải phóng SQLite trên Windows. Task6 nối ledger thật, Task3 dùng injected ledger stub rõ ràng.
- [ ] Thêm `clock` injectable và observer optional cho runner, role/as_of truyền từ execution context xuống retrieval; giữ API cũ default. Store raw route action trước khi mutate để tính coverage đúng.
- [ ] GREEN tests và regression routing/retrieval/demo/LLM; commit `feat(evaluation): execute traced system cases with isolated state`.

## Task 4: Component probes và coverage thực tế

**Files:** Modify `system_execution.py`, `system_metrics.py`; test `tests/unit/test_system_components.py`; update benchmark coverage matrix.

**Interfaces:** `run_component_probes(inputs: VerifiedSystemInputs, deps: SystemDependencies) -> list[CaseResult]`; scope component, không merge metrics thành e2e.

- [ ] RED: đúng intent nhưng sai doc, đúng doc sai version, expired/revoked/unapproved/ACL, policy conflict, encoder unavailable; không liên quan phải abstain; invalid date metadata và boundary valid_to phải không trở thành evidence hợp lệ.
- [ ] RED: unsupported34 và human_agent đúng team/queue; policy unapproved/NaN margin/manual override không quyền không được draft; question policy chung không ép order ID.
- [ ] Chạy RED; nối adapter thật với fixture clocks/metadata; nếu test lộ lỗi runtime, sửa tối thiểu file sở hữu lỗi (`retrieval/importer.py`, `adapter.py`, `intent/routing.py`) và giữ regression test. Không sửa gold theo lỗi code.
- [ ] GREEN; ghi rõ KB mặc định ba chính sách chưa chứng minh phủ mọi intent; commit `feat(evaluation): benchmark routing and semantic retrieval components`.

## Task 5: Oversight, ownership và idempotency

**Files:** Create `tests/integration/test_system_oversight.py`; modify demo `service.py`, `store.py`, `static/app.js` và orchestration `store.py` chỉ theo test; extend `system_execution.py`.

**Interfaces:** `run_oversight_scenarios(deps: SystemDependencies, runtime_dir: Path) -> list[CaseResult]`; đưa actual persistence/audit facts vào oversight results, không tự suy từ cờ response.

- [ ] RED: session B replay submission/feedback session A bị từ chối; hash stale approve409; sửa UI chưa Save không approve bản cũ; approve/edit/reject/escalate chỉ ghi feedback hợp lệ và không gửi/giao dịch.
- [ ] RED: hai runner đồng thời cùng ID và restart chỉ có một stored result/một escalation job; đếm cả side effects. Exception giữa enqueue/save không để dữ liệu nửa chừng; DB file xóa được sau close trên Windows.
- [ ] Run RED; sửa lỗi có bằng chứng tại đúng tầng. Ownership dùng authenticated session từ server; hash approval lấy bản draft đã lưu; mọi retry so fingerprint và ID, không tin client scope.
- [ ] GREEN integration và demo regression; UI hash flow kiểm tra bằng browser nếu sửa JS. Commit `fix(demo): enforce verified oversight and idempotent evaluation flows`.

## Task 6: Latency protocol và budget ledger

**Files:** Create `pipeline/evaluation/system_performance.py`; modify `system_execution.py`; tests `tests/unit/test_system_performance.py`.

**Interfaces:** `BudgetLedger(db_path: Path, config: SystemConfig)`, `.reserve(input_token_bound: int, output_token_bound: int) -> str`, `.record(attempt_id: str, usage: dict | None) -> None`, `.summary() -> dict`; `measure_system_latency(inputs: VerifiedSystemInputs, deps: SystemDependencies) -> list[CaseResult]`. SQLite `runtime/budget.sqlite3` chia sẻ parent/server qua path; BEGIN IMMEDIATE reserve, attempt ID unique, usage record idempotent. Inject wrapper Gemini generate để mọi warm-up/quality/performance/probe đi qua một ledger; không giữ transaction qua network.

- [ ] RED: lỗi/timeout vẫn trong scheduled counts; ID mới tránh cached latency; round-robin100 requests từ ≥10case đại diện; mock/fault/cold tách profile; p95 gồm failure elapsed, timeout censored được đánh dấu.
- [ ] RED: max calls tính cả warm-up/failed attempt; reserve quá budget chặn trước network; usage thiếu cost unknown, reservation không reset; không có pricing/token bound bị từ chối USD-cap; exhausted tạo not_run và partial.
- [ ] RED: hai process cùng reserve khi còn một call thì chỉ một thành công; server crash/restart giữ reservation, usage record lại không double-release; warm-up lại sau hard timeout được tính ngân sách và thiếu quota thì partial.
- [ ] Run RED; implement loopback API timer, per-stage observer, deterministic warm-up/schedule; không đo full live provider dưới thread không hủy được. Lưu p50/p95, attempts, successes, timeout count, prompt/output/thinking usage nếu có, coverage cost và source pricing.
- [ ] GREEN; commit `feat(evaluation): measure system latency and enforce run budgets`.

## Task 7: CLI, reports và publish an toàn

**Files:** Create `run_system_evaluation.py`, `system_reporting.py`; modify `run_evaluation.py`; tests `tests/unit/test_system_reporting.py`, `tests/integration/test_system_evaluation.py`.

**Interfaces:** `run_system_evaluation(suite_path: Path, config_path: Path, profile: str, run_id: str, output_root: Path) -> Path`; `write_system_report(run_dir: Path, metrics: dict, gates: dict, state: str) -> None`. CLI theo §10 spec; annotation dispatch qua `assess_run` Task2. Output manifest ghi mọi artifact bắt buộc và hash.

- [ ] RED: `--mode system --profile mock` chạy offline và ghi đầy đủ artifacts; mode ml vẫn hoạt động; run ID tồn tại/path escape bị từ chối; source config/suite/KB/prompt/release đổi giữa chạy khiến publish failed.
- [ ] RED: missing result giữ execution error; tất cả fallback không thể báo grounding pass; completed khác gate pass; partial exit2; preflight fail exit1; assessments không overwrite run gốc và version cũ.
- [ ] Run RED; implement orchestration verify→preflight→probes→quality→oversight→latency→aggregate→recheck→atomic manifest. Import ML metrics phải verify inputs/output lineage bắt buộc, thiếu thì ML not_evaluated thay vì giả số.
- [ ] GREEN mock integration, snapshot output schema và CLI exit codes; commit `feat(evaluation): publish system benchmark reports and CLI`.

## Task 8: Hướng dẫn, kiểm chứng và bàn giao acceptance

**Files:** Modify `pipeline/evaluation/README.md`, benchmark README; create annotation/product session examples chứa dữ liệu giả dưới `tests/fixtures/system_evaluation/`.

- [ ] Bổ sung setup ML service, weights BGE cache, dotenv phía server, profile mock/live, run IDs, budget/pricing, human annotation/assessment, artifact meaning và error handling. Không hardcode giá hiện hành hoặc đưa API key vào command/example.
- [ ] Chạy `.venv\Scripts\python.exe -m pytest tests/unit tests/integration --basetemp=.pytest-system-final -q`; expected không regression, không paid calls. Chạy `git diff --check`; scan artifact/log fixture không có credential. Không khẳng định số test trước khi chạy.
- [ ] Chạy mock CLI với fixture suite và xác minh offline, outputs/checksums/exit2 khi chỉ có simulated evidence; xác minh run kế tiếp không ghi đè.
- [ ] Sau review benchmark/KB bởi người thật và live explicit: chạy smoke ≤3 case với call cap3, sau đó acceptance full trong budget được cấu hình. Không chạy smoke cũ như bằng chứng đủ cho 156case hoặc latency100requests; budget không đủ thì báo partial.
- [ ] Người chấm import đầy đủ annotation; thu product study thật; mở assessment mới. Không tự đánh dấu hai bước human này hoàn tất bằng automation.
- [ ] Review báo cáo theo từng gate; những lỗi runtime phát hiện chưa sửa phải hiện fail/insufficient evidence. Commit docs/artifact phù hợp, không add DB/secret hoặc staging toàn bộ working tree.

## Tiêu chí hoàn tất và thứ tự

Thực hiện Task1→2→3→4→5→6→7→8. Các tên mới ở file map là mục tiêu triển khai, không tuyên bố file đã tồn tại. Sau Task7 có system evaluator chạy được; chỉ khi Task8 có benchmark/annotation/product evidence thật mới có thể kết luận đủ các tiêu chí đề tài. Review nguồn và kế hoạch trước khi triển khai; người thực hiện chọn native hoặc subagent theo quy trình dự án.
