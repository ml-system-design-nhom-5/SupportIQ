# Biên bản xử lý 8 vấn đề review

Branch: `fix/completion-review-eight`. Không commit/push hoặc ghi đè artifact lịch sử trong đợt sửa này.

| Vấn đề | Cách xử lý | Bằng chứng |
| --- | --- | --- |
| Late write sau timeout | IsolatedCaller chạy callable trong process; kill/join thực sự. Live E2E gọi endpoint có nonce trong managed worker | Native SQLite probe và integration HTTP worker |
| Dev/acceptance trùng | Tạo v3 có 50 dev, 156 acceptance với câu mới, pin bộ dev/v1 để kiểm tra overlap | Loader quota/hash/normalized-text checks; metadata vẫn draft |
| CV import không có lineage | Descriptor pin release/report/artifacts; kiểm tra model/version, protocol10fold, uniqueness/finite scores và mean | Positive CV fixture + tampered report và unsigned candidate negative tests |
| Order evidence không lưu | Ghi sanitized snapshot vào `llm_inputs` trước egress; giữ nguồn và hash trong persisted run/export | Gemini MockTransport với policy+order citation, lưu/đọc SQLite |
| KBv2 không được nối | Default adapter và benchmark v3 dùng KBv2 | Default KB probe và hash trong manifests |
| Pool không được dùng | Intent mặc định dùng `_get_client`; Gemini lazy pool sở hữu, đóng qua lifespan/dependencies | Spy hai request chỉ một pool, không top-level post |
| Human metadata mặc định/thiếu evidence | Actor/timezone/attestation boolean/relevance/citation/evidence bắt buộc | Missing-metadata negative probes; uppercase verdict và string-false regression |
| Báo cáo pass thiếu nguồn | Viết lại report, bỏ các số chưa có scope/lineage; lịch sử không được tái chứng nhận | Đối chiếu report với manifest và CVdescriptor |

TDD: các probe trọng tâm đã được quan sát RED trước khi sửa; GREEN sau sửa. Các fixture kiểm thử công thức metric được khai báo riêng trong `tests/annotation_fixtures.py`, không dùng làm annotation sản phẩm hoặc chữ ký người thật.

Mock validation mới: [run 50 case dev v3](../artifacts/evaluation/05-11-2026-review-eight-mock-00/report.md), 50 kết quả không thiếu, `simulated`, chưa chứng nhận nghiệm thu. Đã kiểm tra checksum15 artifact. Không gọi LLM trả phí trong đợt sửa.

Xác nhận người dùng duyệt grounding cũ giữ nguyên; 15/17 claim supported và 28 draft kỳ vọng thiếu không tự biến thành pass. Acceptance v3 do AI chuẩn bị cần người phụ trách duyệt ngữ nghĩa/gold/nguồn; không tuyên bố chỉ đổi câu chữ là bảo đảm độc lập thống kê.

Kết quả regression cuối được ghi tại phần kiểm chứng của `system-evaluation-report.md`.
