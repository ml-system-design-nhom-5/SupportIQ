# Semantic Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Truy xuất chính sách tiếng Anh bằng BGE-small-en-v1.5, kiểm tra nguồn và tra cứu đơn có quyền, cung cấp evidence cho LLM.

**Architecture:** Offline importer/index builder tạo snapshots có checksum; runtime lọc eligible chunks, cosine exact search rồi gộp top3 doc/version. Lookup đơn hàng qua commerce repository tách khỏi vector search. Nối service hiện có và audit/cache theo release.

**Tech Stack:** Python, Transformers/PyTorch, NumPy, SQLAlchemy, Redis, pytest; không BM25, RRF hoặc vector database.

**Spec:** [Semantic Retrieval design](../specs/2026-11-04-retrieval-design.md), [Routing](../specs/2026-11-04-routing-design.md).

## Global Constraints

* BGE English,384 chiều, CLS/L2 normalize, query prefix chuẩn;512 token limit, chunk≤480 gồm title, overlap40.
* CPU FP32, query batch1/build16, torch/BLAS4 threads scoped; GPU chỉ profile riêng nếu có yêu cầu benchmark.
* Top3 doc/version khác nhau, tối đa2 chunk/doc, context≤1500 BGE-token; exact lookup đơn không tính Recall@3.
* Approved+active+valid time+ACL/scope+release mới đủ điều kiện; JSON gốc không tự trở thành approved.
* Không keyword search/fallback. Encoder/index lỗi -> manual fallback; không cache business snapshots, không vector hóa đơn/PII.
* Threshold chọn dev, khóa trước final. Recall@3≥0.80, grounding≥90% cần số đo/chấm thật; không hứa đạt từ kiến trúc.
* Giữ human approval và không tự giao dịch. Không sửa đề bài hoặc overwrite artifacts.

## Review Focus

1. Version cũ/thu hồi xuất hiện từ cache — Tasks1/4 revalidate và invalidate.
2. Điều khoản seller khác nhau bị coi conflict — Task1 kiểm tra overlapping conditions.
3. Tokenization cắt mất ngoại lệ cuối — Task2 chia/kiểm tra bounds và không truncate im lặng.
4. Cosine luôn có nearest neighbor cho OOD — Task3 no-answer gate dev và unanswerable tests.
5. Guess order ID hoặc snapshot khách khác lộ LLM — Task4 check scope và allowlist fields.

## File map

Create `pipeline/retrieval/{__init__.py,build_index.py}`, `apps/core-backend/src/modules/retrieval/{importer.py,encoder.py,index.py}`, `apps/core-backend/config/policies/retrieval_policy.v1.json`, `db/migrations/knowledge/002_retrieval_metadata.sql`, `tests/unit/test_semantic_retrieval.py`, `tests/integration/test_routing_retrieval.py` (chia ownership với Routing plan).

Modify retrieval `models.py,schemas.py,service.py,validator.py`, privacy/commerce interfaces, LLM `builder.py,validator.py`, orchestration integration và release manifest schemas khi cần. Cập nhật backend dependency manifest hiện dùng sau kiểm tra phiên bản; dùng Transformers đã có, không thêm sentence-transformers nếu CLS pooling qua AutoModel đủ.

### Task1: Metadata importer và eligibility

**Interface:** `import_policies(session, policies_path, metadata_path) -> ImportReport`; `eligible_versions(session, release, scope, as_of) -> list[PolicyVersion]`. Metadata sidecar theo spec; stable external doc/version mapping.

- [ ] RED: approved valid allowed passes; inactive3/missing approval/date/wrong role/market excluded; same version different content rejects; import repeat idempotent; same rule different seller không conflict, overlap trái value có conflict.
- [ ] Run RED: `.venv\Scripts\python.exe -m pytest tests/unit/test_semantic_retrieval.py -k 'metadata or eligible or conflict' --basetemp=.pytest-semantic-task1 -q`.
- [ ] Implement migration nullable valid_to có nghĩa explicit approved unlimited; approved metadata/source hash required, reject ambiguous. Import report quarantine/coverage, không build ready khi không có eligible evidence; DB là authority runtime, source JSON giữ nguyên. Case conditions mô hình có cấu trúc, không so whole-document string.
- [ ] GREEN: chạy command, DB migration roundtrip fixture và timezone boundary valid_from/valid_to tests. Metadata thật do người phụ trách/giảng viên duyệt, không tự bịa ngày.
- [ ] Checkpoint: `feat: validate versioned policy source eligibility`.

### Task2: Encoder và index bất biến

**Interfaces:** `PolicyEncoder.encode_queries(texts) -> np.ndarray`; `.encode_passages(texts) -> np.ndarray`; `build_index(policies, metadata, model_dir, output_dir, index_version) -> dict`.

- [ ] RED: fake encoder checks query prefix only, normalize finite Nx384; >480 chia và giữ câu ngoại lệ, chunk overlap40; mismatch source/model/dimension not ready; `.npy` object dtype rejected; existing version no overwrite.
- [ ] Run RED: `.venv\Scripts\python.exe -m pytest tests/unit/test_semantic_retrieval.py -k 'encoder or chunk or index' --basetemp=.pytest-semantic-task2 -q`.
- [ ] Implement local safetensors/revision pin, CLS+L2, eval/inference_mode, CPU/thread config và batch; build chunks/embeddings.npy/metadata/manifest atomic, allow_pickle=False. Encode title+content và giữ offsets; không vector hóa tags thành lexical field hoặc đơn hàng. Runtime model load một lần, health/readiness có checksum/count/dimension mapping.
- [ ] GREEN: tests command và fake loader không network; real BGE download/encode là bước riêng ghi revision/hash, không tải trong unit test. Fail build giữ active index cũ, không silently truncate.
- [ ] Checkpoint: `feat: build versioned English semantic policy index`.

### Task3: Cosine ranking và relevance gate

**Interface:** `search_policies(query, eligible_chunks, encoder, policy, final_intent) -> RetrievalResult`; cosine descending, group max score/doc, tie intent chỉ khi score bằng rồi stable IDs. Caller không hard filter category theo intent.

- [ ] RED: toy vectors chứng minh top3 distinct docs; wrong intent vẫn retrieve doc đúng; invalid ACL doc similarity cao bị loại trước rank; thấp hơn dev threshold -> no_evidence; encoder failure -> manual fallback; không đủ3 thì trả ít, không thêm irrelevant.
- [ ] Run RED: `.venv\Scripts\python.exe -m pytest tests/unit/test_semantic_retrieval.py -k 'ranking or threshold or failure' --basetemp=.pytest-semantic-task3 -q`.
- [ ] Implement normalized exact dot search, eligible-before-ranking, top2 chunks/doc và budget1500 tokens; không lexical/RRF. Recheck metadata/rule conditions trước result. Không có threshold profile đã duyệt -> human-review-only và report gate chưa đánh giá; fake development profile dùng riêng unit fixture.
- [ ] GREEN: kiểm tra deterministic ties, empty query/corpus và relevance score không được gọi confidence/probability; error reasons đúng enum. Không chọn threshold bằng final suite.
- [ ] Checkpoint: `feat: rank semantic evidence with no-answer gates`.

### Task4: Lookup, cache, citation và tích hợp Routing

**Interface:** `lookup_order_evidence(order_token, ticket_customer, scope, as_of) -> BusinessEvidence`; giữ `retrieve_evidence()` signature cũ bằng adapter nhưng result mở rộng policy/business evidence và reasons/release metadata. Routing Task3 cùng phối hợp file runner, làm tuần tự tránh sửa chồng.

- [ ] RED: cross-customer denied, missing refund fields unknown, query chung không order vẫn có policy; cache role/release/time khác không dùng lại; revoked cached evidence chặn; no-source không enqueue LLM; context không phone/name/full transaction; citation sai version/hash bị reject.
- [ ] Run RED: `.venv\Scripts\python.exe -m pytest tests/integration/test_routing_retrieval.py --basetemp=.pytest-semantic-task4 -q` bằng DB/cache fixtures.
- [ ] Implement commerce snapshot source pin/metadata scenario_as_of, exact access lookup và allowlist tối thiểu; không order vectors/cache. Cache key version/scope/query hash+as_of, TTL≤60s và validity boundary; revocation invalidation, cache recheck. LLM builder nhận citation external doc/version/chunk/hash và business snapshot tách loại; validator không chỉ kiểm tra citation ID. Timeout retrieval2s đề xuất với cancellation thực, không giữ background task vô hạn. Không thay actor bằng agent cố định.
- [ ] GREEN: retry/audit approval tests, release swap/rollback và cache fail không bypass ACL. Sensitive request chỉ hỗ trợ thông tin, không side effect.
- [ ] Checkpoint: `feat: integrate scoped semantic evidence into copilot workflow`.

### Task5: Suite, benchmark và tài liệu bàn giao

**Files:** Create `pipeline/retrieval/README.md`, `pipeline/evaluation/evaluate_retrieval.py`, `tests/unit/test_retrieval_evaluation.py`; suite thật ở `data/evaluation/retrieval/<version>/` sau duyệt.
**Interface:** `score_retrieval(cases, retrieved_documents) -> dict` theo Recall@3/Hit@3 trong spec; query answered/abstained lưu đủ outcome, không loại mẫu khó.

- [ ] RED: gold{A,B}, top3{A,C,D} -> recall0.5/hit1; expired version không đúng; unanswerable không vào recall nhưng tính false-answer; no answerable -> N/A; missing case prediction -> error.
- [ ] Run RED/GREEN: `.venv\Scripts\python.exe -m pytest tests/unit/test_retrieval_evaluation.py --basetemp=.pytest-semantic-task5 -q` trước/sau implement metrics.
- [ ] Chuẩn bị dev≥60 answerable/30 unanswerable và final tương tự, cover11 content intents và human-agent escalation; hai người duyệt gold source/version/conditions. Tune dev cosine gate/chunk config rồi freeze; chưa có người duyệt thì dừng kết luận final, vẫn bàn giao code/fixtures.
- [ ] Đo oracle intent và predicted routing, Recall@3≥0.80 final, no-answer/conflict guards và p50/p95 cold/warm trên CPU cùng classifier; nguồn thiếu metadata không bypass cho đủ điểm. Chấm grounding≥90% bằng claims thật, all must-escalate/approval đúng, E2E p95≤12s theo protocol Evaluation; người dùng thử nghiệm/cost còn thiếu phải not_evaluated.
- [ ] Run tests hai kế hoạch và regression pipeline hiện có trong workspace temp riêng; `git diff --check`. Viết README setup/model pin/index build/serving/rollback/reasons/benchmark, checkpoint `test: benchmark and document semantic retrieval`.

## Nghiệm thu và self-review

Trình tự: metadata Task1 → index Task2 → search Task3 → integrations Task4 → benchmark Task5. Routing Tasks1/2 có thể chuẩn bị trước; tích hợp làm sau cả hai contract. Spec mục1–9 đều có task, mỗi Review Focus có test. Gửi reports thực tế gồm count filtered/quarantined, gold support, limits, version manifest; thiếu CV classifier hoặc user-study không được báo toàn đề bài pass. Kế hoạch chỉ hiện thực semantic retrieval theo sửa đổi mới nhất, không giữ dependency/module keyword search.
