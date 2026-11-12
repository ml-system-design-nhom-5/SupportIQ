# Đặc tả cải thiện SupportIQ theo Chủ đề 1

Ngày 2026-11-12 · Trạng thái: người dùng đã ủy quyền triển khai và giao coordinator đảm nhận các vai trò stakeholder; xem [kết quả và giới hạn nghiệm thu](../../audits/2026-11-12-topic-1-integration.md).

## 1. Mục đích và lựa chọn thiết kế

Hỗ trợ nhân viên CSKH xử lý yêu cầu bằng model intent tự huấn luyện, nguồn chính sách có phiên bản và LLM; nhân viên quyết định mọi câu trả lời. Đặc tả này bổ sung [requirements hiện có](../../product/requirements.md), lấy [đề gốc](../../CHỦ%20ĐỀ%201.md) làm chuẩn khi có xung đột. Các vấn đề thực tế ở [báo cáo review](../../audits/2026-11-12-topic-1-review.md).

Phương án đã thực thi theo ủy quyền: cải thiện dần trên backend/AI gateway hiện tại, sửa model provenance và giữ kiến trúc đang dùng. Các quyết định stakeholder cụ thể được ghi trong báo cáo tích hợp.

Không xây chatbot tự gửi, cổng thanh toán, tích hợp đơn hàng thật hoặc tự động hoàn tiền. Không cần thêm model NER mới trước khi đo được lỗi privacy hiện tại.

## 2. Actors, dữ liệu và phạm vi

- Customer: chỉ đọc dữ liệu mô phỏng thuộc mình, gửi yêu cầu, xem reply con người đã gửi.
- Staff: xem/sửa intent, nguồn, draft; edit/approve/reject/escalate theo quyền.
- Manager: xử lý case cần thẩm quyền, duyệt proposal và xem báo cáo.
- Admin: quản lý tài khoản nội bộ và phiên bản; không truy cập ticket/dữ liệu khách.
- Policy owner: duyệt KB và ngày hiệu lực ngoài luồng gửi reply.

46 nhãn Bitext dùng cho đánh giá ML, split train/validation/test cố định trước thí nghiệm; baseline truyền thống và model được chọn cùng đánh giá. Không lấy `response` Bitext làm policy.

12 intent sản phẩm: `track_order`, `cancel_order`, `delivery_time`, `delivery_issue`, `shipping_costs`, `return_policy`, `return_product`, `refund_policy`, `request_refund`, `refund_status`, `payment_issue`, `human_agent`. `human_agent` chuyển người xử lý, không tạo draft. Các nhãn khác abstain/manual. Dữ liệu giao dịch và PII phải là giả lập. Giữ English cho model/KB/UI hiện có; tài liệu review bằng tiếng Việt.

## 3. Yêu cầu bổ sung có thể nghiệm thu

| ID | Hành vi bắt buộc | Bằng chứng nghiệm thu |
|---|---|---|
| IMP-01 | Thiếu/sai checksum artifact thì ML không được ready; không dùng heuristic dưới identity model thật | Test thiếu từng file, thư mục không có và checksum sai |
| IMP-02 | Nếu giữ fallback demo: bật tường minh, identity heuristic riêng, không checksum thật, không score calibrated | Test response/provenance và benchmark từ chối fallback |
| IMP-03 | Giữ API hiện có; thêm metadata provenance theo kiểu additive nếu cần, cập nhật contract/UI cùng lúc | Contract và UI hiển thị loại score/nguồn model đúng |
| IMP-04 | Intent override ghi actor và source=staff; số 1.0 do staff chọn không được hiểu là xác suất model | Test audit, score_kind và quyền sửa intent |
| IMP-05 | Chỉ truy xuất nguồn đúng phiên bản, còn hiệu lực theo as_of; thiếu/mâu thuẫn thì không khẳng định | Golden retrieval + expired/conflict scenarios |
| IMP-06 | Draft chỉ dựa trên nguồn và context được phép; thiếu chi tiết tạo clarification hoặc abstain, không bịa trạng thái đơn | Claim annotations và tests input thiếu dữ liệu |
| IMP-07 | Không tự gửi; authority case chỉ manager gửi; AI lỗi vẫn nhập reply thủ công được | PostgreSQL integration + E2E customer/staff/manager |
| IMP-08 | Audit lưu actor/action/reason và model/KB/prompt version; message/audit bất biến | Test DB trigger bằng runtime role |
| IMP-09 | Trước egress: mask dữ liệu nhận diện, allowlist order fields, không log key/raw PII | Captured fake transport payload + log assertions |
| IMP-10 | Metric thiếu là not_evaluated; mock/fallback không đạt live acceptance | Report contract tests và mixed-evidence rejection |
| IMP-11 | Mỗi run có run_id, commit, split/KB/model/prompt hashes, evidence_kind, model_mode, config, counts, environment | Manifest schema + kiểm tra liên kết từng metric |
| IMP-12 | Tài liệu phân biệt native app, legacy demo và evaluation, không tuyên bố vượt bằng chứng | Link/doc consistency check, review thủ công |

## 4. Luồng và giao diện dữ liệu

Customer tạo ticket → backend kiểm quyền, persist và mask → gateway phân loại/retrieve → trả analysis cùng routing/reason/version → draft nếu đủ điều kiện → staff kiểm chứng/edit → gửi trực tiếp hoặc proposal cho manager → customer nhận reply đã gửi. Jobs lỗi/timeout trả trạng thái xử lý thủ công, không đổi lỗi thành draft khẳng định.

Giữ endpoints `/v1/analyses`, `/v1/drafts`, `/v1/asset-versions` và schema backend trong `contracts/backend.openapi.json`. Không tạo API mới chỉ để phục vụ review. Provenance đề xuất gồm `model_mode=trained|heuristic_demo|unavailable`, `verified`, `score_kind`; chốt tên và regenerate schema trong task triển khai. Với heuristic, checksum artifact phải null/không có; chỉ model đã hash thực tế được gắn verified.

State UI phải phân biệt pending, draft_ready, abstained, escalation_recommended, llm_unavailable. Không hiện nút review draft khi draft không có. Retry mặc định chỉ cho lỗi transient hiện có; regenerate draft_ready là quyết định UX riêng, không phải yêu cầu bắt buộc của đề.

## 5. Tiêu chí chất lượng và cách đo

| Hạng mục | Gate và phương pháp |
|---|---|
| ML | Macro-F1 ≥ 0,85 qua 10-fold; công bố mean/std, per-class F1 và confusion matrix; baseline/model cùng splits; holdout không dùng tune |
| Robustness | Báo cáo riêng typo, paraphrase, mơ hồ, multi-intent, OOD; không trộn với 46-class headline |
| Retrieval | Recall@3 ≥ 0,80 trên câu có tài liệu đáp ứng; ghi denominator, KB version, gold document IDs; expired/conflict kiểm riêng |
| Grounding | ≥ 90% factual/policy claims được nguồn hỗ trợ trên bộ chấm thủ công; ghi unsupported/contradicted/insufficient, số claims, người chấm; không dùng citation existence thay entailment |
| Oversight | 100% câu trả lời qua người; tất cả mandatory escalation scenarios đúng; không transaction tự động |
| Latency | p50/p95 end-to-end, error rate, concurrency, cold/warm, hardware và số mẫu; p95 ≤ 12 giây trong cấu hình thống nhất |
| Cost | Token input/output thực tế; giá/version/ngày áp dụng phải được xác minh lúc chạy; thiếu giá ghi chưa đo, không ghi 0 |
| Product | Cùng tập yêu cầu, so sánh thủ công và có copilot; counterbalance thứ tự/người để giảm learning effect; báo cáo time và approve/edit/reject/escalate |

Mục tiêu giảm 20% hay ECE ≤ 0,10 trong tài liệu mở rộng phải được ghi riêng, không gán thành tiêu chí bắt buộc của đề gốc. Không công bố giảm thời gian khi chưa có người tham gia thực nghiệm.

## 6. Điều kiện bàn giao và rủi ro

Môi trường cần Python venv, Node/pnpm, PostgreSQL và native driver được Windows cho phép. Không vô hiệu hóa Application Control để nghiệm thu. LLM live là run được gắn nhãn riêng; dữ liệu giả lập, không in credentials. Tách schema thử nghiệm, không reset database demo đang dùng.

Bàn giao phải có test results mới, manifest, raw outputs, report và ma trận FR-01…FR-08. Các gate chưa chạy ghi blocked/not_evaluated kèm nguyên nhân. Correctness & Safety → Traceability & Human Control → Reliability & Latency → Cost. Chưa được gọi là production-ready chỉ từ suite unit hoặc một benchmark nhỏ.
