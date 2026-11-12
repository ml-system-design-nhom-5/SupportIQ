# Báo cáo Playwright MCP: 12 intent hỗ trợ

- **Ngày chạy:** 2026-11-05
- **Môi trường:** UI React và backend FastAPI; Playwright MCP gửi câu hỏi qua form Support.
- **Dữ liệu:** PostgreSQL schema kiểm thử tạm, độc lập inbox thật; 12 request được tạo, không gắn order.
- **AI:** DistilBERT, BGE, KB release hiện hành và LLM.
- **Điều kiện:** score và margin phải đạt policy; KB phải hợp lệ và cosine >= 0.55; intent nhạy cảm yêu cầu quản lý gửi; `human_agent` đề nghị escalation.

| Ticket | Câu hỏi | Intent dự đoán (score) | Kết quả | KB truy xuất |
|---|---|---|---|---|
| TCK-1001 | Where is my order? | `track_order` (0.9886661767959595) | Draft sẵn sàng | `POL-ORD-001` |
| TCK-1002 | Please cancel my order | `cancel_order` (0.9490456581115723) | Draft sẵn sàng; cần quản lý gửi | `POL-ORD-002` |
| TCK-1003 | When will my order arrive? | `track_order` (0.9720165729522705) | LLM không tạo được draft: `grounding_failed` | `POL-ORD-001` |
| TCK-1004 | My delivery is late and tracking has not updated | `missing_item` (0.38882848620414734) | Abstain; intent ngoài 12, score thấp, không có KB hợp lệ | Không có |
| TCK-1005 | How much does shipping cost? | `shipping_costs` (0.9839247465133667) | Draft sẵn sàng | `POL-SHIP-002` |
| TCK-1006 | What is your return policy? | `return_policy` (0.9962878227233887) | Draft sẵn sàng | `POL-RET-001`, `POL-RET-003`, `POL-RET-002` |
| TCK-1007 | I want to return a product I bought | `return_product` (0.9847442507743835) | Draft sẵn sàng; cần quản lý gửi | `POL-RET-001`, `POL-RET-003`, `POL-RET-002` |
| TCK-1008 | What is your refund policy? | `refund_policy` (0.9928520321846008) | Draft sẵn sàng | `POL-REFUND-001`, `POL-REFUND-002` |
| TCK-1009 | Please issue a refund for my order | `request_refund` (0.757427990436554) | Abstain do score dưới ngưỡng 0.8; yêu cầu quản lý | `POL-REFUND-001`, `POL-REFUND-002` |
| TCK-1010 | Where is my refund? | `refund_status` (0.9898968935012817) | Draft sẵn sàng | `POL-REFUND-007`, `POL-REFUND-002` |
| TCK-1011 | I was charged twice for one purchase | `request_invoice` (0.5189369320869446) | Abstain; intent ngoài 12, score thấp, không có KB hợp lệ | Không có |
| TCK-1012 | I want to speak to a human agent | `human_agent` (0.9951560497283936) | Đề nghị escalation; không tạo draft | Không cần KB |

## Nhận xét

- 8/12 request đi tới `draft_ready`; 2 abstain vì nhãn ngoài phạm vi và score thấp; 1 abstain vì `request_refund` chưa đạt ngưỡng; 1 đề nghị escalation cho người thật.
- Câu về giao hàng trễ bị phân loại thành `missing_item` (0.38882848620414734). Câu bị trừ tiền hai lần bị phân loại thành `request_invoice` (0.5189369320869446). Cả hai nhãn không nằm trong 12 intent hỗ trợ nên dừng trước LLM.
- “When will my order arrive?” bị xếp thành `track_order`, sau đó LLM trả `grounding_failed`. Retrieval vẫn tìm thấy `POL-ORD-001`; cần điều tra khâu grounding.
- `request_refund` nhận đúng intent nhưng score 0.757427990436554 thấp hơn ngưỡng 0.8. `cancel_order` và `return_product` có draft, nhưng quản lý phải gửi.
- Các tài liệu trả hàng là tài liệu thuộc KB release hiện hành, không có legacy document.

## Giới hạn

Mỗi intent được thử bằng một câu đơn tiếng Anh, không gắn order. Đây là kết quả đường đi cho các mẫu này, chưa đủ để ước lượng độ chính xác tổng quát. Draft `draft_ready` vẫn cần nhân viên xem xét và chưa được gửi khách.
