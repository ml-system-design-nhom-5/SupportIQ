# Đặc tả Routing với supportiq_distilbert

**Ngày:** 04/11/2026. **Trạng thái:** Thiết kế đề xuất, chưa hiện thực. Người dùng chọn `supportiq_distilbert`, phạm vi tiếng Anh.

**Căn cứ:** [Đề bài](<../../CHỦ ĐỀ 1.md>), [Evaluation](2026-11-03-pipeline-evaluation-design.md), [Retrieval](2026-11-04-retrieval-design.md). Thiết kế hướng tới đủ bằng chứng đánh giá; không cam kết đạt điểm trước thực nghiệm.

## 1. Mục tiêu và hiện trạng

Nhận intent từ `artifacts/models/trained/distilbert-supportiq`, hỗ trợ đầy đủ 12 intent theo đề tài và chuyển 34 intent còn lại đến nhóm nhân viên phù hợp. Mọi câu trả lời đều qua duyệt; mọi thay đổi đơn/hoàn tiền do nhân viên có quyền thực hiện ở luồng nghiệp vụ riêng.

Model local thực chất được fine-tune từ DistilBERT pretrained. Report hiện có ghi 2 epoch, train9.200/validation1.840; đây không phải bằng chứng đạt Macro-F1≥0,85 trên 10-fold CV. Không gán điểm CV baseline cho model này. Chọn làm model sản phẩm không thay đổi winner lịch sử của benchmark baseline.

Backend hiện có `intent/client.py`, `escalation/service.py`, `orchestration/pipeline_runner.py` và `config/policies/intent_policy.v1.json`. Cần thay đổi các điểm sau khi hiện thực:

* `all_46_labels` trong policy hiện không khớp taxonomy Bitext/model; một số tên như `create_account` phải thay bằng nhãn chuẩn, không thêm alias như lớp thứ47.
* Client đang fallback regex rồi gán confidence cao và giữ model version như inference thật; cần bỏ cách báo kết quả này. ML lỗi phải trả trạng thái lỗi và chuyển thủ công, không giả là model đã dự đoán.
* Gate hiện xét sensitivity trước confidence, có thể cho request nhạy cảm ít tin cậy đi tiếp. Thiết kế mới kiểm tra độ tin cậy trước khi cho tạo bản nháp.
* Orchestrator có scope agent cố định; phải dùng principal đã xác thực và phạm vi ticket thật, không hard-code UUID/role.

## 2. Lựa chọn kiến trúc

LLM tự quyết routing khó tái lập và làm tăng chi phí; chỉ dùng top1 classifier thì không xử lý được uncertainty và thiếu thông tin. Chọn **classifier + policy xác định + nhân viên**. Policy version hóa, kiểm thử độc lập, LLM không có quyền đổi policy/action. Đây là thiết kế được đề xuất để duyệt, chưa bổ sung code.

`privacy → model inference → routing policy → nguồn chính sách/lookup có quyền → retrieval gate → bản nháp hoặc clarify/escalate → nhân viên duyệt`.

## 3. Hợp đồng và thứ tự gate

`IntentPrediction`: request ID, `model_id=supportiq_distilbert`, revision/checksum, `top_k` gồm intent/probability theo mapping46 nhãn; score_kind=`uncalibrated_softmax` trừ khi có calibration artifact hợp lệ; duration/error. Service load safetensors local, tokenizer đúng checksum, eval/inference_mode, max_length64 như training; ghi nhận truncation. Output finite, probabilities hợp lệ, label mapping bijection đúng STANDARD_INTENTS; model/version mismatch -> lỗi.

`RouteDecision`: decision ID, action (`retrieve_draft`, `clarify`, `escalate`, `manual_fallback`), predicted/final intent, queue, reason_codes, required_slots/missing_slots, `must_human_approve=true`, `can_execute_transaction=false`, model/policy version, classifier score/margin và provenance override. Queue là phân công nhân viên, không tự cấp thêm quyền.

Thứ tự ưu tiên:

1. Xác thực actor, quyền ticket và cấu trúc input; không có quyền thì từ chối tại API, không tạo side effect.
2. Lỗi ML/version/output -> `manual_fallback`, `ml_unavailable`/`invalid_model_output`, queue general_support. Không tự sử dụng regex thay score model.
3. Khách yêu cầu gặp người rõ ràng (rule đã duyệt) hoặc intent human_agent đủ căn cứ -> escalate general_support ngay, không ép qua LLM. Rule ghi source=`explicit_human_request`, không score ML giả.
4. Ngôn ngữ không được hỗ trợ, tín hiệu nhiều ý/OOD hoặc confidence/margin không đạt -> clarify nếu có thể hỏi lại an toàn; escalation khi đã hỏi một lần vẫn chưa rõ hoặc case bắt buộc. Regex chỉ nhận diện một số tình huống đã biết, không chứng nhận phát hiện mọi OOD.
5. Một trong34 intent -> escalate theo bảng, reason=`recognized_outside_product_scope`, giữ nguyên nhãn để tránh bị coi invalid output.
6. Một trong11 intent tự phục vụ còn lại -> kiểm tra slot và quyền lookup nếu cần. Thiếu slot -> clarify, không suy đoán trạng thái giao dịch. Trường hợp nhạy cảm vẫn có thể truy xuất để hỗ trợ nhưng quyết định thuộc queue có thẩm quyền.
7. Retrieval không đủ/nguồn xung đột/cũ, hoặc nghiệp vụ tranh chấp/ngoại lệ -> escalate. LLM/API lỗi -> manual_fallback. Không có evidence thì không tạo khẳng định thiếu căn cứ.

Policy chứa ngưỡng confidence và top1–top2 margin chọn trên tập phát triển riêng với routing/OOD cases có nhãn, không trên final test. Ngưỡng0,70/0,80 cũ chỉ là cấu hình khởi đầu, chưa được coi đã hiệu chuẩn. Tối ưu selective accuracy/coverage và false accept OOD, đồng thời tất cả case bắt buộc escalation phải đúng. Không đạt hoặc chưa có policy được duyệt -> chế độ human-review-only, không tuyên bố đạt uncertainty/OOD. Override intent chỉ agent có quyền, audit lý do; không bypass safety, access hoặc source gates.

## 4. Ma trận12 intent

Các ID dưới đây là tài liệu ứng viên theo tiêu đề trong JSON, phải rà soát nội dung/hiệu lực và gán gold trước sử dụng. Bảng là hướng truy xuất, không hard filter theo intent.

| Intent | Hỗ trợ và nguồn chính | Slot / queue |
| --- | --- | --- |
| track_order | Hướng dẫn tracking POL-ORD-001, trạng thái/vận chuyển theo order | order_id cho câu cá nhân; order_support |
| cancel_order | Điều kiện POL-ORD-002/006; giải thích can_cancel/cancel_note, không hủy tự động | order_id khi xét đơn; order_support, manager khi ngoại lệ |
| delivery_time | POL-SHIP-001/007/008, estimated_delivery nếu có đơn | không cần order cho quy định chung; delivery_support |
| delivery_issue | POL-SHIP-003/004/005, shipping_timeline theo đơn | order_id khi xử lý cá nhân; delivery_support, manager khi tranh chấp |
| shipping_costs | POL-SHIP-002/006/007; không tự tính phí khi thiếu tariff/địa chỉ | slot theo điều kiện cần; delivery_support |
| return_policy | POL-RET-001/003 và quy định sản phẩm liên quan | hỏi điều kiện seller/product khi thiếu; returns_support |
| return_product | POL-RET-002/004/005/006/008, eligible_for_return nếu có | order_id khi tạo hướng dẫn theo đơn; returns_support |
| refund_policy | POL-REFUND-001/002 và tài liệu cùng nhóm đã duyệt | không cần order cho quy định chung; payments_support |
| request_refund | Quy trình hoàn/đối soát theo nguồn đã duyệt, không phê duyệt/chi tiền | order_id; payments_support, manager cho quyết định ngoại lệ |
| refund_status | Trạng thái/amount/time hoàn tiền theo đơn, POL-REFUND-002 và nguồn liên quan | order_id; payments_support |
| payment_issue | POL-PAY-001/003/004, payment_status/reconciliation_status | order_id nếu cần; payments_support, manager cho dispute |
| human_agent | Chuyển người thật, có thể kèm hướng dẫn liên hệ POL-CS-001 nếu hợp lệ | không chặn chuyển cấp vì thiếu order; general_support |

“Hỗ trợ12 intent” bao gồm xử lý human_agent bằng chuyển người, không phải tạo nội dung dài cho cả12. Khi hỏi chung không ép thu thập order ID. Không cấp quyền manager chỉ vì queue manager; nhân viên nhận việc vẫn phải có role thực.

## 5. Ma trận34 intent chuyển cấp

| Queue logic | Intent chuẩn (mỗi nhãn xuất hiện đúng một lần) |
| --- | --- |
| general_support | customer_service |
| account_support | change_account, close_account, open_account, order_history, recover_password |
| technical_support | technical_issue, use_app |
| order_support | add_product, remove_product, change_order, request_invoice |
| delivery_support | damaged_delivery, missing_item, track_delivery, wrong_item |
| feedback_support | submit_feedback, submit_product_feedback, submit_product_idea |
| payments_support | pay, payment_methods |
| product_support | availability, availability_in_store, availability_online, exchange_product, exchange_product_in_store, product_information, product_issue |
| returns_support | return_product_in_store, return_product_online |
| sales_support | sales_period |
| store_support | store_location, store_opening_hours |
| privacy_support | request_right_to_rectification |

Khởi động phải assert supported12 và escalated34 rời nhau, hợp đúng46 nhãn model. Queue logic map sang `standard`/`manager` hoặc assignment team DB qua config version hóa vì backend hiện chỉ có queue thô; triển khai prototype có thể map toàn bộ team thường sang standard nhưng vẫn giữ `requested_team` và reason trong ticket/audit. Privacy/dispute theo nhân viên có quyền; thiếu người trực -> general_support dự phòng có cảnh báo, không mất ticket. Không âm thầm đổi 34 intent thành12 để tạo câu trả lời.

## 6. Phiên bản, lỗi và kiểm thử

Release pin model/tokenizer/checksums, routing policy version và retrieval index/KB versions. Khóa phiên bản cho mỗi run; audit không chứa PII thô. Đồng thời lưu decision/action/queue/reason, override actor, nguồn evidence và error. Timeout theo ngân sách Retrieval; enqueue escalation idempotent theo run/decision để retry không tạo ticket lặp.

Tests bắt buộc: đủ46 và mapping chuẩn; mỗi12 có luồng thành công hoặc human_agent đúng; mỗi34 chuyển đúng queue; low confidence nhạy cảm không bypass; explicit human request được ưu tiên; override không bypass quyền; ML timeout không tạo confidence giả; slot chung/cá nhân phân biệt; order của người khác bị từ chối; ticket escalation ghi lý do và không tự gửi; retry không tạo escalation lặp; LLM lỗi/chính sách cũ/mâu thuẫn không tạo khẳng định chắc chắn.

Evaluation: case đủ46 label, typo/paraphrase/multi-intent/OOD/unknown-language; confusion matrix routing action/queue, coverage, selective accuracy và false acceptance, toàn bộ must_escalate đúng. Mục tiêu100% case escalation bắt buộc; không đặt F1 classifier mới từ điểm routing. Supportiq_distilbert cần chứng minh mục tiêu CV≥0,85 bằng thực nghiệm riêng hoặc báo rõ chưa đánh giá. Không tuning lại policy sau nhìn final suite mà vẫn gọi suite độc lập.

## 7. Ranh giới hiện thực

Sửa modules intent client/schemas, escalation gate và orchestration runner; bổ sung route policy v2 lấy taxonomy chung, service classifier phục vụ model đã chọn và integration tests. Giữ human approval/commerce execution ở backend hiện có. Đây là tài liệu thiết kế, không tạo service hoặc thay đổi policy đang chạy.
