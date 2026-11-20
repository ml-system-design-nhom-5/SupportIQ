# Báo cáo đánh giá toàn hệ thống SupportIQ — cập nhật HTTP và grounding

Ngày cập nhật: 05-11-2026. Trạng thái: **live thử nghiệm, chưa nghiệm thu**.

## 1. Kết luận

Đã bổ sung phép đo qua HTTP demo thật và chấm grounding sơ bộ bằng AI trên toàn bộ 13 draft của lần chạy chất lượng trước. Người dùng đã chọn quy trình “AI chấm sơ bộ, người dùng duyệt sau”; chưa có kết quả chấm thủ công được phê duyệt.

p95 HTTP chung đạt **10.68 giây** trên 100 request, dưới mục tiêu 12 giây trong đợt đo này. Tuy nhiên, p95 riêng nhánh có gọi LLM là **15.31 giây**. Chất lượng toàn hệ thống vẫn chưa đạt: routing và retrieval còn dưới mục tiêu, thiếu draft ở nhiều case kỳ vọng, grounding chưa được người chấm xác nhận và một kịch bản oversight chưa đạt.

Không thay đổi số liệu hoặc manifest của lần chạy cũ. Báo cáo này tổng hợp hai đợt đo riêng, không coi chênh lệch latency là bằng chứng tối ưu hiệu năng.

## 2. Phạm vi và nguồn bằng chứng

- Chất lượng: [run gốc 156 case](../05-11-2026-system-live-experimental-00/report.md), model `supportiq_distilbert`, BGE semantic retrieval và Gemini thật.
- Grounding: [13 draft, evidence và mapping citation đã lưu](grounding/evidence.jsonl); nhận định AI có tên tác giả và trạng thái chờ duyệt.
- HTTP: `POST /api/demo/runs` qua loopback thật, **100 request đo + 5 warm-up**, concurrency 1, ID mới cho mỗi request, phiên cookie thật và SQLite riêng.
- Worker HTTP dùng snapshot/config/as-of đã pin và cùng ledger ngân sách với process điều phối; không dùng runner mặc định ngoài cấu hình benchmark.
- Đầu vào latency là 100 case đầu của suite theo cùng thứ tự chọn mẫu trước đây, bao gồm nhánh clarify/escalate và draft. Không chỉ chọn request thành công hoặc chỉ chọn nhánh nhanh.
- Suite vẫn là `draft`; bằng chứng mang nhãn `live_experimental`, không tự phê duyệt dữ liệu.

## 3. Bảng đối chiếu tiêu chí

| Tiêu chí | Kết quả | Nhận định |
| --- | --- | --- |
| ML CV Macro-F1 ≥ 0,85 | Run hệ thống chưa import bằng chứng CV | Chưa đánh giá lại trong báo cáo này |
| Escalation bắt buộc đúng 100% | 31/63 | Chưa đạt |
| Retrieval Recall@3 ≥ 0,80 | 61.76% E2E | Chưa đạt |
| Grounding chấm thủ công ≥ 90% | Chờ người duyệt | Chưa đủ bằng chứng |
| Grounding AI sơ bộ trên draft đã sinh | 15/17 = 88.24% | Dưới mục tiêu tham khảo; không thay điểm chấm thủ công |
| HTTP demo p95 ≤ 12 giây | 10.68 giây / 100 request | Đạt trong đợt đo HTTP này |
| Oversight | 3/4 scenario đạt | Chưa đạt toàn bộ |
| Draft ở các case kỳ vọng | 6/34 | Thiếu 28 draft kỳ vọng |

Recall@3 bên trên là kết quả toàn luồng với intent dự đoán, không thay bằng điểm retrieval dùng gold intent. False evidence rate trên tập unanswerable của lần chạy chất lượng là 29.51%.

## 4. Grounding sơ bộ và phiếu duyệt

Đã đọc 13 draft và tách 17 claim thực tế/chính sách. Lời xác nhận lại yêu cầu của khách hàng không được tính là claim chính sách. Mỗi claim có đoạn văn trong draft, citation, document/version, evidence span, checksum của excerpt và lý do chấm.

- **Supported: 15 claim.** Nội dung được evidence ghi lại hỗ trợ.
- **Unknown: 2 claim.** Cùng thuộc `sup-request_refund-01`: “không thể hủy đơn này” và “đơn đã được bàn giao cho courier”. Nguồn S1 là chính sách chung, chưa đủ chứng minh hai khẳng định về đơn cụ thể. Payload `order_facts` gửi LLM không được lưu đầy đủ trong artifact đánh giá để xác minh lại; không tự suy đoán là đúng hoặc bịa đặt.
- Unknown không được tính là supported. Điểm sơ bộ là **15/17 = 88,24%**, chưa phải kết quả người chấm.
- Đã xem toàn bộ draft đã sinh, nhưng chỉ 6/34 case `draft_expected` có draft. Chấm tốt các draft có sẵn không làm 28 case thiếu draft biến mất khỏi đánh giá.

### Các vấn đề cần duyệt ngoài grounding

| Case | Nhận định AI sơ bộ |
| --- | --- |
| `sup-refund_policy-05` | Hỏi điều kiện được hoàn tiền đầy đủ, draft lại nói chính sách hủy đơn. Nội dung có nguồn nhưng lệch yêu cầu. |
| `sup-refund_status-01`, `sup-refund_status-03` | Chỉ nêu thời gian hoàn tiền chung, chưa trả trạng thái hoàn tiền thực tế của đơn. |
| `sup-return_product-02`, `sup-return_product-04` | Nêu điều kiện đổi trả, chưa hướng dẫn khởi tạo quy trình trả hàng. |

Citation ID hợp lệ không đồng nghĩa claim được hỗ trợ hoặc câu hỏi đã được giải quyết.

### Người dùng duyệt sau

1. Mở [phiếu duyệt có draft và evidence](grounding/review.md).
2. Điền tên/thời điểm, kiểm tra toàn bộ claim và sửa nhận định trong [human_review.jsonl](grounding/human_review.jsonl). Trường `proposed_verdict` là gợi ý AI; `verdict` đang để `unknown` để người chấm xác nhận rõ ràng. Xác nhận đã rà soát đủ claim, bổ sung claim nếu AI bỏ sót.
3. Không đổi `reviewer_type: ai` thành người chấm nếu chưa thực sự duyệt. [ai_annotations.jsonl](grounding/ai_annotations.jsonl) không được import làm bằng chứng người chấm.
4. Có thể dùng `pipeline.evaluation.assess_system` để tạo assessment mới từ phiếu người chấm. Thiếu các draft kỳ vọng vẫn phải báo `insufficient_evidence`; không chứng nhận nghiệm thu chỉ vì các draft đã có được duyệt.

## 5. Latency qua HTTP demo thật

Timer bắt đầu trước HTTP POST và kết thúc sau khi nhận/parse HTTP response. Bao gồm kết nối HTTP, middleware/session, ML inference HTTP, routing, tra cứu nghiệp vụ, retrieval, LLM khi nhánh cần dùng, persistence và serialization.

Không gồm tải model, warm-up, browser rendering hay thời gian nhân viên đọc/duyệt.

| Nhánh | Số request | p50 (giây) | p95 (giây) |
| --- | ---: | ---: | ---: |
| Tất cả HTTP request | 100 | 2.21 | 10.68 |
| Có gọi LLM, gồm cả fallback | 36 | 4.65 | 15.31 |
| Thực sự sinh draft | 17 | 5.34 | 15.31 |
| Không gọi LLM | 64 | 2.17 | 2.27 |

HTTP technical errors: **0**; HTTP timeout: **0**; restart: **0**. Giá trị tối đa: **17.41 giây**. Dùng percentile nearest-rank cho p95, không loại lỗi khỏi tập đo.

Trong 100 HTTP request: 17 sinh draft, 44 escalate, 32 clarify và 7 manual fallback. HTTP 200 chỉ chứng minh endpoint trả kết quả, không chứng minh LLM đã soạn được câu trả lời. Trong 36 lượt có gọi LLM: 17 sinh draft, 12 từ chối do thiếu evidence, 3 unavailable, 3 invalid citations và 1 timeout.

p95 runner cũ 17,40 giây và p95 HTTP mới 10,68 giây thuộc hai đợt khác nhau, khác đường vào và tình trạng provider. Không lấy hiệu hai số để suy ra overhead HTTP hoặc tuyên bố code đã tăng tốc. Riêng nhánh LLM/draft vẫn có p95 15,31 giây, cần tiếp tục cải thiện.

## 6. Ngân sách và truy vết

Đợt HTTP ghi 36 reservation; chi phí dự phòng/ước tính theo ledger là 0.0900 USD. Có usage chưa xác minh, vì vậy đây **không phải hóa đơn thực tế**. Cộng với dự phòng của đợt gốc, tổng khoảng 0,3225 USD, dưới cấu hình 1 USD; tổng reservation là 129/200. Warm-up cũng đi qua ledger.

- [HTTP metrics](http_latency.json), [metrics theo nhánh](http_latency_slices.json), [chi phí](http_cost.json).
- [HTTP records gốc](http_results.jsonl) và [records chuẩn hóa](http_results.normalized.jsonl). Cờ `llm_called` bị thiếu trong bộ trích xuất ban đầu đã được khôi phục từ HTTP response lưu trong SQLite; không thay thời gian đo. [Nhật ký chuẩn hóa](normalization.json).
- [Manifest đợt HTTP](manifest.json) giữ hash run gốc và input hashes; [assessment manifest](assessment_manifest.json) bổ sung report và phiếu grounding. Không sửa run gốc.

## 7. Công việc còn lại trước nghiệm thu

1. Người dùng duyệt phiếu grounding và xác minh hai claim về đơn hàng bằng evidence nghiệp vụ có thể truy vết.
2. Bổ sung KB được duyệt và đánh giá lại độ liên quan, abstention và 28 case thiếu draft; không chỉnh theo test để làm đẹp điểm.
3. Khắc phục các trường hợp must-escalate sai và scenario oversight audit chưa đạt.
4. Cải thiện độ ổn định và p95 của nhánh LLM; đo lại cùng giao thức, ghi riêng lỗi provider.
5. Sau khi suite được duyệt và đủ bằng chứng, chạy acceptance độc lập. Hiện tại chưa kết luận hệ thống đạt toàn bộ tiêu chí đề tài.
