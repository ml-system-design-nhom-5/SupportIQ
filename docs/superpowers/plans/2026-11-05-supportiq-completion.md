# SupportIQ Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện chất lượng và bằng chứng nghiệm thu SupportIQ sau benchmark thực tế, bảo đảm chuyển cấp, retrieval, grounding, human oversight và hiệu năng được đánh giá đúng.

**Architecture:** Giữ `supportiq_distilbert`, BGE semantic retrieval và Google AI Studio; sửa tại các thành phần hiện có. Đóng phiên bản benchmark/KB/policy/prompt, chỉnh trên dev và nghiệm thu trên acceptance mới. Dùng chung evidence có kiểu cho chính sách và dữ liệu nghiệp vụ, đo toàn luồng qua HTTP demo thật.

**Tech Stack:** Python .venv, FastAPI/httpx, SQLite, Pydantic, NumPy, torch/transformers, pytest; không thêm nền tảng evaluation hoặc dashboard mới.

**Spec:** [System evaluation design](../specs/2026-11-05-system-evaluation-design.md), [Routing design](../specs/2026-11-04-routing-design.md), [Retrieval design](../specs/2026-11-04-retrieval-design.md), [đề bài](../../CHỦ%20ĐỀ%201.md).

**Evidence:** [Báo cáo HTTP và grounding AI](../../../artifacts/evaluation/05-11-2026-system-http-assessment-00/report.md). Đây là kế hoạch để review, chưa triển khai; các lựa chọn mở rộng bên dưới là đề xuất của tác giả, chưa phải dữ liệu/chính sách được người dùng phê duyệt.

## Global Constraints

- Không sửa `docs/CHỦ ĐỀ 1.md`; không sửa/ghi đè artifact hoặc điểm benchmark đã phát hành.
- ML vẫn phân loại 46 intent; 12 intent sản phẩm bao gồm `human_agent` luôn hướng tới người xử lý, 34 intent còn lại có chuyển cấp phù hợp.
- Retrieval chỉ tìm kiếm ngữ nghĩa; giữ BGE-small-en-v1.5 làm mặc định, tiếng Anh; không thêm BM25/keyword search.
- CV Macro-F1 ≥ 0.85; Recall@3 ≥ 0.80; human-supported factual/policy claims ≥ 0.90; must-escalate và human approval đúng 100% trên bộ được duyệt; HTTP p95 ≤ 12 giây.
- Không hạ ngưỡng nghiệm thu, bỏ case lỗi, luôn từ chối hoặc giảm độ phủ để làm đẹp metric. N/A/thiếu bằng chứng không được pass.
- Không tự ký duyệt KB, policy, benchmark hoặc grounding; AI sơ bộ và human assessment được tách riêng.
- Không tự gửi câu trả lời, phê duyệt hoàn tiền hoặc thực hiện giao dịch. Chỉ dữ liệu giả lập, ACL và ownership phải được thực thi.
- Không retrain/chọn model hoặc threshold/prompt trên acceptance. Kết quả v1 đã xem được dùng chẩn đoán/dev, không còn là bằng chứng đánh giá mù cho thay đổi mới.
- Test tự động không gọi API trả phí; live benchmark chạy explicit, ledger dùng chung, mặc định tối đa 200 outbound LLM attempts và 1 USD dự phòng/campaign. Hết budget phải báo partial, không tự tăng hạn mức.
- Thay đổi bằng TDD; Python dùng `.venv\Scripts\python.exe`; pytest temp nằm trong workspace. Không staging toàn bộ working tree vì có thay đổi ngoài phạm vi.

## Hiện trạng và đích hoàn thiện

| Hạng mục | Bằng chứng hiện tại | Điều kiện hoàn thiện |
| --- | --- | --- |
| Routing guardrail | 31/63; 21 clarify, 10 manual_fallback, 1 timeout thiếu decision trong nhóm sai | Hợp đồng/gold được duyệt; 100% must-escalate đúng, có job/audit |
| Retrieval | Recall@3 E2E 61,76%; false evidence 29,51%; KB runtime 3 policy ngắn | ≥80% trên acceptance có nguồn đáp ứng, nguồn sai ACL/hết hạn/revoked không xuất hiện |
| Draft coverage | 6/34 case kỳ vọng có draft; tổng 13 draft | Toàn bộ case thực sự answerable được duyệt có kết quả; lỗi provider/thiếu output không bị giấu |
| Grounding | AI sơ bộ 15/17 claim (88,24%), hai unknown về đơn hàng | Có business evidence truy vết, người chấm duyệt đầy đủ; ≥90% và đủ phạm vi |
| Relevance | Có draft nói hủy đơn khi được hỏi điều kiện hoàn tiền | Không trả lời bằng policy khác chủ đề; thiếu thông tin thì clarify/escalate đúng hợp đồng |
| HTTP latency | p95 chung 10,68s; nhánh LLM/draft 15,31s | Giữ p95 chung ≤12s, báo riêng nhánh LLM; đề xuất cải thiện nhánh LLM ≤12s trên dev mà không giảm draft coverage |
| Oversight | 3/4; feedback audit không ghi được trong một scenario | Phân biệt thiếu draft và lỗi audit; kiểm chứng ownership, hash, các action và persistence thực tế |
| Bằng chứng ML/product | Chưa import CV vào report hệ thống; chưa có study người dùng thật | CV đúng model/release; dữ liệu paired manual/copilot và feedback người thật |

Không cam kết trước mọi ngưỡng sẽ đạt: nếu dữ liệu/phần cứng/provider chưa đáp ứng, báo đúng fail/insufficient_evidence và nguyên nhân.

## Review Focus

1. Gold answerable không khớp KB, generic policy khác truy vấn, source version sai: không sửa nhãn theo output để tăng điểm — Task 1/3/4.
2. Yêu cầu người thật hoặc intent ngoài phạm vi bị confidence gate chuyển clarify; ML/fault mất response: phải có kết quả an toàn đúng hợp đồng và trace riêng — Task 2.
3. Dữ liệu đơn hàng có trong prompt nhưng không có citation/snapshot; thiếu draft hoặc AI annotation bị tính như human: không chứng nhận grounding — Task 5.
4. Tác vụ native tiếp tục sau timeout, request cache hoặc HTTP lỗi nhanh tạo p95 đẹp: worker phải dừng thực sự, đo mẫu mới, lỗi không được pass — Task 2/6.
5. Feedback bị từ chối vì không có draft nhưng bị coi như kiểm tra security thành công; artifact CV thuộc model khác; budget bị reset giữa workers: phải kiểm tra dữ liệu/audit/lineage thật — Task 7/8.

## File map

| Files | Trách nhiệm |
| --- | --- |
| `data/benchmarks/system/v2/dev/`, `v2/acceptance/` (create) | Hai bộ có nguồn gốc/review/quota độc lập, lineage tới v1 nếu kế thừa |
| `pipeline/evaluation/system_contracts.py`, `system_metrics.py` | Validation gold/coverage, expected actions/team/reason và các gate |
| `apps/core_backend/intent/routing.py`, `schemas.py`, `config/policies/intent_policy.v2.json` | Thứ tự safety gates, typed route/context; policy thay đổi phải là version mới |
| `apps/core_backend/orchestration/pipeline_runner.py`, `store.py` | Fault outcomes, evidence snapshot, timing và escalation bền vững |
| `data/knowledge/staging/policies.v2.json`, `approved_kb.v2.json` (create) | Nguồn chờ duyệt và bản phát hành thực sự được duyệt |
| `apps/core_backend/retrieval/{importer,adapter,index}.py` | Metadata thật, intent applicability, semantic relevance, đủ chunk trong budget |
| `apps/core_backend/llm/gemini.py` | Payload evidence có kiểu, citation cho policy/order facts, prompt đúng yêu cầu, client lifecycle |
| `pipeline/evaluation/{assess_system,system_execution,system_server,system_performance,complete_system_report,system_reporting,run_system_evaluation}.py` | Worker/deadline, quality vs latency, human assessment, import ML, lineage/report |
| `apps/core_backend/intent/client.py`, `apps/demo/{app,service,store}.py` | HTTP pool, session, feedback và audit; giữ UI hiện có |
| `tests/unit/test_completion_*.py`, `tests/integration/test_completion_*.py` (create) | Regression từ nguyên nhân đã xác nhận, không dựa output cụ thể của Gemini |
| `docs/system-evaluation-report.md`, `pipeline/evaluation/README.md` | Hướng dẫn chạy, diễn giải kết quả và bàn giao human review |

## Task 1: Chốt hợp đồng đánh giá và tách dev/acceptance

**Files:** Create `data/benchmarks/system/v2/{dev,acceptance}/README.md`, manifest/cases/coverage; modify `system_contracts.py`, `system_metrics.py`; test `tests/unit/test_completion_contracts.py`.

**Interfaces:** Giữ `load_system_inputs(...) -> VerifiedSystemInputs`; bổ sung `validate_expected_outcomes(cases: list[SystemCase], kb_snapshot: list[dict]) -> dict`. Kết quả chứa `contradictions`, `missing_evidence`, `coverage_by_intent`; lỗi contract raise `EvaluationError`.

- [ ] RED: answerable nhưng nguồn thiếu capability được khai báo, thiếu source/version, expected actions mâu thuẫn must-escalate/must-not-draft, gold thiếu quyền/hiệu lực, thiếu reviewer/quotas; fixture phải bị reject hoặc giữ draft có coverage gap. Validator kiểm tra hợp đồng/metadata; mức đúng nghĩa giữa câu hỏi và gold do người duyệt xác nhận, không giả định code có oracle ngữ nghĩa.
- [ ] Chạy `.venv\Scripts\python.exe -m pytest tests/unit/test_completion_contracts.py --basetemp=.pytest-completion-01 -q`; xác nhận fail do validation còn thiếu.
- [ ] Lập `failure_inventory.jsonl` từ v1: case_id, expected/actual, initial/final action, model score/margin, reason, fault, KB availability; phân biệt lỗi model, gate, fixture/gold và provider. V1 là evidence chẩn đoán, không chỉnh sửa.
- [ ] Soạn dev v2 dựa lỗi v1 và acceptance v2 bằng câu diễn đạt mới do người duyệt xác nhận. Giữ coverage 46 intent/12 scope; đề xuất acceptance 156 case theo quotas spec, không tái dùng case đã tuning làm test mù.
- [ ] Quy định riêng `must_escalate` (action escalation + assignment) và `safe_manual_handling` (có thể fallback). Chỉ đổi gold khi người duyệt xác nhận hợp đồng cho phép, ghi rationale/version; không biến 10 fallback sai thành đúng chỉ để tăng điểm.
- [ ] Implement strict contracts: reviewer/status hợp lệ, quotas, ID, dates, finite scores, actions/team/reasons, đầy đủ output. Tính outcome success riêng, không dùng `execution_status=ok` thay quality success.
- [ ] GREEN tests; lưu bảng câu hỏi nghiệp vụ cần người duyệt, để suite acceptance `draft` cho tới khi xác nhận. Commit `feat(evaluation): freeze completion contracts and dev acceptance suites`.

**Gate:** Có phân loại nguyên nhân và gold đáng tin cậy; chưa điều chỉnh ngưỡng/prompt trước bước này.

## Task 2: Sửa routing, fault handling và hard deadline

**Files:** Modify routing/schemas, `pipeline_runner.py`, `system_execution.py`, `system_server.py`, store; test `test_completion_routing.py`, `tests/integration/test_completion_deadline.py`.

**Interfaces:** Giữ `decide_route(prediction, context, policy) -> RouteDecision`; context bổ sung chỉ tín hiệu được server xác thực. `execute_system_case(...) -> CaseResult` không được dùng `PyThreadState_SetAsyncExc`; worker process có `terminate/join/restart` với ledger/DB không reset.

- [ ] RED: explicit human request + low confidence vẫn escalate; `human_agent` hoặc outside-scope được nhận diện không được trượt sang draft; team không chắc thì general queue có lý do, không bịa nhãn chắc chắn.
- [ ] RED: uncertainty của 11 intent hỗ trợ vẫn được clarify khi hợp đồng cho phép; yêu cầu chung không ép order ID; personal lookup thiếu slot chỉ hỏi đúng thông tin cần thiết. Không escalate toàn bộ traffic để đạt safety.
- [ ] RED: ML/encoder/LLM timeout/failure được inject tại dependency thật; case phải đi qua orchestration, có safe action/reason; không trả ngay một timeout giả thay việc kiểm tra fallback.
- [ ] RED native SQLite probe: khóa DB, timeout request, mở khóa sau timeout; không có bản ghi muộn, process cũ đã chết, retry không enqueue trùng. Mock fixture sleep đơn thuần chưa đủ.
- [ ] Chạy test RED; chỉnh thứ tự gate theo hợp đồng Task1, không ưu tiên nhãn ML sai hơn tín hiệu human request đã xác thực. Giữ invalid output fail-closed và quyền override.
- [ ] Cô lập execution có side effect trong process; kill/join cây worker khi deadline, giữ reservation, restart có handshake và re-warm có ngân sách. Tác vụ provider phía Google có thể vẫn hoàn tất; báo usage unknown, không tự retry.
- [ ] GREEN unit/integration; kiểm tra số job/audit sau restart/concurrency. Commit `fix(routing): enforce escalation contracts and process deadlines`.

**Gate:** Oracle routing tests đúng hợp đồng; E2E vẫn báo riêng lỗi classifier, không khẳng định đã đạt 100% chỉ từ unit tests.

## Task 3: Hoàn thiện KB và dữ liệu nghiệp vụ có truy vết

**Files:** Create staging/approved KB v2 và coverage matrix; modify importer/adapter, commerce adapter khi cần; test `tests/unit/test_completion_knowledge.py`.

**Interfaces:** Policy metadata đề xuất thêm `supported_intents: list[str]`, `answer_capabilities: list[str]`; đây là applicability metadata, không là keyword search. `publish_approved_kb(staging_path: Path, output_path: Path) -> Path` chỉ nhận record được người thật duyệt, refuse existing version.

- [ ] RED: thiếu approval, date sai, ACL rỗng/sai, conflicting rules, placeholder content hash, source không đủ capability phải quarantine/reject; không tự điền reviewer/date.
- [ ] Kiểm kê `data/knowledge/policies.json` và mock orders; map từng intent tới policy, FAQ hướng dẫn hoặc business lookup. `human_agent` cần escalation, không ép có policy để drafting.
- [ ] Bổ sung staging cho tracking/delivery/shipping, cancellation, return initiation, refund eligibility/request/status và payment issues. Thiếu nội dung được giảng viên/đơn vị dữ liệu xác nhận thì giữ coverage gap, không tự đặt giá/phí/thời hạn nghiệp vụ.
- [ ] Hash thật từ nội dung chuẩn hóa; lưu nguồn, document/version, hiệu lực, ACL, rule assertions và capability. Giữ business data snapshot/hash riêng với policy.
- [ ] Người phụ trách duyệt nội dung và metadata; sau đó publish `approved_kb.v2.json`, đóng checksum và coverage matrix. Cần dùng cùng bản được duyệt khi đánh giá chung giữa các nhóm.
- [ ] GREEN importer/eligibility tests; mọi case dev answerable có evidence thật. Commit `feat(knowledge): publish reviewed coverage for supported workflows` sau khi thực sự được duyệt.

**Gate người làm:** KB approval là dependency bắt buộc trước công bố coverage đủ; code và staging có thể hoàn thành trước.

## Task 4: Cải thiện semantic retrieval và kiểm tra mức liên quan

**Files:** Modify retrieval adapter/index/importer, config retrieval version mới; tests `test_completion_retrieval.py`; cập nhật dev fixtures.

**Interfaces:** Giữ `RetrievalAdapter.retrieve(query, intent, role, current_time) -> dict`; evidence trả đủ doc/version, excerpt/chunk IDs, score, source type, content hash và reason. Search vẫn cosine trên embeddings BGE.

- [ ] RED: hỏi refund eligibility không nhận cancellation policy làm evidence đủ; hỏi refund status không được dùng timeline chung như trạng thái đơn; hỏi cách khởi tạo return phải cần capability hướng dẫn tương ứng.
- [ ] RED: đúng doc sai version, expired/revoked/ACL/conflict không được trả; token budget có ngoại lệ cuối không được cắt mất; nhóm chunk không trộn version của cùng document.
- [ ] Chạy RED; prefilter eligibility + applicability metadata, semantic rank sau đó. Evidence gate kiểm tra capability cần cho câu hỏi; intent không chắc không được mở rộng quyền hoặc tự coi đủ evidence.
- [ ] Chỉ trên dev, so sánh top-k/chunk/context budget/threshold; lưu bảng cấu hình và Recall@3, Hit@3, false evidence, eligible answer coverage. Không tăng Recall bằng cách trả mọi document hoặc hạ threshold vô điều kiện.
- [ ] Chốt config trên dev rồi khóa; không đụng acceptance. Nếu vẫn thiếu Recall, xử lý coverage/chunking trước khi đề xuất đổi embedding model.
- [ ] GREEN tests, chạy real-encoder dev probe có version/checksum; commit `fix(retrieval): require semantically relevant answer evidence`.

**Gate:** Dev Recall@3 ≥0.80 trên case có evidence được duyệt; zero protected-source violations. False evidence và coverage luôn báo kèm, không tự đặt ngưỡng nghiệm thu mới ngoài đề bài.

## Task 5: Grounding cho policy và order facts, trả lời đúng yêu cầu

**Files:** Modify `gemini.py`, runner, evidence schemas, assessment/export; create `test_completion_grounding.py`, `tests/integration/test_completion_evidence.py`.

**Interfaces:** `build_grounded_sources(policy_evidence: list[dict], authorized_facts: dict | None, provenance: dict) -> list[dict]`; source có `source_id`, `source_type` (`policy`/`order_facts`), document_id, version, excerpt và SHA-256. Dùng chung ID `S1..Sn` cho cả hai kiểu; không đưa facts không có nguồn qua side channel.

- [ ] RED: phát biểu trạng thái đơn chỉ được hỗ trợ bởi order evidence đã phân quyền; policy chung không chứng minh đơn đã bàn giao hoặc không thể hủy. Mỗi factual claim cần citation đúng loại evidence.
- [ ] RED: refund eligibility query không được trả cancellation-only draft; missing policy/fields → clarify hoặc safe fallback đúng contract, không kết luận chắc chắn; không tuyên bố đã refund/cancel.
- [ ] RED: export giữ đúng sanitized payload/snapshot đã gửi LLM, source version/hash, draft hash; không lộ email/phone/API key. Business facts chỉ chứa allowlist cần thiết, không dump toàn order.
- [ ] Chạy RED; hợp nhất evidence có kiểu, lưu snapshot tối thiểu trước egress, cập nhật prompt/schema/citation validator và provenance trong result/artifact. Prompt mới có version; không tự đổi provider/model.
- [ ] Thêm scoring relevance riêng `fully_answers`/`partial`/`off_topic`; giữ claim support khác relevance và citation validity. Duplicate/unknown/claim thiếu review không làm tăng điểm.
- [ ] Trên dev, xuất toàn bộ claim của mọi draft và danh sách expected draft bị thiếu; dùng AI preassessment có `reviewer_type=ai`, người dùng duyệt sau như đã chọn. Không tự ký thay người dùng.
- [ ] GREEN tests và review evidence pack; commit `feat(grounding): cite auditable policy and authorized business facts`.

**Gate:** Đủ lineage để người chấm giải quyết hai unknown; chưa có human review thì vẫn pending. Mục tiêu ≥90% không được chứng nhận từ AI score.

## Task 6: Độ trễ nhánh LLM và độ tin cậy provider

**Files:** Modify `intent/client.py`, `gemini.py`, demo lifespan, runner timers, HTTP benchmark; tests `test_completion_http_clients.py`, `test_completion_performance.py`.

**Interfaces:** Inject/reuse `httpx.Client` theo lifespan; explicit `close()`. Request timing lưu ML/connect/retrieval/LLM/persist/API totals cả khi exception. `summarize_http_results(...)` báo all/LLM-attempt/draft/no-LLM, lỗi và coverage.

- [ ] RED: nhiều request dùng lại pool, đóng đúng khi shutdown; timeout/error không mất timer; API key chỉ đúng endpoint; stale connection được trả typed error, không tự retry tạo draft trùng.
- [ ] RED: nhanh vì toàn HTTP lỗi hoặc toàn fallback không thể công bố thành công tổng thể; UUID mới mỗi mẫu, đủ100 mẫu, không loại timeout. Native deadline theo Task2.
- [ ] Profile dev theo stage trước khi thay code; kiểm tra ML client URL loopback, DNS/connect và việc tạo client mới từng call. Đối chiếu fresh vs pooled trên cùng máy, không quy toàn bộ độ trễ cho GPU/model.
- [ ] Tái sử dụng connection/tokenizer/index; giảm evidence/prompt/token output có kiểm chứng giữ ngoại lệ và chất lượng. Giữ model hiện tại trước; chỉ thay model nếu có quyết định/bằng chứng riêng.
- [ ] Đề xuất thử trên dev ML connect≤1s/read≤3s, LLM connect≤2s/read≤8s, đo deadline toàn request và fallback. Các số này là candidate, không tự coi timeout ngắn hơn là cải thiện chất lượng.
- [ ] Chọn cấu hình với draft coverage/relevance/grounding không giảm; giá trị timeout chính thức dựa profiling. Provider vẫn chậm thì báo fail/partial, không che bằng template hoặc đổi model tự động.
- [ ] GREEN tests; paired HTTP dev runs cùng branch mix và điều kiện, không so hai thời điểm để suy overhead. Commit `perf(http): reuse clients and bound LLM request latency`.

**Gate:** p95 chung ≤12s, nhánh LLM được báo riêng và hướng tới≤12s; không suy giảm khả năng tạo draft đúng. Nhánh mục tiêu phụ chưa đạt phải hiển thị rõ.

## Task 7: Human oversight, ML evidence và báo cáo trung thực

**Files:** Modify demo service/store/app/static nếu test chứng minh cần, evaluation metrics/contracts/reporting/assess; tests `tests/integration/test_completion_oversight.py`, `tests/unit/test_completion_reporting.py`.

**Interfaces:** `import_verified_ml_metrics(manifest_path: Path, expected_model_release: dict) -> dict`; `evaluate_oversight(records: list[CaseResult], expected_ids: set[str]) -> dict`. Giữ human assessment immutable và schema actor type.

- [ ] RED: thiếu draft thì báo prerequisite not met; không dùng409 do no-draft làm bằng chứng stale-hash/ownership pass. Có draft hợp lệ thì approve/edit/reject/escalate tạo đúng audit và hash được duyệt.
- [ ] RED: replay/feedback khác session bị từ chối, sửa chưa save không approve bản cũ, restart/concurrency không trùng escalation; xác minh DB facts và transaction side effects, không chỉ response flags.
- [ ] RED: CV của baseline khác/release khác, thiếu checksum hoặc historical manifest bị sửa bị reject; không gán CV winner SVM làm CV của `supportiq_distilbert`.
- [ ] Chạy RED; sửa nguyên nhân scenario audit không ghi được, tách deterministic integration evidence và live provider availability. Import CV đúng model/protocol/release từ artifact đã xác minh; thiếu lineage giữ not_evaluated.
- [ ] Chuẩn hóa usage theo field thực của Gemini, thinking/cache khi có; pricing snapshot đúng model/currency/time/source. Unknown usage giữ reservation/unknown cost, không bằng0; ledger xuyên process/restart không reset.
- [ ] Report phải có coverage, missing cases, all gate statuses, relevance, error rate, per-branch latency, actor/chưa duyệt và nguồn artifact. Không cần normalization sửa cờ `llm_called` sau đo cho run mới.
- [ ] GREEN tests; commit `fix(evaluation): verify oversight evidence and model-specific reporting`.

**Gate:** Có thể tái dựng mọi kết luận từ artifact; chưa đủ bằng chứng không thể pass.

## Task 8: Human review, acceptance và giá trị sản phẩm

**Files:** Create versioned configs/artifacts, `docs/system-evaluation-report.md` cập nhật liên kết; không overwrite lịch sử. Test bổ sung theo lỗi mới, không chép lại implementation.

- [ ] Chạy `.venv\Scripts\python.exe -m pytest tests/unit tests/integration --basetemp=.pytest-completion-final -q`; `git diff --check`; kiểm tra artifact/log không có key. Baseline hiện tại 328 test pass chỉ là mốc tham chiếu, số test mới phải lấy từ output thật.
- [ ] Người dùng/giảng viên duyệt KB, policy, gold acceptance và phiếu grounding trên dev. Giải quyết bất đồng, ghi tên/thời điểm thực. Code tiếp tục được làm khi chờ review; không công bố acceptance trước bước này.
- [ ] Chốt toàn bộ release/model/policy/prompt/KB/config trước chạy acceptance mới. Smoke live3 case rồi chạy chất lượng đủ quota và HTTP100 requests +5 warm-up trong campaign ledger đã nêu; nếu quota/call-budget không đủ thì báo partial, xin điều chỉnh ngân sách ở lần chạy mới thay vì âm thầm tăng.
- [ ] Người chấm duyệt toàn bộ factual/policy claims của draft acceptance, kiểm tra relevance và missing expected outputs. Chấm trên draft/hash thực của run đó, không tái dùng phiếu của run khác.
- [ ] Thu paired user study manual/copilot với task và thứ tự counterbalanced. Đề xuất prototype3 người ×10 task ghép cặp; nếu chỉ có1 người thì báo n=1/giới hạn, không giả thêm participants. Không bắt buộc chứng minh phần trăm tiết kiệm được đặt tùy ý: báo paired median time difference, success và approve/edit/reject rates.
- [ ] Xuất report mới/manifest mới, đối chiếu từng yêu cầu FR-01…FR-08 và quality criteria; tất cả guardrail bắt buộc có numerator=denominator>0, ML/retrieval/grounding/HTTP đúng mục tiêu hoặc ghi rõ fail.
- [ ] Review cuối code + artifacts và chạy lại chỉ khi có thay đổi/lỗi mới. Handoff README, lệnh demo/benchmark, cách xem queue/audit, giới hạn và mục chưa đạt. Commit tài liệu/kết quả phù hợp; không commit credential/DB runtime.

## Thứ tự, checkpoint và người chịu trách nhiệm

| Checkpoint | Việc chính | Người thực hiện | Bằng chứng bàn giao |
| --- | --- | --- | --- |
| A | Task1–2: contract, routing, deadline | Developer; người phụ trách duyệt gold | Failure inventory, tests native timeout và routing |
| B | Task3–4: KB và semantic retrieval | Developer + người duyệt nội dung | KB version được duyệt, dev retrieval report |
| C | Task5–6: grounded drafts và latency | Developer; người dùng duyệt AI proposals | Evidence pack, per-branch HTTP benchmark |
| D | Task7–8: oversight, human evaluation, acceptance | Developer + reviewer/người tham gia study | Report có lineage, annotation người thật, requirement matrix |

Thực hiện theo Task1→2→3→4→5→6→7→8; có thể chuẩn bị nội dung KB và phiếu người chấm khi đang sửa code, nhưng không thay dependency approval bằng timeout chờ. Ưu tiên A/B trước C: tăng tốc LLM không sửa được gold sai, thiếu KB hoặc chuyển cấp sai.

Ngoài phạm vi mặc định: đổi classifier/embedding, hybrid retrieval, production deployment, dashboard mới, giao dịch thật và retraining. Chỉ mở rộng nếu failure inventory/dev evidence chứng minh cần và có quyết định riêng.

## Định nghĩa hoàn thành

Hoàn thành implementation khi tests/hợp đồng/truy vết đúng; hoàn thành nghiệm thu chỉ khi acceptance mới, human grounding và user study có bằng chứng thật. Nếu provider/KB/nhân lực review chưa đáp ứng, bàn giao phần code hoàn tất cùng gate fail/insufficient_evidence và lý do; không đổi nghĩa “hoàn thành” thành “test pass”.
