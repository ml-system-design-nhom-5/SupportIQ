# SupportIQ System Evaluation Benchmark Suite (v1)

Bộ benchmark đánh giá toàn hệ thống SupportIQ phiên bản v1, phục vụ đo lường năng lực phân loại ý định, cổng định tuyến an toàn, trích xuất căn cứ chính sách (Semantic Retrieval) và cơ chế kiểm soát con người (Human Oversight).

---

## 1. Cấu trúc và Provenance

* **Suite ID**: `supportiq-system-acceptance-v1`
* **Split**: `acceptance`
* **Trạng thái hiện tại**: `draft` (Bộ dữ liệu cần hoàn thành kiểm thử độc lập bởi người đánh giá trước khi chuyển `approved` cho live acceptance).
* **Thời điểm hiệu lực (`as_of`)**: `2026-11-05T00:00:00Z`
* **Tệp danh mục (`cases.jsonl`)**: Chứa đúng 156 ca kiểm thử duy nhất, không trùng lặp ID, được cấu trúc theo định dạng typed JSON Lines.
* **Ma trận phân bổ (`coverage_matrix.csv`)**: Thống kê số lượng ca kiểm thử theo từng lát cắt nghiệp vụ (primary slice) và kiểm tra khớp định ngạch.

---

## 2. Định ngạch 156 ca kiểm thử (Primary Slices Quota)

Theo quy định tại mục 5 Đặc tả hệ thống, toàn bộ 156 ca kiểm thử được chia thành 5 lát cắt không giao nhau:

| Lát cắt chính (`primary_slice`) | Định ngạch | Số lượng thực tế | Mục đích kiểm thử |
|---|---|---|---|
| **`supported`** | 60 | 60 | 12 ý định sản phẩm cốt lõi (5 ca/ý định); kiểm tra khả năng phân loại và kích hoạt luồng đề xuất hỗ trợ. Riêng `human_agent` bắt buộc chuyển cấp (`must_escalate=True`). |
| **`unsupported`** | 34 | 34 | 34 ý định ngoài phạm vi chi tiết (1 ca/ý định); kiểm tra Gate 5 định tuyến đúng hàng đợi chuyên môn và không sinh bản nháp bừa bãi. |
| **`answerable`** | 24 | 24 | Các câu hỏi chính sách có tài liệu chứng cứ hợp lệ trong `data/knowledge/approved_kb.v1.json` (chính sách trả hàng, hoàn tiền, hủy đơn); kiểm tra Recall@3 và sinh bản nháp đúng căn cứ. |
| **`unanswerable`** | 18 | 18 | Các câu hỏi thiếu căn cứ chính sách (chưa phủ trong KB, tài liệu hết hạn, tài liệu chưa duyệt/bị thu hồi, hạn chế quyền truy cập ACL, mâu thuẫn chính sách); kiểm tra tính an toàn (fail-closed) và không sinh bản nháp ảo. |
| **`uncertainty_and_faults`** | 20 | 20 | Kiểm thử tính bền bỉ và cơ chế xử lý lỗi có kiểm soát: câu hỏi sai chính tả nặng, câu hỏi đa ý định nhập nhằng, câu hỏi ngoài miền (OOD null intent), tấn công tiêm nhiễm prompt injection, mô phỏng lỗi timeout/sự cố ML/Encoder/LLM, và vi phạm quyền hạn đơn hàng. |
| **Tổng cộng** | **156** | **156** | **Khớp chính xác 100% định ngạch thiết kế** |

---

## 3. Quy tắc kiểm tra tính toàn vẹn (Integrity & Checksums)

Mọi tệp đầu vào tham chiếu trong `suite_manifest.json` đều được kiểm tra mã băm SHA-256 nghiêm ngặt trước và sau khi chạy:
- Nếu tệp bị sửa đổi hoặc thiếu sót giữa chu trình đánh giá, hệ thống sẽ từ chối xuất báo cáo nghiệm thu và phát tín hiệu cảnh báo vi phạm provenance.
- Tuyệt đối không sử dụng đường dẫn thoát khỏi phạm vi repository (`..` hoặc symlink ngoài).

---

## 4. Phạm vi dữ liệu tri thức mặc định (KB Coverage Note)

- Hiện tại kho tri thức đã duyệt `data/knowledge/approved_kb.v1.json` chỉ chứa 3 chính sách cốt lõi được phê duyệt chính thức (Return Policy, Refund Policy, Cancellation Policy).
- KB mặc định **chưa chứng minh phủ mọi intent trong số 12 intent sản phẩm**.
- Hệ thống báo cáo rõ `kb_coverage_gap` và không tự ý bịa gold document IDs cho các intent chưa có tài liệu chứng cứ được phê duyệt hợp lệ.
