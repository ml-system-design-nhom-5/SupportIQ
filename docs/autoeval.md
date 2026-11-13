# Đánh giá tự động (autoeval) cho module ML và LLM

Một lệnh chạy lại toàn bộ đánh giá trên **bộ dữ liệu cố định**, so với **ngưỡng nghiệm thu** trong
`pipeline/configs/autoeval.json`, ghi báo cáo và trả mã thoát để CI chặn thay đổi làm hệ thống xấu đi.

```powershell
# LLM offline (0 chi phí API, dùng probe giả lập cục bộ + exit code thật)
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run --suite llm --llm-mode offline

# ML + LLM offline (yêu cầu thư mục model release cục bộ nếu chạy suite ML)
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run

# Chỉ ML, ép dùng backend numpy (yêu cầu model release cục bộ; không dùng torch)
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run --suite ml --backend numpy

# LLM live: chỉ chạy thủ công cục bộ (tốn phí; cần GEMINI_API_KEY và ngân sách được duyệt riêng).
# Giới hạn trong config (`max_calls=80`, `max_cost_usd=0.5`) là vòng lặp chặn mềm/ước lượng, không phải
# hard cap HTTP/USD tuyệt đối; ngân sách còn lại của vòng hiện tại (3/24) không đủ phép chạy 80 calls.
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run --suite llm --llm-mode live --max-llm-calls <N_duoc_duyet>

# So sánh với lần chạy nền để phát hiện tụt lùi (chỉ trả exit 1 khi truyền thêm --fail-on-regression)
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run --suite llm --llm-mode offline --compare pipeline/configs/autoeval_baseline.json --fail-on-regression
```

Kết quả nằm ở `artifacts/evaluation/autoeval/<run-id>/` (`report.md` để đọc, `report.json` cho máy);
đường dẫn lần chạy mới nhất ghi trong `artifacts/evaluation/autoeval/latest.txt`.

| Mã thoát | Ý nghĩa |
|---|---|
| `0` | Mọi gate mức `block` đạt (truyền `--compare` đơn lẻ chỉ ghi diff vào báo cáo chứ không làm fail exit code nếu không bật `--fail-on-regression`) |
| `1` | Có gate `block` không đạt, hoặc phát hiện tụt lùi khi truyền kèm `--fail-on-regression` |
| `2` | Không chạy được đánh giá (manifest sai/chưa cập nhật, lỗi môi trường, hoặc theo hợp đồng CLI của Worker A: đối số/suite không hợp lệ hay thiếu/lỗi file `--compare` được yêu cầu đều fail-closed với mã `2`) |

## Đo những gì

### Suite ML (`--suite ml`)
Chạy model DistilBERT đã phát hành **cùng hàm routing thật** (`decide_route` + policy v2).

| Nhóm | Dữ liệu | Chỉ số chính |
|---|---|---|
| Toàn vẹn model | `artifacts/models/trained/distilbert-supportiq` | checksum khớp `EXPECTED_MANIFEST` của dịch vụ ML, đủ 46 nhãn |
| Câu do người viết | `data/benchmarks/system/v1/cases.jsonl` (156 câu) | accuracy, Macro-F1, đúng đội, đúng phạm vi 12/34, theo slice, nhầm lẫn |
| Hiệu chỉnh | như trên | ECE, bảng reliability, số câu sai mà tự tin ≥ 0,8, accuracy theo ngưỡng |
| Routing | như trên | câu bắt buộc chuyển cấp bị đưa sang soạn nháp (do ML), tỷ lệ clarify, lượt soạn nháp mang intent sai, đúng đội khi chuyển cấp |
| Nhiễu (NFR-02) | `ml_noise.jsonl`: 84 câu × (gốc, văn nói, 3 biến thể lỗi chính tả) | mức giảm Macro-F1 |
| Ngoài phạm vi (NFR-02) | `ml_oos.jsonl`: 80 câu (kiến thức chung, lĩnh vực khác, TMĐT ngoài taxonomy, mơ hồ, nhiều ý) | tỷ lệ gắn cờ/chuyển xử lý, tỷ lệ confidence thấp, AUROC entropy |

Backend: `--backend torch` dùng đúng stack của dịch vụ (`max_length=64`, `padding="max_length"`);
`--backend numpy` là bản dựng lại thuần numpy (`npbert.py`) để chạy ở máy/CI không có torch;
`auto` (mặc định) thử torch rồi lùi về numpy. Kiểm tra hai backend khớp nhau:
`python -m pipeline.evaluation.autoeval parity` (cần torch; sai lệch logits ≤ 1e-3, không đổi nhãn).
Latency trong báo cáo chỉ là thời gian tính của backend, không phải latency dịch vụ.

### Suite LLM (`--suite llm`)

**Offline (mặc định, miễn phí, tất định)**

| Nhóm | Cách làm | Bắt được |
|---|---|---|
| Payload gửi Gemini | Dựng đúng prompt của `prepare_llm_input` cho 21 case có đơn hàng, quét tên/điện thoại/email/mã đơn/mã vận đơn | LLM-01 (FR-10) |
| Probe validator | 18 phản hồi Gemini giả qua HTTP client giả vào `GeminiDraftClient.generate()`; so với hành vi **mong muốn** | LLM-03, 04, 05, 09 (**kiểm tra cấu trúc/contract citation & ràng buộc**, không kiểm tra semantic grounding) |
| Probe che dữ liệu | 11 chuỗi vào `redact_contacts()` | LLM-06 |
| Probe pipeline | `PipelineRunner` với thành phần giả: LLM/ML lỗi có vào `escalation_queue` không, có ghi `llm_ms` không | LLM-02, LLM-10 (cần đủ requirements, gồm torch, để import) |

**Live (`--llm-mode live`, tốn phí)** gọi Gemini cho 66 case cố định trong `llm_cases.jsonl`:
24 answerable (có nguồn đúng), 18 unanswerable (phải từ chối), 21 tra cứu đơn, 3 chèn lệnh.

- `--evidence oracle` (mặc định): đưa đúng tài liệu nguồn từ KB, cô lập chất lượng LLM khỏi retrieval.
- `--evidence retrieval`: dùng `RetrievalAdapter` thật (cần BGE).
- Chỉ số: tỷ lệ có bản nháp khi nên có, tỷ lệ từ chối khi nên từ chối, tỷ lệ citation sai,
  tỷ lệ câu có citation, số liệu không có trong nguồn, câu khẳng định đã giao dịch, có trích nguồn đúng,
  có nhắc dữ kiện bắt buộc, vi phạm khi bị chèn lệnh, latency p50/p95, token và chi phí.
- Ngân sách: `llm.max_calls` (`80`) và `llm.max_cost_usd` (`0.5` USD) trong `pipeline/configs/autoeval.json` (cùng `--max-llm-calls` để giảm thêm) chỉ là bộ đếm/ước lượng chi phí theo vòng lặp case, **không phải hard cap tuyệt đối cho từng HTTP retry hay hóa đơn USD phía provider**. Chưa có paid LLM call nào được cấp phép cho CI; ngân sách còn lại của vòng hiện tại (`3/24` calls) **không** đủ để chạy 80 calls, nên mọi lần chạy live thủ công trong tương lai phải được cấp ngân sách riêng biệt.
- `--judge`: thêm một LLM làm giám khảo, tách từng khẳng định và chấm SUPPORTED/UNSUPPORTED.
  Kết quả xuất ra `judge_claims.jsonl`.

**Grounding ngữ nghĩa (NFR-04), AI review được ủy quyền và người chấm.** Kiểm tra validator offline chỉ xác nhận cấu trúc citation/contract chứ không chứng minh suy luận ngữ nghĩa (semantic grounding). `--judge` hoặc đánh giá ngữ nghĩa do AI coordinator thực hiện dưới ủy quyền stakeholder (`delegated AI stakeholder grading`) **có thể được tính là bài đánh giá AI khi gắn nhãn tường minh là AI review (`human_participants = 0`)**, nhưng **không được gắn nhãn là human study hay thử nghiệm nhân viên CS thật** (những kiểm chứng dùng người chấm độc lập cho NFR-04 phải được ghi nhận tách biệt). Quy trình kiểm chứng/hậu kiểm thủ công với nhãn người chấm:
1. Chỉ chạy live `--judge` cục bộ khi được cấp ngân sách thủ công riêng và có `GEMINI_API_KEY` hợp lệ.
2. Mở `judge_claims.jsonl`, điền `human_label` (`SUPPORTED / UNSUPPORTED / NOT_A_CLAIM`) cho ít nhất 50–100 khẳng định.
3. Chạy lại với `--human-labels <đường dẫn file đã điền>` để có tỷ lệ grounding theo người chấm và
   độ đồng thuận giám khảo–người. Chỉ dùng giám khảo để sàng lọc khi độ đồng thuận đủ cao.

## Gates

Mỗi gate trong `pipeline/configs/autoeval.json` có `metric` (đường dẫn trong `report.json`), `op`,
`threshold`, `severity` (`block` làm lệnh thất bại, `warn` chỉ cảnh báo) và `ref` (mã yêu cầu hoặc mã lỗi
trong bản đánh giá). Gate bị bỏ qua khi suite không chạy, khi `skip_if` đúng (ví dụ live bị tắt), hoặc
khi chỉ số không có. Đổi ngưỡng bằng cách sửa file config và ghi lý do trong PR.

## Dữ liệu cố định

`data/benchmarks/autoeval/v1/` được commit cùng `manifest.json` (SHA-256, đã chuẩn hóa xuống dòng CRLF/LF).
Lệnh `run` từ chối chạy nếu dữ liệu, benchmark, KB hoặc mock orders bị sửa mà manifest chưa cập nhật.

- `ml_noise.jsonl`, `llm_cases.jsonl` sinh lại được bằng `python -m pipeline.evaluation.autoeval build-data` (seed 42).
- `ml_oos.jsonl` viết tay; thêm câu rồi chạy `build-data` để cập nhật manifest.
- Không chỉnh model, ngưỡng hoặc prompt dựa trên từng câu của các bộ này; nếu cần dữ liệu để tinh chỉnh,
  tách một bộ dev riêng.

## CI Dự kiến và Phạm vi Cục bộ

Kiến trúc CI (theo kế hoạch tại [2026-11-13-automated-evaluation-ci.md](superpowers/plans/2026-11-13-automated-evaluation-ci.md), đồng bộ cùng [tests/README.md](../tests/README.md) và [hướng dẫn xác minh ứng dụng](guides/application-verification.md)) hiện ở trạng thái **kế hoạch CI dự kiến** (chờ Worker B tích hợp workflow và chạy kiểm chứng trên hosted GitHub Actions; các lần chạy cục bộ không ngụ ý hosted CI đã xanh):

- **Không có paid call / không có workflow live hay tải model qua URL trong CI của B:** Worker B không thiết lập `workflow_dispatch` live job hay cơ chế biến `SUPPORTIQ_MODEL_URL` để tải weight trên runner. Mọi job CI dự kiến đều chạy **100% offline, 0 paid calls, 0 secret provider**.
- **PR / push lên `main` — Python + PostgreSQL (offline, dự kiến):** chạy bộ kiểm thử mặc định với dịch vụ PostgreSQL disposable và cấu hình tạm, lưu JUnit XML / báo cáo kết quả và không đóng gói secret làm artifact.
- **PR / push lên `main` — Frontend (dự kiến):** chạy Vitest và build production của `apps/frontend`, lưu log/build summary.
- **Offline Autoeval (bắt buộc không tốn phí, dự kiến):** chạy `python -m pipeline.evaluation.autoeval run --suite llm --llm-mode offline` với exit code thật (`0`/`1`/`2`) làm gate, giữ lại báo cáo Markdown/JSON làm bằng chứng. Suite **ML** trong CI offline thông thường được xem là **chưa cấp model / chưa đánh giá** (pending model provisioning / not evaluated), tránh ngầm hiểu skip thành pass.
- **Live LLM trả phí (ngoài CI, thủ công cục bộ):** chỉ chạy khi kích hoạt thủ công trên máy cục bộ qua CLI (`--suite llm --llm-mode live --max-llm-calls <N>`) với ngân sách được phê duyệt riêng ngoài CI.

## Kết quả nền lịch sử (historical: commit 159f9e6, model `dc7af8cf…`, backend numpy)

Lưu tại `pipeline/configs/autoeval_baseline.json`. **7 gate chặn không đạt**, tất cả trùng với lỗi đã
ghi trong bản đánh giá module:

| Gate | Giá trị | Ngưỡng |
|---|---|---|
| ml_scope_accuracy | 0,861 | ≥ 0,90 |
| ml_macro_f1_written | 0,611 | ≥ 0,75 |
| ml_noise_f1_drop (NFR-02) | 0,159 | ≤ 0,10 |
| ml_unsafe_drafts | 1 | = 0 |
| llm_payload_order_ids (LLM-01) | 42 | = 0 |
| llm_validator_blocking (LLM-03, LLM-05) | 3 probe | không có |
| llm_pipeline_failures_queued (LLM-02) | 2 probe | không có |

Đạt: toàn vẹn model; gắn cờ câu ngoài phạm vi 97,5%; không có tên/điện thoại/email trong payload.
Khi sửa một lỗi, chạy lại với `--compare pipeline/configs/autoeval_baseline.json --fail-on-regression`, rồi cập nhật file baseline trong cùng PR.

## Giới hạn

- Benchmark 156 câu có một số nhãn gây tranh cãi giữa các intent gần nghĩa của Bitext; nên rà lại.
- Bộ nhiễu và bộ ngoài phạm vi còn nhỏ, chỉ dùng để định hướng; mở rộng dần.
- Chỉ số grounding offline là kiểm tra cấu trúc/contract; chỉ số grounding live (`--judge`) hoặc đánh giá được ủy quyền bởi AI coordinator phải được gắn nhãn tường minh là AI review (`human_participants = 0`) và không được xem hay gắn nhãn như human study cho NFR-04.
- Không đo latency dịch vụ thật; NFR-08 cần load test riêng.
- Baseline TF-IDF đã có bản tái lập huấn luyện riêng trong repo nhưng pipeline `autoeval` hiện đánh giá cho model DistilBERT + Gemini, nên không so sánh trực tiếp trong cùng một gate.
