# Chất lượng dữ liệu — Bước 1: Mục đích và yêu cầu

**Dự án:** SupportIQ — AI Customer Support Copilot for E-commerce.

**Căn cứ:** [CHỦ ĐỀ 1](<CHỦ ĐỀ 1.md>) và Chương 16 — Data Quality trong `ai-for-production.zip`.

**Bản cập nhật ngày 03/11/2026:** Đã kiểm kê các file trong `data/` bằng cách đọc CSV/JSON và đối chiếu README đi kèm. Các số lượng dưới đây là kết quả kiểm kê, chưa phải kết luận dữ liệu đạt chất lượng.

## 0. Dữ liệu hiện có

| File / nguồn | Nội dung đã xác nhận | Vai trò và lưu ý |
| --- | --- | --- |
| [`data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv`](../data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv) | 44.884 bản ghi, 46 intent, 13 category; các cột `instruction`, `intent`, `category`, `tags`, `response`. | Chọn làm bản đầu vào cho phân loại intent trong tài liệu này. Chưa thấy file chia train/validation/test trong `data/`. |
| [`data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset/`](../data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset/) | Chứa README, `.gitattributes` và một CSV giống hệt bản ở thư mục cha, cùng kích thước 42.624.013 byte và SHA-256. README mô tả dữ liệu hybrid synthetic, ngôn ngữ `en`, giấy phép `cdla-sharing-1.0`. | Là bản tải kèm tài liệu nguồn; không nối hai CSV thành một dataset vì sẽ nhân đôi toàn bộ mẫu. Chưa xác định revision hoặc ngày tải từ các thông tin đã kiểm tra. |
| [`data/knowledge/policies.json`](../data/knowledge/policies.json) | 50 tài liệu thuộc 7 category: `return_refund` (16), `shipping_delivery` (8), `orders` (7), `warranty` (7), `payment` (6), `support` (5), `promotions` (1). Có 47 tài liệu active và 3 inactive. Các trường: `doc_id`, `category`, `title`, `content`, `version`, `is_active`, `tags`. | Nguồn KB ứng viên. Nội dung đã đọc bằng tiếng Anh, nhắc thương hiệu Tiki; việc file tồn tại hoặc `is_active=true` không chứng minh được giảng viên phê duyệt hay phản ánh chính sách Tiki thực tế. |
| [`data/knowledge/mock_orders.json`](../data/knowledge/mock_orders.json) | 100 đơn hàng, có 8 giá trị `order_status`: `Cancelled`, `Delivered`, `Delivery_Delayed`, `In_Transit`, `Payment_Failed`, `Processing`, `Returned`, `Shipping`. Có dữ liệu khách hàng, thanh toán, vận chuyển, đổi trả/hoàn tiền và danh sách `items`; trường bổ sung thay đổi theo tình huống. | Nguồn nghiệp vụ mô phỏng dự kiến. Có `customer_name`, `phone`, `transaction_id`; cần xác nhận nguồn tạo giả lập và kiểm soát khi đưa vào log/API. Không kết luận dữ liệu là thật hoặc giả chỉ từ tên file. |

**Dấu vân tay của cả hai CSV (SHA-256):** `13A988266FED4E2B2C1FF947A89EF220CE09B5B13AC83C4A1496C0D7B81E8127`.

Bộ tình huống kiểm thử có đáp án tham chiếu, ma trận intent–tài liệu và log phản hồi chưa có file riêng trong `data/` tại thời điểm kiểm kê. Các nguồn này vẫn là đầu ra cần chuẩn bị cho đánh giá chung.

## 1. Mục đích sử dụng dữ liệu

Dữ liệu phục vụ SupportIQ, một công cụ hỗ trợ nhân viên CSKH soạn và kiểm tra câu trả lời. Kết quả AI phải được nhân viên xem xét trước khi sử dụng; dữ liệu không phục vụ tự động quyết định hoàn tiền, thay đổi đơn hàng hoặc thực hiện giao dịch.

| Nguồn dữ liệu | Mục đích sử dụng | Giới hạn sử dụng |
| --- | --- | --- |
| CSV Bitext đã tải | Dùng riêng `instruction` làm đầu vào và `intent` làm nhãn để huấn luyện, lựa chọn và đánh giá mô hình phân loại single-label trên 46 intent. Phân tích riêng kết quả của 12 intent trong phạm vi sản phẩm. `category` và `tags` phục vụ phân tích các nhóm dữ liệu. | Không đưa `intent`, `category`, `tags` hoặc `response` vào đặc trưng của baseline chỉ nhận câu hỏi. Không dùng `response` làm chính sách nghiệp vụ đã xác thực. Không mặc định hiệu năng trên dữ liệu tổng hợp phản ánh hiệu năng thực tế. |
| `policies.json` — KB ứng viên | Sau khi xác minh phê duyệt, làm nguồn truy xuất cho LLM và căn cứ kiểm tra thông tin, trích dẫn trong bản nháp cho 12 intent sản phẩm. | Lọc `is_active=true` cho luồng trả lời chính sách hiện hành; giữ bản inactive để truy vết/kiểm thử khi cần. Chỉ đưa tài liệu đã xác minh nguồn, hiệu lực và tính nhất quán vào KB được phép trả lời. |
| `mock_orders.json` | Cung cấp trạng thái đơn hàng, giao hàng, thanh toán và hoàn tiền để kiểm thử câu trả lời theo từng tình huống. Dùng `order_id` để tra cứu và `customer_id` để kiểm tra phạm vi truy cập. | Chỉ sử dụng sau khi xác nhận nguồn giả lập; không coi dữ liệu này là trạng thái giao dịch thực tế. Chỉ truyền cho LLM những trường cần thiết cho câu hỏi. |
| Bộ tình huống kiểm thử chung | Đánh giá retrieval, câu trả lời có căn cứ, xử lý thiếu thông tin, nhiều ý, ngoài phạm vi và escalation. | Tách khỏi dữ liệu dùng để điều chỉnh hệ thống; không đưa đáp án kiểm thử vào dữ liệu huấn luyện. |
| Phản hồi và log đánh giá | Ghi nhận approve/edit/reject/escalate, nguồn tham chiếu và phiên bản để đánh giá, giám sát và truy vết lỗi. | Phản hồi chưa kiểm duyệt không tự động trở thành nhãn đúng hoặc chính sách mới. |

**Đối tượng sử dụng kết quả đánh giá:** nhóm phát triển, người phụ trách dữ liệu, người đánh giá/giảng viên và quản lý CSKH. Ưu tiên kiểm soát lỗi có thể dẫn đến tư vấn sai về hủy đơn, thanh toán, đổi trả và hoàn tiền.

## 2. Phạm vi và giả định cần xác minh

* Đơn vị đánh giá của Bitext là cặp `instruction`–`intent`; của kho kiến thức là tài liệu và đoạn được truy xuất; của dữ liệu mô phỏng là bản ghi cùng các liên kết nghiệp vụ.
* README Bitext khai báo tiếng Anh (`en`); các mẫu đã đọc phù hợp khai báo. Phạm vi dữ liệu nền hiện tại là tiếng Anh; chưa có bộ đánh giá tiếng Việt riêng. Nếu bổ sung bản dịch, phải ghi nguồn, phiên bản và kiểm tra lại nhãn; ngôn ngữ toàn bộ corpus vẫn cần kiểm tra ở bước EDA.
* Đã xác nhận số lượng bản ghi, intent và category ở mục 0. Phân bố từng nhãn, tỷ lệ nhãn sai, trùng/gần trùng và tính đại diện vẫn cần được đánh giá; 44.884 mẫu không tự chứng minh dữ liệu đủ tốt cho mọi intent.
* `policies.json` có phiên bản và cờ active nhưng chưa có trường nguồn phê duyệt, `effective_from`/`effective_to` hoặc thời điểm rà soát. Cần bổ sung metadata trong dữ liệu hoặc manifest đi kèm trước khi xác nhận tính hiệu lực. Các nhóm category không tương đương trực tiếp với 12 intent; cần lập ánh xạ theo nội dung, không dùng số tài liệu để suy ra đã bao phủ đủ.
* `mock_orders.json` có các trường theo từng trạng thái; không bắt buộc mọi đơn đều có trường hoàn tiền hay vận chuyển. Cần schema chung và ràng buộc theo trạng thái. Các ngày tuyệt đối và chuỗi tương đối như `return_deadline` cần được đối chiếu với ngày tham chiếu cố định của kịch bản; chưa thấy trường ngày tham chiếu chung trong dữ liệu đã kiểm tra.
* Hai nhóm dùng cùng phiên bản dữ liệu nền, danh mục nhãn và quy trình chia dữ liệu. Cần làm rõ cách kết hợp 10-fold cross validation với train/validation/test: test giữ riêng cho đánh giá cuối, không tham gia lựa chọn mô hình hoặc điều chỉnh tham số; các fold được tạo trong phần dữ liệu phát triển.

## 3. Yêu cầu chất lượng và cách đo

Các tiêu chí dưới đây cụ thể hóa năm khía cạnh trong Chương 16: accuracy, completeness, uniqueness, consistency và currentness. **Các ngưỡng định lượng bổ sung là đề xuất cho prototype, cần được thống nhất trước thực nghiệm; chưa phải số liệu đo được hoặc yêu cầu gốc của đề bài.** Ngưỡng áp dụng cho bản dữ liệu đưa vào sử dụng; bản dữ liệu gốc được giữ lại để truy vết.

| ID / Tiêu chí | Yêu cầu cho SupportIQ | Cách đánh giá và mức chấp nhận đề xuất |
| --- | --- | --- |
| DQ-01 — Độ chính xác | Câu hỏi phải được gán đúng ý định; chính sách và trạng thái mô phỏng phải đúng với nguồn đã duyệt và kịch bản định nghĩa. | Hai người rà soát độc lập tối thiểu 10 mẫu/intent, hoặc toàn bộ nếu lớp có ít hơn 10 mẫu; thống nhất nhãn tham chiếu cho trường hợp bất đồng. Mục tiêu tỷ lệ nhãn sai ≤ 5% trên mẫu rà soát, báo cáo cả theo intent và quy mô mẫu. Chính sách đưa vào KB phải được đối chiếu 100% với nguồn duyệt. |
| DQ-02 — Tính đầy đủ | Dữ liệu phân loại có `instruction` không rỗng và `intent` hợp lệ; có đủ 46 intent. KB có tài liệu đáp ứng các tình huống trả lời được thuộc 12 intent; thiếu căn cứ phải được biểu diễn thành tình huống fallback. | 0 bản ghi thiếu trường bắt buộc trong bản sử dụng. 46/46 intent xuất hiện ở train và tập đánh giá, và trong từng fold nếu dùng stratified 10-fold. Lập ma trận bao phủ 12 intent với tài liệu hoặc quy tắc chuyển xử lý tương ứng. |
| DQ-03 — Tính duy nhất | Tránh bản ghi lặp làm tăng trọng số giả tạo hoặc gây rò rỉ giữa các tập đánh giá. | 0 bản ghi trùng hoàn toàn sau chuẩn hóa trong bản sử dụng. 0 nhóm câu hỏi trùng/gần trùng đã xác nhận nằm ở nhiều tập hoặc nhiều fold. Cùng câu hỏi nhưng khác nhãn phải được xử lý trước khi chia dữ liệu. |
| DQ-04 — Tính nhất quán | Nhãn thuộc cùng danh mục 46 intent; ánh xạ 12 intent thống nhất giữa ML, retrieval và kiểm thử. Các bản ghi và chính sách phải thống nhất về mã, trạng thái, thời gian, đơn vị và điều kiện nghiệp vụ. | 100% nhãn thuộc danh mục chuẩn. 0 lỗi liên kết bắt buộc và 0 mâu thuẫn nghiệp vụ nghiêm trọng chưa xử lý trong bản sử dụng. Tài liệu mâu thuẫn được cách ly hoặc xác định rõ thứ tự ưu tiên. |
| DQ-05 — Tính cập nhật | Tài liệu dùng để trả lời phải còn hiệu lực tại thời điểm của kịch bản; dữ liệu mô phỏng phải có mốc thời gian để diễn giải trạng thái. | 100% tài liệu chính sách có phiên bản, trạng thái và thông tin hiệu lực. 0 tài liệu hết hiệu lực được dùng làm căn cứ cho chính sách hiện hành. Cố định phiên bản Bitext; không đồng nhất dữ liệu mới hơn với dữ liệu tốt hơn. |
| DQ-06 — Khả năng truy vết | Có thể xác định nguồn và các thay đổi từ dữ liệu gốc đến bản dùng để huấn luyện, truy xuất và đánh giá. | Mỗi phiên bản có định danh nguồn/revision hoặc checksum, ngày lấy dữ liệu, mô tả xử lý và cấu hình chia tập. 100% tài liệu KB có mã nguồn và phiên bản để kiểm tra trích dẫn. |
| DQ-07 — Phù hợp với phạm vi | Dữ liệu đánh giá phải phản ánh cả bài toán 46 intent và luồng hỗ trợ 12 intent, đồng thời kiểm tra giới hạn của dữ liệu tổng hợp. | Báo cáo số mẫu theo nhãn, ngôn ngữ và từng tập. Bộ tình huống riêng phải có lỗi chính tả, diễn đạt khác thường, nhiều ý, ngoài phạm vi, thiếu/mâu thuẫn/hết hiệu lực nguồn và các trường hợp bắt buộc escalation. Chưa kết luận tính đại diện cho production nếu chưa có dữ liệu kiểm chứng. |
| DQ-08 — Quyền riêng tư | Dữ liệu dự án, tình huống và log không chứa dữ liệu cá nhân hoặc giao dịch thật, phù hợp phạm vi ở mục 1.3 của tài liệu chủ đề. | Rà soát các nguồn trước khi sử dụng; 0 trường hợp dữ liệu cá nhân/giao dịch thật được xác nhận còn tồn tại trong bản sử dụng. Dùng định danh và thông tin liên hệ giả lập khi cần. |

Áp dụng các tiêu chí vào dữ liệu hiện có:

* **Bitext (DQ-02/03/04/06):** kiểm tra `instruction`–`intent`, danh mục 46 nhãn và quan hệ intent–category; chỉ nạp một CSV. Gom nhóm câu hỏi trùng/gần trùng trước khi chia tập để tránh rò rỉ. Giữ `tags` để phân tích biến thể ngôn ngữ, không coi tag là nhãn intent.
* **Policies (DQ-01/02/04/05/06):** kiểm tra `doc_id` duy nhất, nội dung không rỗng, kiểu boolean của `is_active`, phiên bản và metadata phê duyệt/hiệu lực. 47 tài liệu active là ứng viên cần xác minh, không phải 47 tài liệu đã được chứng nhận đúng; 3 tài liệu inactive không được dùng để khẳng định chính sách hiện hành. Các nội dung warranty/promotions ngoài phạm vi 12 intent chỉ được dùng khi có ánh xạ phù hợp hoặc chuyển xử lý.
* **Mock orders (DQ-01/04/05/08):** kiểm tra `order_id` duy nhất; không yêu cầu `customer_id` duy nhất vì một khách có thể có nhiều đơn. Kiểm tra `items`, số lượng, số tiền, quan hệ giữa trạng thái đơn–thanh toán–hoàn tiền và các mốc thời gian theo kịch bản. Xác định rõ đơn vị tiền tệ và cách tính `total_amount`, kể cả phí/giảm giá nếu có, trước khi đặt công thức đối soát. Xác nhận nguồn giả lập của tên, số điện thoại và thông tin giao dịch; che hoặc bỏ trường không cần thiết trong log và yêu cầu gửi dịch vụ ngoài.

**Quy ước đo:** tỷ lệ lỗi bằng số đơn vị vi phạm chia cho số đơn vị được kiểm tra; luôn báo cáo tử số, mẫu số và phạm vi kiểm tra. Kiểm tra toàn bộ bằng quy tắc tự động khi có thể; kết quả rà soát nhãn theo mẫu không được trình bày như đã xác minh toàn bộ dataset. “Mâu thuẫn nghiêm trọng” là mâu thuẫn có thể thay đổi hướng xử lý hoặc điều kiện/hạn mức/thời hạn tư vấn cho khách hàng.

## 4. Điều kiện sử dụng và trách nhiệm

* **Được sử dụng:** dữ liệu đáp ứng các ràng buộc bắt buộc, có phiên bản và bằng chứng kiểm tra; các ngưỡng đề xuất đã được thống nhất và đánh giá.
* **Cần khắc phục hoặc giới hạn sử dụng:** phát hiện nhãn sai, thiếu bao phủ hoặc dữ liệu không đại diện. Ghi rõ vấn đề, phạm vi ảnh hưởng và người xử lý; không tuyên bố chất lượng vượt quá bằng chứng hiện có.
* **Chưa đưa phần dữ liệu bị ảnh hưởng vào sử dụng:** có rò rỉ train/test, dữ liệu cá nhân thật, chính sách chưa xác thực hoặc mâu thuẫn nghiêm trọng chưa giải quyết. Cách ly, sửa và kiểm tra lại trước khi dùng.
* **Phân công đề xuất:** người phụ trách ML quản lý nhãn và chia tập; người phụ trách KB quản lý nguồn và hiệu lực; người phụ trách kiểm thử quản lý bộ tình huống và bằng chứng đánh giá. Đại diện hai nhóm thống nhất phiên bản chung; giảng viên phê duyệt bộ FAQ/chính sách theo mục 2.3 của tài liệu chủ đề.

**Đầu ra của bước 1:** danh mục mục đích sử dụng, các giả định cần xác minh và bộ yêu cầu DQ-01–DQ-08. Bước này chưa chứng minh dataset đạt chất lượng; kết luận đạt/chưa đạt chỉ được đưa ra sau EDA, kiểm tra schema và xác minh nội dung. Macro-F1, Recall@3 và tỷ lệ câu trả lời có căn cứ ở mục 4 của tài liệu chủ đề là chỉ số của mô hình/hệ thống, không thay thế việc đánh giá chất lượng dữ liệu.
