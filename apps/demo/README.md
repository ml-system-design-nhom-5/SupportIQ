# SupportIQ · Bàn Hỗ Trợ Demo (Local Copilot Demo)

Giao diện web cục bộ phục vụ trải nghiệm và kiểm chứng hệ thống phân loại ý định (Intent Classification), định tuyến thông minh (Routing Gates), tra cứu ngữ nghĩa (Native Semantic Retrieval với BGE-small-en-v1.5) và cơ chế lưu trữ phản hồi kiểm duyệt nhân viên (Staff Feedback & Draft Revision).

> **Lưu ý quan trọng**: Đây là môi trường **Local Demo** độc lập chạy trên máy chủ nội bộ (`127.0.0.1`). Mọi dữ liệu khách hàng và đơn hàng là dữ liệu mô phỏng bảo mật. Thao tác kiểm duyệt bản nháp (`approve`/`edit`/`reject`/`escalate`) chỉ ghi nhận sự kiện phản hồi của nhân viên trong SQLite nội bộ, **không** tự động gửi tin nhắn hay gọi API thanh toán/giao dịch ra bên ngoài.

---

## 1. Cấu hình Gemini và khởi động 2 dịch vụ

Luồng mới dùng **Google AI Studio / Gemini Developer API**, mặc định `gemini-3.5-flash-lite`. API key chỉ nằm trên backend. Cài dependency demo nếu môi trường chưa đủ:

```powershell
.venv\Scripts\python.exe -m pip install -r apps/demo/requirements.txt
```

Nếu chưa có `.env`, sao chép `.env.example` vào `.env` tại gốc repository và điền `GEMINI_API_KEY`. Không ghi đè `.env` đã có. Cấu hình:

```dotenv
GEMINI_API_KEY=<key-local-cua-ban>
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=7
```

Demo tự đọc `.env` khi khởi động; biến môi trường hệ điều hành ưu tiên hơn `.env`. Khởi động lại demo sau khi đổi cấu hình. `.env` bị Git bỏ qua; không đưa key vào JavaScript, ảnh chụp hoặc báo cáo. Model `gemini-2.5-flash` ban đầu đã trả404 cho tài khoản này; `gemini-2.5-flash-lite` cũng không truy cập được, còn `gemini-3.1-flash-lite` đã tạo nội dung thành công khi kiểm chứng ngày04/11/2026. Quyền/quota có thể thay đổi theo tài khoản.

Luồng hiện tại: ML → routing → evidence hợp lệ → Gemini JSON → kiểm tra citation → bản nháp LLM → nhân viên duyệt. Gemini chỉ nhận câu hỏi đã che email/phone/identifier thông dụng, tối đa3 policy snippets và các trạng thái đơn được allowlist. Không gửi API key cho browser; không gửi tên/phone/full transaction từ dữ liệu đơn. Bộ che dữ liệu theo mẫu không bảo đảm nhận biết mọi PII trong văn bản tự do; demo chỉ dùng dữ liệu giả lập.

Mỗi bản nháp có metadata provider/model/model_version, prompt version, citations, token usage và thời gian LLM. Citation `[S1]` ánh xạ với source ID/version đang hiển thị. Validator kiểm tra định dạng, finishReason và ID citation; không tự chứng minh mọi claim đúng ngữ nghĩa. Vẫn cần nhân viên rà soát và bộ chấm grounding thủ công trước khi kết luận≥90%.

Provider timeout mặc định7 giây chờ HTTP (connect≤3 giây); đổi `GEMINI_TIMEOUT_SECONDS` trong khoảng(0,60] khi cần. Cấu hình local hiện dùng15 giây để kiểm tra provider phản hồi chậm; đây không phải bằng chứng đạt p95 end-to-end≤12 giây. Timeout, lỗi quyền/quota, output bị chặn/không hoàn tất hoặc citation sai đều không tạo template thay thế. Trả reason `llm_timeout`, `llm_auth_error`, `llm_rate_limited`, `llm_model_unavailable`, `llm_invalid_citations`... và chuyển xử lý thủ công. Gemini báo không đủ căn cứ thì escalation `llm_insufficient_evidence`. Không tự retry provider; người dùng có thể thử request mới khi lỗi tạm thời đã hết. Retry cùng run ID đã hoàn tất lấy kết quả đã lưu để tránh gọi trùng.

API dùng endpoint [generateContent](https://ai.google.dev/api/generate-content); model được chọn theo [giá Standard](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite). Usage được ghi, không tự suy chi phí hóa đơn khi chưa có billing thực tế.

**Kiểm chứng tích hợp ngày04/11/2026:** 237 test unit/integration pass với provider giả lập trong test. Gọi Gemini thật độc lập đã tạo được bản nháp có citation; các lượt demo end-to-end trong phiên kiểm tra gặp timeout hoặc citation sai và bị chuyển thủ công. Chưa chứng nhận luồng end-to-end ổn định, grounding≥90% hoặc p95≤12s. Retry mới có thể phát sinh một lượt API mới; retry cùng submission ID đã lưu lấy kết quả cũ, kể cả kết quả fallback.

### Khởi động

Hệ thống hoạt động theo kiến trúc 2 dịch vụ độc lập:
1. **Dịch vụ suy luận mô hình ML (`ml_inference`)**: Chạy DistilBERT fine-tuned phân loại 46 nhãn ý định, lắng nghe tại cổng `8001`.
2. **Dịch vụ ứng dụng Demo UI & Điều phối (`demo_backend`)**: Chạy pipeline điều phối, tra cứu ngữ nghĩa và phục vụ giao diện web, lắng nghe tại cổng `8000`.

### Bước 1: Khởi động dịch vụ suy luận mô hình ML (Cổng 8001)
Mở cửa sổ dòng lệnh thứ nhất:
```powershell
.venv\Scripts\python.exe -m uvicorn apps.ml_inference.app:app --host 127.0.0.1 --port 8001
```
*Kiểm tra sẵn sàng:* `/health` chỉ kiểm tra process; dùng `http://127.0.0.1:8001/ready` để kiểm tra model đã load và version.

### Bước 2: Khởi động dịch vụ ứng dụng Demo (Cổng 8000)
Mở cửa sổ dòng lệnh thứ hai:
```powershell
.venv\Scripts\python.exe -m uvicorn apps.demo.app:create_app --factory --host 127.0.0.1 --port 8000
```
*Truy cập giao diện:* Mở trình duyệt web và truy cập `http://127.0.0.1:8000/`.

---

## 2. Danh sách hồ sơ khách hàng mô phỏng (Server-side Profiles)

Phạm vi quyền hạn (`verified_scope`) và quyền truy cập đơn hàng được quản lý hoàn toàn ở phía máy chủ, ngăn chặn mọi nỗ lực can thiệp hoặc giả mạo quyền từ trình duyệt:

| ID Hồ sơ | Tên hiển thị | Đơn hàng được phép | Phạm vi quyền hạn (Server Scope) |
|---|---|---|---|
| `demo-customer` | Bùi Thị An (Khách hàng mẫu) | `ORD-1001` | `ticket:read order:read` |
| `cust-1002` | Phan Văn An (Khách hàng mẫu) | `ORD-1002` | `ticket:read order:read` |
| `staff-member` | Nguyễn Văn Hỗ Trợ (Nhân viên CSKH) | `ORD-1001`, `ORD-1002` | `ticket:read order:read staff` |

---

## 3. Các câu hỏi mẫu thử nghiệm (Sample Queries)

Giao diện tích hợp sẵn danh sách ví dụ mẫu để kiểm tra từng nhánh xử lý trong pipeline:

| Loại kịch bản | Câu hỏi tiếng Anh mẫu | Hồ sơ / Thiết lập | Hành động kỳ vọng |
|---|---|---|---|
| **Hỏi chính sách chung** | *"What is your standard return policy and window?"* | `demo-customer` · Không chọn tra cứu đơn | **Đề xuất bản nháp** (`retrieve_draft`): Trích dẫn `Standard Return Policy` và gọi Gemini tạo bản nháp có citation. |
| **Tra cứu đơn hợp lệ** | *"Where is my package and what is the current delivery status?"* | `demo-customer` · Đơn `ORD-1001` | **Chuyển nhân viên / Đề xuất** tùy theo độ tin cậy và trạng thái đơn hàng. |
| **Đơn hàng trái phép** | *"I want to track order ORD-1002 and see the shipping details."* | `demo-customer` · Đơn `ORD-1002` | **Chuyển nhân viên** (`escalate`): Bị chặn bởi Gate 4 với lý do `commerce_unauthorized_customer`. |
| **Thiếu thông tin đơn** | *"Can you check why my order is delayed? I need tracking updates."* | `demo-customer` · Tra cứu đơn nhưng để trống mã | **Cần bổ sung thông tin** (`clarify`): Bị chặn bởi Gate 3 với mã lý do `missing_order_id`. |
| **Ý định ngoài phạm vi** | *"How much are the shipping customs fees to Tokyo Japan?"* | `demo-customer` · Không chọn tra cứu đơn | **Chuyển nhân viên** (`escalate`): Hệ thống nhận diện thiếu bằng chứng (`insufficient_evidence`) hoặc intent chưa hỗ trợ. |

---

## 4. Ý nghĩa các nhãn trạng thái (Action Badges)

Mỗi phản hồi từ pipeline điều phối được phân loại theo 4 hành động chính:

1. 🟢 **Đề xuất bản nháp (`retrieve_draft`)**: Ý định có độ tin cậy cao, vượt qua mọi kiểm tra an toàn, tìm thấy tài liệu chính sách phê duyệt còn hiệu lực và sinh bản nháp gợi ý từ Gemini.
2. 🟡 **Cần bổ sung thông tin (`clarify`)**: Câu hỏi thiếu thông tin thiết yếu (ví dụ thiếu `order_id` khi hỏi về đơn) hoặc độ tin cậy mô hình ở mức trung bình cần hỏi lại khách hàng.
3. 🟠 **Chuyển nhân viên hỗ trợ (`escalate`)**: Yêu cầu thao tác nhạy cảm, khách hàng hỏi đơn hàng không có quyền truy cập, thiếu căn cứ chính sách hoặc khách yêu cầu gặp trực tiếp con người. Được đưa vào hàng đợi điều phối tương ứng (`returns_support`, `order_support`, `general_support`).
4. 🔴 **Xử lý thủ công (`manual_fallback`)**: Kích hoạt khi dịch vụ mô hình ML gặp sự cố hoặc không thể kết nối. Hệ thống tuân thủ nguyên tắc fail-closed, không đoán mò và chuyển toàn bộ cho nhân viên xử lý an toàn.

---

## 5. Quy trình kiểm duyệt bản nháp của nhân viên

Khi có bản nháp gợi ý:
- Bản nháp hiển thị nhãn **Sinh bởi gemini-3.5-flash-lite** và mã băm toàn vẹn (`draft_hash`).
- Nhân viên có thể nhấn **Duyệt bản nháp** để xác nhận bản nháp hiện tại.
- Nhân viên có thể sửa trực tiếp nội dung trong ô soạn thảo và nhấn **Lưu chỉnh sửa**. Hệ thống tính toán mã băm mới và cập nhật trạng thái; phiên bản cũ không thể duyệt tiếp nếu chưa xác nhận bản mới.
- Nhân viên có thể nhấn **Từ chối** hoặc **Chuyển cấp** nếu nhận thấy bản nháp không phù hợp.
- Tất cả thao tác được lưu trữ bền vững trong bảng `demo_feedback` của SQLite.

---

## 6. Chạy toàn bộ bộ kiểm thử

Để chạy kiểm thử đơn vị và tích hợp cho toàn bộ dự án:
```powershell
.venv\Scripts\python.exe -m pytest -q
```
Tất cả các bộ test đơn vị (`tests/unit/`) và kiểm thử luồng tích hợp (`tests/integration/`) phải hoàn thành và pass 100%.
