# Đặc tả Semantic Retrieval tiếng Anh — SupportIQ

**Ngày:** 04/11/2026. **Trạng thái:** Đề xuất thiết kế, chưa hiện thực/benchmark. Model ML do người dùng chọn là supportiq_distilbert; embedding chỉ cần tiếng Anh.

**Căn cứ:** [Đề bài](<../../CHỦ ĐỀ 1.md>), [Routing](2026-11-04-routing-design.md), [Evaluation](2026-11-03-pipeline-evaluation-design.md).

## 1. Quyết định và phần cứng

Phần cứng kiểm tra local: i5-14600K, RAM34.028.830.720 byte (khoảng32GiB), RTX5060 VRAM8151MiB. Theo yêu cầu đã cập nhật, chọn **semantic retrieval BAAI/bge-small-en-v1.5**, sau kiểm tra nguồn hợp lệ và trước tạo context LLM. Intent là tín hiệu ưu tiên, không hard filter theo category.

Không triển khai tìm kiếm từ khóa, BM25 hoặc RRF. Semantic search có thể bỏ sót điều kiện chính xác; kiểm chứng các trường hợp phủ định, số ngày, seller và ngoại lệ trên bộ đánh giá. Reranker/model lớn chưa dùng ban đầu, chỉ cân nhắc nếu dev benchmark chứng minh cần và còn latency budget. Không thêm vector database cho50 chính sách; dùng ma trận NumPy cosine exact search trong RAM, lưu file version hóa.

Embedding **BAAI/bge-small-en-v1.5** có vector384 chiều, giới hạn512 token, hỗ trợ tiếng Anh. Query thêm prefix `Represent this sentence for searching relevant passages: `; passage không thêm prefix; CLS pooling và L2 normalize theo tài liệu tác giả. Pin revision/checksum tokenizer/config/weights, chỉ safetensors local, eval/inference_mode. [Model card chính thức](https://huggingface.co/BAAI/bge-small-en-v1.5).

Phục vụ khởi đầu CPU FP32; batch encode index16, online query1, torch/BLAS4 threads scoped và ghi số thực. Vector50×384 float32 chỉ76.800byte (~75KiB), chưa gồm chunks, model weights và runtime. Đánh giá lựa chọn này là phù hợp quy mô, không phải số đo latency. GPU CUDA optional cho build index hoặc phục vụ khi benchmark cần, phải đo memory khi đồng thời chạy classifier; không nạp embedding/model mỗi request. CPU fallback phải rõ profile/telemetry, không âm thầm gắn nhãn GPU.

## 2. Nguồn dữ liệu thực tế và vấn đề cần giải quyết

`data/knowledge/policies.json`:50 tài liệu,47 active và3 inactive, các trường `doc_id,category,title,content,version,is_active,tags`; nội dung tiếng Anh, nhắc thương hiệu Tiki. Categories: orders, shipping_delivery, return_refund, payment, support, warranty, promotions. `is_active` không chứng nhận phê duyệt hay hiệu lực thực tế. Không gọi đây là chính sách Tiki thật đã xác minh.

`mock_orders.json`:100 đơn, dữ liệu theo trạng thái, có tên/phone/customer_id/payment/shipping/refund/items và một số mốc ngày/chuỗi tương đối. Không đưa file đơn hàng vào vector index, không expose PII giữa khách hàng. Xác nhận nguồn giả lập; dữ liệu customer_name/phone không được gửi LLM mặc định.

Backend retrieval hiện dùng any-word match và lấy3 dòng đầu, chưa phải semantic ranking. Cache chưa chứa release/scope version trong key. DB đã có KnowledgeDocument/Version metadata phê duyệt, valid_from/to, roles và policy_key; tái sử dụng qua importer, không tạo KB runtime song song không đồng bộ DB.

## 3. Hợp đồng nhập và quản trị nguồn

Giữ JSON gốc; tạo `data/knowledge/policy_metadata.<version>.json` đi kèm, key `(doc_id,version)` với source hash, approval status/approved_by/approved_at, valid_from/to timezone UTC (valid_to có thể null nếu vô thời hạn được duyệt rõ), allowed_roles, store/market applicability, language=en, policy_key và các rule assertions/conditions có cấu trúc khi cần phát hiện xung đột. Registry version hóa và được người phụ trách/giảng viên phê duyệt. Trường ngày chưa có không được tự suy từ giờ sửa file.

Importer upsert idempotent theo doc_id/version/content hash; cùng version khác content -> reject yêu cầu version mới. Bảo toàn external doc_id trong DB qua mapping ổn định, không dùng UUID thay mà mất citation lineage. Inactive3 không vào tập serving; giữ bản gốc/archive cho negative tests. Metadata thiếu -> quarantine/report, không tự gán approved. Không được lặng lẽ bỏ hết tài liệu để báo index build thành công: readiness cần coverage từng12 intent, report tài liệu bị loại và số khả dụng.

Doc hợp lệ khi: nằm trong KB release, approved, active, `valid_from<=as_of<valid_to` nếu có, role/market/store phù hợp. Thiếu customer scope áp dụng không rõ -> hỏi lại/route, không chọn điều kiện có lợi tùy ý. ACL theo principal thật. Dùng exact eligible set cho semantic search; index cũ không được làm policy vừa thu hồi quay lại kết quả. Recheck khi cache hit và trước context LLM.

`policy_key`/rule assertions không dùng một giá trị cho toàn tài liệu nhiều quy tắc. Rule có key, value/unit và condition (seller, product type, dates); hai điều khoản khác phạm vi không tự là mâu thuẫn. Hai rule cùng key/overlapping conditions và giá trị trái nhau -> conflict. Lỗi ngữ nghĩa chưa được mã hóa cần manual review; không tuyên bố phát hiện mọi conflict chỉ bằng regex hay embedding.

## 4. Chunking, index và ranking

Một policy ngắn = một chunk chứa title+content; tags chỉ dùng làm metadata, không tạo chỉ mục từ khóa. Tokenizer BGE đếm toàn passage; nếu >480 token chia tại đoạn/câu thành ≤480 token gồm title, overlap40 token, giữ nguyên điều kiện/ngoại lệ bằng context liên kết; không cắt im lặng phần cuối512. Policy dài không tách được an toàn -> manual curation trước index.

Chunk ID từ doc/version/content hash/chunk ordinal; giữ offsets, source hash, policy_key/conditions và parent. Query chỉ sanitized customer text, không chèn raw tên/phone/order transaction.

Passage là title+content, embedding384 chiều đã L2 normalize; query thêm prefix chuẩn model. Cosine = dot của các vector chuẩn hóa, không phải probability. Tính score trên toàn bộ chunks hợp lệ, gộp document/version bằng score chunk cao nhất, sort cosine giảm dần. Tie-break: ưu tiên nhóm intent liên quan chỉ khi cosine bằng nhau, sau đó doc_id/version/chunk_id ổn định. Không hard filter theo intent; không có lexical rank hoặc rank fusion.

Top3 kết quả cuối là **3 doc/version khác nhau**, mỗi doc tối đa2 chunk hữu ích, toàn context≤1500 BGE-token như ngân sách đề xuất. Nguồn cùng ID khác version không được trộn nếu release chỉ cho một version theo điều kiện. Dedup trước chọn3, không để chunk cùng doc chiếm hết top3. Lưu cosine score, chunk/doc rank và reason để debug; các score không phải evidence correctness.

## 5. Relevance, thiếu nguồn và lỗi

Không mặc định có top3 thì trả lời được: corpus hữu hạn luôn có nearest neighbor dù câu OOD. Chọn cosine threshold và điều kiện đủ evidence trên retrieval dev set có answerable/unanswerable; khóa trước final evaluation. Không lấy một ngưỡng score phổ quát làm xác suất đúng. Chưa có gate được duyệt thì human-review-only và chưa đánh giá no-answer safety.

Sau ranking: verify validity/ACL/hash lại, kiểm tra rule conflict và các điều kiện bắt buộc, thiếu thông tin thì clarify, không evidence thì no_evidence, conflict thì conflicting_evidence. Không lấp top3 bằng tài liệu không liên quan chỉ để đủ số. Query vô nghĩa/mơ hồ/chưa đủ slot không kích hoạt khẳng định chính sách.

Semantic encoder/index lỗi, timeout hoặc checksum mismatch -> manual_fallback/escalate với reason rõ; không fallback sang keyword search. Cache chỉ được sử dụng khi cùng release và vượt kiểm tra validity/ACL đầy đủ, không che trạng thái encoder/index không ready. Timeout Retrieval đề xuất2s (query encode+search+checks), cần đo concurrent model trước chốt.

## 6. Lookup đơn hàng và evidence cho LLM

Exact lookup theo order_id và phạm vi customer của ticket, principal có quyền; text phải resolve identifier qua privacy module, không tìm order bằng semantic similarity hoặc customer_name. Nhân viên không tự có quyền xem mọi đơn chỉ vì biết ID. Không tìm thấy/trái quyền -> thông báo an toàn và chuyển xử lý, không tiết lộ đơn của người khác.

Import mock_orders vào commerce store hoặc read-only repository dưới cùng access interface, pin seed hash và `scenario_as_of`. Không dùng cả JSON lẫn DB như hai nguồn “mới nhất” không có thứ tự ưu tiên; runtime chọn commerce store snapshot, JSON là seed. Fields thay đổi theo status: refund_status thiếu là unknown chứ không “chưa hoàn”; estimated_delivery không phải ngày đảm bảo. return_deadline chuỗi tương đối cần ngày tham chiếu; thiếu thì không tự tính điều kiện. Total_amount không tự suy bằng sum(items) khi chưa định nghĩa phí/discount/currency.

LLM nhận policy evidence và business evidence tách loại, chỉ trường cần thiết được phép. Ví dụ status lookup không cần phone, customer_name hoặc full transaction_id. Citation nghiệp vụ là snapshot ID + order token + as_of/hash, không fake doc policy. Budget top3 áp dụng policy docs; business snapshot riêng, không tính vào Recall@3 chính sách. Không cache snapshot đơn giữa request hoặc đưa vào vector index.

`Evidence` mở rộng: citation_id, external_doc_id, DB source/version IDs, chunk_id, snippet nguyên văn, title, content_hash, KB/index/embedding revisions, valid_from/to, approval/scope, as_of, rank và score provenance. BusinessEvidence có schema riêng. `RetrievalResult` gồm policy_evidence, business_evidence, query_hash, retrieval_mode/degraded flag, reasons, elapsed, needs_clarification và release IDs. Giữ tương thích với builder/validator bằng adapter rõ ràng; không ném metadata version khi chuyển Evidence cũ.

LLM chỉ soạn từ context, đánh dấu nguồn cho từng thông tin thực tế; unsupported/conflicting -> không tạo kết luận khẳng định. Citation kiểm tra source/version/hash và quyền trước hiển thị/gửi, không chỉ citation ID tồn tại. Nhân viên duyệt bản nháp; thay đổi nội dung cần duyệt lại. Tài liệu nguồn là dữ liệu, không làm theo instruction nằm trong content.

## 7. Cache, release và quan sát

Cache chỉ policy retrieval, TTL60s đề xuất; key gồm sanitized-query hash, intent, routing-policy version, KB/index/embedding revision, ACL/scope/market version và as_of scenario. Thời gian TTL không vượt mốc hiệu lực gần nhất; revocation invalidation và revalidation bắt buộc. Không lưu raw query/PII trong key/log. Cache không bao gồm LLM drafts hoặc business snapshot. Một cache hit không bypass kiểm tra role/valid_from/to/approval.

Build artifacts offline dưới `artifacts/search-index/<index-version>/`: chunks.jsonl, embeddings.npy (load với allow_pickle=False), metadata.json, manifest.json. Manifest có hash policy/metadata/model/tokenizer/chunk config và dimension/count mapping, code/runtime versions, source coverage. Ghi atomic, không overwrite version; build fail không thay active index. Release pin classifier+routing policy+KB+index+prompt; load kiểm tra hash/count/dimension và status, health readiness. Swap release nguyên tử, rollback cả tập tương thích; request đang chạy giữ release đã pin nhưng phải recheck revocation trước sử dụng evidence.

Metrics riêng: encode/search/gates/lookup latency, cache hit, empty/filtered/conflict/error counts, fallback, index readiness, model/release version. Không log raw phone/customer data. Cache không giúp che cold-path latency khi benchmark.

## 8. Đánh giá và điều kiện nghiệm thu

Tạo retrieval suite tiếng Anh độc lập khỏi Bitext response; gold theo doc/version/điều kiện/as_of, hai người rà soát. Đề xuất dev ít nhất60 answerable và30 unanswerable, final ít nhất60 answerable và30 unanswerable với paraphrase, typo, condition/seller, inactive, contradiction, ngoài phạm vi. Final cover11 intent có truy xuất nội dung và human_agent chuyển cấp; mỗi intent truy xuất có≥5 query đáp ứng được, cộng thêm để đủ60. Không giả human_agent phải tìm3 tài liệu mới đạt coverage.

Đánh giá semantic retrieval trên eligible corpus và query/gold đã khóa. Có thể đối chiếu các cấu hình chunk/threshold trên dev, không mở rộng sang BM25/hybrid trong phạm vi này. Đo hai chế độ intent gold và intent dự đoán để tách routing errors. `Recall@3(q)=|top3_doc_versions∩gold_relevant_doc_versions|/|gold_relevant_doc_versions|` rồi mean trên answerable; Hit@3 riêng. Query unanswerable không vào mẫu số recall nhưng phải đánh giá abstain. Gold>3 có trần recall<1, cần báo và thống nhất benchmark; không đổi gold sau khi thấy kết quả.

| Tiêu chí đề bài | Bằng chứng cần đạt / giới hạn |
| --- | --- |
| ML Macro-F1≥0,85 10fold | Chạy đánh giá phù hợp supportiq_distilbert; report2epoch hiện tại chưa chứng minh; Retrieval không bù tiêu chí này |
| Retrieval Recall@3≥0,80 | Final semantic retrieval trên nguồn hợp lệ; báo số query, per-intent và gold/predicted routing |
| LLM grounded≥90% | Người chấm claims supported/unsupported/contradicted/unverifiable; không có claim là N/A, không100%; cite nguồn thực đưa LLM |
| Safety/human oversight | Tất cả must_escalate đúng, gửi chỉ sau approve, không transaction side effect; unit tests và integration audit |
| Reliability | ML/retrieval/LLM lỗi/nguồn thiếu/conflict có fallback, không certainty thiếu căn cứ |
| p95 end-to-end≤12s | Đo cả classifier→routing→retrieval→LLM ở workload chung; ngân sách đề xuất ML1s/retrieval2s/LLM7s/overhead2s chỉ là timeout plan, không chứng minh tổng p95 |
| Cost/product value | Báo token/API cost, mean request gồm retry, thời gian xử lý có/không Copilot và approve/edit/reject/escalate; cần thử nghiệm người dùng |

Unit/integration tests: semantic paraphrase, điều kiện/số ngày/phủ định và cosine ordering/dedup, wrong intent vẫn tìm được policy đúng;3 inactive không trả; thiếu approval/date bị quarantine; role khác cache không lộ; cache invalidated policy revoked; same rule disjoint conditions không false conflict; overlapping contradictory rules escalated; no evidence không gọi LLM khẳng định; cross-customer order denied; no PII in vector/egress; tokenizer512 không cắt mất ngoại lệ; index/model checksum mismatch not ready; semantic timeout có fallback rõ; retry/audit/citation version đúng.

Đo CPU warm/cold, concurrent classifier+embedding và retry. GPU profile tách CPU, synchronization và memory; không đưa tất cả vào một bảng nhãn phần cứng sai. Không tuyên bố chắc chắn đạt tiêu chí chỉ từ chọn embedding hoặc Recall dev.

## 9. File thay đổi dự kiến và công việc người phụ trách

Backend modules retrieval: importer, dense encoder, cosine ranker, evidence/validity service; bổ sung index build ở `pipeline/retrieval/` và config dưới `apps/core-backend/config/`. Mở rộng DB metadata bằng migration và mapping source IDs; nối commerce lookup, privacy, LLM builder/validator và routing orchestration theo contracts. Chưa cần Elasticsearch/vector DB hoặc cross-encoder khi quy mô chưa đòi hỏi.

Con người phải phê duyệt metadata/hiệu lực, rà soát policy conflicts/coverage, xác nhận mock dữ liệu, gán gold và chấm grounding. Code tự động schema/checksum/index/rank/cache/tests/metrics theo quy tắc. Những thiếu hụt metadata hoặc benchmark chưa có phải xuất rõ, không tự gán “approved” để đạt readiness.

Hai tài liệu này là thiết kế để review trước triển khai; các ngưỡng, latency budgets, corpus/ngày hiệu lực và suite cần được khóa bằng evidence thực. Không thay JSON gốc, model hoặc policy backend trong công việc viết đặc tả này.
