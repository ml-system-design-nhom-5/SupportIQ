# CHỦ ĐỀ 1

**Project:** AI Customer Support Copilot for E-commerce
**Áp dụng:** Nhóm 2 và Nhóm 5

## 1. Product Definition & Scope

### 1.1. Mục tiêu

Xây dựng một **AI-powered Copilot** hỗ trợ nhân viên chăm sóc khách hàng (CSKH) trong thương mại điện tử.

Hệ thống sử dụng:

* **Non-generative ML:** nhận diện ý định (*intent classification*) từ yêu cầu khách hàng.
* **LLM + Retrieval:** truy xuất thông tin liên quan và đề xuất câu trả lời có căn cứ.
* **Human oversight:** nhân viên kiểm tra, chỉnh sửa hoặc từ chối câu trả lời trước khi sử dụng.

**Giá trị mong muốn:** Giảm thời gian xử lý yêu cầu, tăng tính chính xác và nhất quán của thông tin tư vấn, đồng thời hạn chế rủi ro do AI đưa ra kết quả sai.

### 1.2. Stakeholders

* **Primary user:** Nhân viên CSKH.
* **Beneficiary:** Khách hàng thương mại điện tử.
* **Other stakeholders:** Quản lý CSKH, quản trị viên và đơn vị quản lý dữ liệu/chính sách.

### 1.3. Scope

**In scope:**

* Tiếp nhận và phân loại yêu cầu bằng ngôn ngữ tự nhiên.
* Tra cứu chính sách, FAQ và dữ liệu nghiệp vụ mô phỏng.
* Tạo câu trả lời đề xuất kèm nguồn tham chiếu.
* Hỗ trợ nhân viên phê duyệt, chỉnh sửa, từ chối hoặc chuyển cấp xử lý.
* Ghi nhận phản hồi và thông tin phục vụ đánh giá, giám sát hệ thống.

**Out of scope:**

* Chatbot tự động trả lời khách hàng không qua nhân viên.
* Tự động phê duyệt hoàn tiền, thay đổi đơn hàng hoặc thực hiện giao dịch.
* Xây dựng hệ thống bán hàng, thanh toán, giao vận hoàn chỉnh.
* Tích hợp bắt buộc với hệ thống thương mại điện tử thực tế.
* Sử dụng dữ liệu cá nhân hoặc giao dịch thật.

## 2. Data & AI Tasks

### 2.1. Non-generative ML

**Task:** Single-label Intent Classification.

**Dataset chung:** [Bitext Retail E-commerce](https://huggingface.co/datasets/bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset).

* Input: instruction – câu hỏi/yêu cầu khách hàng.
* Target: intent – 46 nhãn intent.
* Output: predicted intent và thông tin hỗ trợ đánh giá độ tin cậy.
* Dataset được chia thành train/validation/test theo cùng quy trình, cố định trước khi thực nghiệm.

**Bắt buộc:** Mỗi nhóm tự huấn luyện và đánh giá tối thiểu một baseline truyền thống (ví dụ TF-IDF + Logistic Regression/SVM) và một giải pháp ML do nhóm lựa chọn.

Không bắt buộc multi-label classification. Các câu hỏi nhiều ý hoặc ngoài phạm vi sẽ được đánh giá trong bộ kiểm thử tình huống riêng.

### 2.2. Product Scenarios

Để giới hạn khối lượng công việc, sản phẩm tập trung hỗ trợ **12 intent chung** thuộc tập Bitext:

| **Nhóm nghiệp vụ** | **Intents** |
| --- | --- |
| Orders | track\_order, cancel\_order |
| Delivery | delivery\_time, delivery\_issue, shipping\_costs |
| Returns & Refunds | return\_policy, return\_product, refund\_policy, request\_refund, refund\_status |
| Payment | payment\_issue |
| Human support | human\_agent |

Mô hình ML vẫn được đánh giá trên 46 intent. Các intent ngoài phạm vi sản phẩm không bắt buộc tạo câu trả lời chi tiết; hệ thống phải có phương án chuyển xử lý phù hợp.

### 2.3. LLM & Knowledge Base

LLM được sử dụng để:

* Tổng hợp thông tin từ các tài liệu được truy xuất.
* Soạn câu trả lời đề xuất phù hợp với yêu cầu khách hàng.
* Làm rõ thông tin thiếu hoặc mâu thuẫn.
* Hỗ trợ nhân viên hiểu lý do chuyển cấp xử lý.

**Knowledge Base chung:** Sử dụng cùng một bộ FAQ/chính sách thương mại điện tử giả lập đã được giảng viên phê duyệt, bao gồm quy định giao hàng, đổi trả, hoàn tiền và xử lý đơn hàng.

Bộ dữ liệu nghiệp vụ mô phỏng có thể cung cấp trạng thái đơn hàng, giao hàng và hoàn tiền.

Hai nhóm phải sử dụng cùng phiên bản dữ liệu nền trong đánh giá chung. Không coi các câu trả lời mẫu (response) trong Bitext là chính sách nghiệp vụ đã được xác thực.

## 3. Functional Requirements

| **ID** | **Requirement** |
| --- | --- |
| **FR-01** | Tiếp nhận yêu cầu khách hàng và sử dụng mô hình ML tự huấn luyện để dự đoán intent. Hiển thị intent dự đoán và thông tin độ tin cậy thích hợp cho nhân viên. |
| **FR-02** | Dựa trên intent và nội dung yêu cầu, truy xuất tài liệu/chính sách hoặc dữ liệu nghiệp vụ phù hợp. Có khả năng nhận biết thông tin thiếu, không còn hiệu lực hoặc mâu thuẫn. |
| **FR-03** | Sử dụng LLM tạo bản nháp câu trả lời dựa trên thông tin truy xuất, kèm nguồn tham chiếu có thể kiểm tra. Không đưa ra kết luận khẳng định khi thiếu căn cứ. |
| **FR-04** | Cung cấp giao diện để nhân viên xem, chỉnh sửa, phê duyệt hoặc từ chối bản nháp. Hệ thống không được tự động gửi câu trả lời cho khách hàng. |
| **FR-05** | Hỗ trợ *abstention/fallback/escalation* khi AI không đủ tin cậy, thiếu thông tin, gặp yêu cầu nhạy cảm hoặc thành phần hệ thống bị lỗi. Phải ghi nhận lý do chuyển xử lý. |
| **FR-06** | Với các yêu cầu hoàn tiền, khiếu nại giao dịch hoặc ngoại lệ chính sách, hệ thống chỉ cung cấp thông tin hỗ trợ; quyết định nghiệp vụ thuộc về nhân viên có thẩm quyền. |
| **FR-07** | Ghi nhận quyết định của nhân viên (approve/edit/reject/escalate), phiên bản nguồn tham chiếu và phản hồi để phục vụ kiểm thử, giám sát và cải tiến. |
| **FR-08** | Cung cấp cơ chế xử lý lỗi cơ bản, phân quyền người dùng phù hợp và bảo vệ dữ liệu khi sử dụng LLM hoặc dịch vụ bên ngoài. |

Các nhóm được tự quyết định cách hiện thực những yêu cầu trên.

## 4. Quality Requirements & Success Criteria

Các chỉ số dưới đây là **mục tiêu đánh giá chung cho bản prototype**, không phải cam kết hiệu năng của một hệ thống production thực tế.

| **Dimension** | **Yêu cầu / tiêu chí đánh giá** |
| --- | --- |
| **ML quality** | Mục tiêu Macro-F1 ≥ 0,85 (10-fold cross validation); báo cáo per-class F1, confusion matrix và so sánh với baseline. |
| **ML robustness** | Đánh giá riêng trên các tình huống lỗi chính tả, diễn đạt khác thường, câu hỏi mơ hồ hoặc ngoài phạm vi. |
| **Retrieval quality** | Đánh giá mức độ truy xuất đúng tài liệu liên quan và còn hiệu lực; mục tiêu Recall@3 ≥ 0,80 trên tập câu hỏi có tài liệu đáp ứng. |
| **LLM quality** | Mục tiêu ≥ 90% các thông tin thực tế/chính sách trong bản nháp được hỗ trợ bởi nguồn truy xuất trên bộ kiểm thử được chấm thủ công. |
| **Safety & oversight** | 100% câu trả lời gửi qua luồng phê duyệt của nhân viên; không tự động thực hiện giao dịch. Các tình huống bắt buộc escalation trong test set phải được xử lý đúng. |
| **System reliability** | Hệ thống phải xử lý được các tình huống ML uncertainty, không tìm thấy tài liệu và LLM/API failure mà không tạo ra câu trả lời khẳng định thiếu căn cứ. |
| **Latency & cost** | Đo và báo cáo end-to-end p50/p95 latency, tỷ lệ lỗi và chi phí trung bình/request. Mục tiêu p95 ≤ 12 giây trong điều kiện kiểm thử thống nhất. |
| **User/Product value** | Đo và so sánh thời gian xử lý cùng một nhóm yêu cầu theo hai quy trình: thủ công và có SupportIQ hỗ trợ; báo cáo tỷ lệ bản nháp được chấp nhận/chỉnh sửa/từ chối. |

**Ưu tiên chất lượng:** Correctness & Safety → Traceability & Human Control → Reliability & Latency → Cost.

Không được cải thiện một metric bằng cách vi phạm các guardrails bắt buộc.

## 5. Assumptions & Constraints

### 5.1. Assumptions

* **ASM-01:** Dataset có đủ dữ liệu cho bài toán phân loại intent; sự khác biệt giữa dữ liệu tổng hợp và tình huống thực tế phải được kiểm tra.
* **ASM-02:** Knowledge Base và dữ liệu nghiệp vụ mô phỏng có thông tin nguồn, phiên bản và trạng thái hiệu lực đáng tin cậy.
* **ASM-03:** Nhân viên CSKH có khả năng xem xét và quyết định đối với các trường hợp cần human review.

### 5.2. Constraints

* Bắt buộc có **non-generative ML model tự huấn luyện + LLM**.
* Sử dụng dataset, bộ tình huống và quy trình đánh giá chung.
* Ưu tiên dữ liệu giả lập; không yêu cầu tích hợp production.
* Sản phẩm phải có khả năng triển khai, chạy thử và ghi nhận kết quả kiểm thử.

## 6. Initial Risks & Required Controls

| **Failure mode** | **Consequence** | **Required control** |
| --- | --- | --- |
| ML phân loại sai intent | Truy xuất sai tài liệu và tạo câu trả lời không phù hợp | Evaluation, uncertainty handling, nhân viên có thể sửa intent |
| Retrieval trả về tài liệu cũ hoặc không liên quan | LLM tạo câu trả lời có vẻ hợp lý nhưng sai chính sách | Kiểm tra nguồn, phiên bản/hiệu lực, abstention khi thiếu căn cứ |
| LLM tạo thông tin không có trong nguồn | Nhân viên đưa thông tin sai cho khách | Grounding, citation, kiểm tra kết quả, human review |
| Nhân viên quá tin tưởng AI | Lỗi AI vượt qua bước kiểm duyệt | Giao diện hiển thị nguồn, quyền chỉnh sửa/từ chối và feedback |
| LLM/API không khả dụng | Quy trình xử lý bị gián đoạn | Timeout/error handling, fallback sang quy trình thủ công |
| Lộ dữ liệu qua API/log | Rủi ro bảo mật và quyền riêng tư | Dữ liệu giả lập, tối thiểu hóa dữ liệu, bảo vệ API key và log |