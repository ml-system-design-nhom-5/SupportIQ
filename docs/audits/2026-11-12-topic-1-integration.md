# SupportIQ — Kết quả tích hợp và quyết định stakeholder

Ngày: 2026-11-12. Đối chiếu [đề gốc](../CHỦ%20ĐỀ%201.md), [review ban đầu](2026-11-12-topic-1-review.md) và [kế hoạch](../superpowers/plans/2026-11-12-topic-1-improvements.md).

## Phạm vi ủy quyền

Người dùng ủy quyền coordinator thực hiện các vai trò stakeholder. Coordinator chốt: giữ retry cho lỗi, không thêm regenerate draft_ready; model thiếu artifact mặc định unavailable; mọi reply phải do người vận hành duyệt; không đổi gold để đẹp số; dùng AI chấm và agent simulation nhưng không gán thành đánh giá của con người. Các dữ liệu giao dịch dùng trong kiểm thử là giả lập.

Ba worker Antigravity được giao worktree riêng qua [orchestration skill](C:/Users/PC/.agents/skills/orchestration/SKILL.md) và [orca-cli skill](C:/Users/PC/.agents/skills/orca-cli/SKILL.md). Coordinator review và yêu cầu sửa theo commit. Một lượt followup runtime lỗi agent_readiness/worker_identity_changed; không coi đó là worker đã hoàn thành sửa. Coordinator tích hợp và sửa phần runtime trên checkout chính, giữ workspace worker nguyên trạng.

## Thay đổi đã tích hợp

- Model fallback chỉ bật tường minh, có danh tính demo riêng; không giả hash của artifact thật hoặc score calibrated. Reload reset trạng thái cũ; thiếu provenance không tự biến thành verified. Metadata được đưa tới gateway và hiển thị boolean dưới dạng chữ ở developer details.
- Checker citation bổ sung kiểm tra một số claim ngắn về tiền/thời hạn/policy và nguồn order context thiếu field. Đây là structural heuristic, không chứng minh entailment.
- Startup tự tìm PostgreSQL và dùng driver Python với native libpq; giữ DLL directory handle sống, từ chối explicit path sai; không tắt Windows Application Control.
- Tách optional spaCy/model integration khỏi unit test adapter cố định; không tuyên bố regex bảo vệ mọi tên/địa chỉ tự do.
- Khôi phục Contact support từ chi tiết đơn; giữ order_id khi gửi yêu cầu và mở trang hội thoại riêng cho cả yêu cầu có/không có đơn. Backend vẫn kiểm ownership. Idempotency key đổi khi order context đổi.
- E2E chọn đơn thực sự thuộc tài khoản đang đăng nhập, không giả định ORD-1001. Reply thử nghiệm không tự bịa trạng thái giao vận.

## Kiểm chứng mới tại checkout chính

| Kiểm tra | Kết quả | Giới hạn |
|---|---|---|
| `python -m pytest -q` với driver Python/libpq trên PATH | **568 passed, 2 skipped, 2 deselected**, 130,66 giây, tại commit `fddec99` | Các profile real_model/cuda/live opt-in vẫn không thuộc suite mặc định; optional spaCy model chưa cài |
| Frontend Vitest | **13 passed**, 3 files | Có regression tests giữ order context và chuyển đúng trang hội thoại |
| `pnpm build` | TypeScript/Vite thành công | Build riêng không thay runtime smoke |
| Playwright Edge | **12 passed**, 30,4 giây; 1440/768/390/360px | Có axe accessibility và overflow assertions; tạo ticket giả lập trong local demo |
| Native startup không cấu hình driver thủ công | PostgreSQL/backend/AI chạy được | Application mặc định chỉ bind loopback |
| `scripts/verify_ai_integration.py` | model trained verified, 3 sources, 3 citations, draft_ready; analysis 12ms, draft 1456ms, LLM 1434ms | Một request; customer_reply=null trước phê duyệt; schema thử riêng được cleanup |
| Impeccable detector trên phần UI sửa | Không findings | Có xem screenshot mobile sau sửa; không thiết kế lại giao diện |

Kiểm tra Python trước sửa từng thất bại ở spaCy dependency và kỳ vọng retry cũ; E2E trước sửa phát hiện order hardcoded và lối hỗ trợ bị mất. Bảng trên ghi lần chạy sau khắc phục, không che các lỗi đã tìm được. Kết quả worker báo cáo được phân biệt với số test coordinator thực sự chạy.

## Đánh giá live và chấm claim của coordinator

Bằng chứng: `artifacts/evaluation/orchestrator-20261112-live-smoke/`. `manifest.json` ghi commit/source versions và hash file; `raw_cases.jsonl` lưu request/response và toàn văn nguồn theo phiên bản; `ai_claim_annotations.json` lưu từng claim và lý do chấm.

- 15 case smoke, 0 lỗi HTTP; p50 gateway 1,152s, p95 1,903s (nearest rank, n=15). Đây là **gateway request latency**, không phải benchmark end-to-end cho tải production.
- 9 bản nháp; 5 abstain; 1 escalation_recommended. Ba câu in-scope delivery_time/delivery_issue/payment_issue được abstain do uncertainty hoặc nhãn gần, không được tính là draft thành công.
- 37 factual/policy claims được coordinator AI chấm: **36 supported, 1 unsupported overgeneralization (97,30%)**. Một judge, sample chọn thuận tiện, không thay human claim annotations của bộ nghiệm thu chung.
- C07 cần sửa vì draft nói mỹ phẩm nói chung không được return do change of mind, trong khi nguồn chỉ giới hạn nhóm đã mở seal; không gửi nguyên văn.
- C15 chargeback/unauthorized transaction: dù các claim có nguồn, advice về duplicate charge chưa phù hợp; coordinator ở vai manager từ chối draft và chuyển xử lý. Grounding và độ phù hợp nghiệp vụ là hai tiêu chí riêng.
- Quyết định review trên 9 draft: 7 approve, 1 edit, 1 reject/escalate. Đây là quyết định trong bộ review giả lập; không phải tỷ lệ sử dụng của nhân viên thật hoặc audit event gửi khách.

`agent_paired_study.json` ghi 4 lượt trên cùng 2 kịch bản: tracking manual→assisted, return policy assisted→manual. Coordinator thực sự đọc nguồn và soạn/review; không gửi khách. Mean wall time manual 14,591s và assisted 13,934s. Thời gian bao gồm orchestration/tool overhead, không có người dùng thật; mẫu nhỏ, nguồn đã quen và có learning effect. Không suy ra giảm 20% thời gian hoặc tăng năng suất con người.

## Bằng chứng ML và retrieval còn giới hạn

`historical_ml_recomputed.json`: coordinator tính lại từ OOF lưu sẵn, không retrain. Cùng 37.911 sample IDs, folds và nhãn thật; đủ 46 intent/10 folds. Hash OOF baseline khớp training manifest.

| Model | Mean fold Macro-F1 | Std population |
|---|---:|---:|
| TF-IDF + Linear SVM | 0,990258 | 0,000883 |
| TF-IDF + Logistic Regression | 0,989220 | 0,001437 |
| TF-IDF + Multinomial NB | 0,984203 | 0,001232 |
| DistilBERT (stored OOF) | 0,995268 | 0,000999 |

DistilBERT OOF chưa có xác minh manifest từng fold/checkpoint; các giá trị này không chứng nhận một lần huấn luyện mới hoặc không leakage. Model serving thật được kiểm riêng ở smoke.

`retrieval_benchmark_compatibility.json`: 34/34 answerable cases trong suite acceptance v2 tham chiếu UUID/version cũ không xuất hiện trong current application release `POL-*`/version1.0–2.0. **Recall@3 để null/incompatible**, không tự map lại gold theo kết quả retrieval. Cần mapping có nguồn hoặc một bộ gold app-specific được duyệt trước run, và phải phân biệt nó với bộ chung hai nhóm.

Chi phí USD/request chưa được xác minh do chưa chốt bảng giá áp dụng; token usage thật được giữ trong raw records. Không ghi chi phí thiếu thành 0. Không tuyên bố production-ready hoặc toàn bộ quality gates đạt.

## Công việc còn lại trước nghiệm thu toàn bộ kế hoạch

1. Nhánh evaluation đã tích hợp qua 3 vòng worker review và thêm sửa tại coordinator: không coi summary snapshot là raw records, không nghiệm thu component-only metrics thiếu model provenance, CLI xuất UTF-8 nhất quán. Nhóm evaluation/metrics/review-probes đã chạy **53 passed**; lần chạy toàn bộ suite cuối đạt **568 passed, 2 skipped, 2 deselected**. Final independent review đang chờ worker tiếp tục sau lỗi provider 503; chưa coi lượt review này hoàn thành.
2. Chốt cùng phiên bản KB/gold cho đánh giá chung; tái chạy Recall@3, fault-injection và bộ escalation theo đúng benchmark/runtime.
3. Bổ sung provenance fold/checkpoint hoặc chạy lại CV theo pipeline khóa split nếu cần chứng nhận ML mới.
4. Human-only acceptance vẫn chưa đánh giá bằng người thật; AI/agent evidence ở trên được dùng cho phạm vi ủy quyền mô phỏng. Không đổi nhãn evaluator để vượt gate.

Ứng dụng được giữ chạy local; chưa push, deploy hoặc xuất dữ liệu sang hệ thống bên ngoài ngoài provider LLM được cấu hình cho các câu giả lập trong run live.
