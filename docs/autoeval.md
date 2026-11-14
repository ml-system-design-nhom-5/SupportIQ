# Đánh giá tự động (autoeval) cho module ML và LLM

Một lệnh chạy lại toàn bộ đánh giá trên **bộ dữ liệu cố định**, so với **ngưỡng nghiệm thu** trong
`pipeline/configs/autoeval.json`, ghi báo cáo và trả mã thoát để CI chặn thay đổi làm hệ thống xấu đi.

```powershell
# ML + LLM offline (không tốn phí API), ~2–3 phút
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run

# Chỉ ML, ép dùng backend numpy (không cần torch)
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run --suite ml --backend numpy

# LLM live: gọi Gemini thật (cần GEMINI_API_KEY trong .env), giới hạn 80 lượt / 0,5 USD
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run --suite llm --llm-mode live

# So với lần chạy nền để phát hiện tụt lùi
.venv\Scripts\python.exe -m pipeline.evaluation.autoeval run --compare pipeline/configs/autoeval_baseline.json
```

Kết quả nằm ở `artifacts/evaluation/autoeval/<run-id>/` (`report.md` để đọc, `report.json` cho máy);
đường dẫn lần chạy mới nhất ghi trong `artifacts/evaluation/autoeval/latest.txt`.

| Mã thoát | Ý nghĩa |
|---|---|
| 0 | Mọi gate mức `block` đạt |
| 1 | Có gate `block` không đạt (hoặc tụt lùi khi dùng `--fail-on-regression`) |
| 2 | Không chạy được (thiếu file, dữ liệu bị sửa mà không cập nhật manifest, lỗi môi trường) |

## Đo những gì

### Suite ML (`--suite ml`)
Chạy model DistilBERT đã phát hành **cùng hàm routing thật** (`decide_route` + policy v2).

> **Gate data (2026-11-12, [ADR-0016](decisions/0016-frozen-intent-scenario-set.md)).** The ML suite reads its
> benchmark and its noise and out-of-scope sets from `ml.benchmark` and `ml.sets_dir` in
> `pipeline/configs/autoeval.json`, now the frozen set `data/benchmarks/intent/v2/` (since 2026-11-13; `intent/v1` is a
> diagnostic, see the ADR revision) (164 labelled messages,
> 480 noisy variants, 72 out-of-scope messages), written by an independent author. The run stops when the set
> does not match its `manifest.json`. The `system/v1` and `autoeval/v1` files named in the table below remain as
> development diagnostics only. Messages pass through `apps/ml_inference/preprocessing.normalize_placeholders`
> before tokenization, as in serving (DATA-59). The procedure and gate tolerances are in the
> [intent evaluation protocol](design/intent-evaluation-protocol.md).
> When `ml.policy` has a `multi_request` block (policy `v3`), each message is also split with
> `split_clauses` and classified clause by clause, as `ModelContainer.predict` does, so routing gate 2d
> ([multi-request detection](design/multi-request-detection.md)) is measured; the report adds
> `routing.multiple_requests_false_flags`.

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
| Probe validator | 18 phản hồi Gemini giả qua HTTP client giả vào `GeminiDraftClient.generate()`; so với hành vi **mong muốn** | LLM-03, 04, 05, 09 và giữ các hành vi đúng hiện có |
| Probe che dữ liệu | 11 chuỗi vào `redact_contacts()` | LLM-06 |
| Probe pipeline | `PipelineRunner` với thành phần giả: LLM/ML lỗi có vào `escalation_queue` không, có ghi `llm_ms` không | LLM-02, LLM-10 (cần đủ requirements, gồm torch, để import) |

**Live (`--llm-mode live`, tốn phí)** gọi Gemini cho 66 case cố định trong `llm_cases.jsonl`:
24 answerable (có nguồn đúng), 18 unanswerable (phải từ chối), 21 tra cứu đơn, 3 chèn lệnh.

- `--evidence oracle` (mặc định): đưa đúng tài liệu nguồn từ KB, cô lập chất lượng LLM khỏi retrieval.
- `--evidence retrieval`: dùng `RetrievalAdapter` thật (cần BGE).
- Chỉ số: tỷ lệ có bản nháp khi nên có, tỷ lệ từ chối khi nên từ chối, tỷ lệ citation sai,
  tỷ lệ câu có citation, số liệu không có trong nguồn, câu khẳng định đã giao dịch, có trích nguồn đúng,
  có nhắc dữ kiện bắt buộc, vi phạm khi bị chèn lệnh, latency p50/p95, token và chi phí.
- Ngân sách: `llm.max_calls` và `llm.max_cost_usd` trong config; `--max-llm-calls` để giảm thêm.
  Kiểm tra lại bảng giá trong config so với Google AI Studio trước khi tin con số chi phí.
- `--judge`: thêm một LLM làm giám khảo, tách từng khẳng định và chấm SUPPORTED/UNSUPPORTED.
  Kết quả xuất ra `judge_claims.jsonl`.

**Grounding (NFR-04) vẫn cần người chấm.** Quy trình:
1. Chạy live với `--judge`.
2. Mở `judge_claims.jsonl`, điền `human_label` (SUPPORTED / UNSUPPORTED / NOT_A_CLAIM) cho ít nhất 50–100 khẳng định.
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
- `data/benchmarks/intent/v1/` is built once by `python -m pipeline.evaluation.autoeval.build_intent_set` from
  `raw_cases.jsonl`; the script refuses to rebuild once `manifest.json` exists (DATA-23) and prints counts only.

## CI (`.github/workflows/autoeval.yml`)

- **offline**: chạy khi PR đổi intent/llm/orchestration/policy/model/dữ liệu/evaluator, và mỗi đêm.
  Cài torch CPU, chạy unit test của evaluator rồi `run --compare pipeline/configs/autoeval_baseline.json`,
  đưa `report.md` vào Job Summary và lưu thư mục kết quả làm artifact.
- **live**: chạy theo lịch hoặc thủ công (`workflow_dispatch`, chọn `llm_mode=live`, tùy chọn `judge`).

Cấu hình trong Settings → Secrets and variables → Actions:

| Tên | Loại | Dùng để |
|---|---|---|
| `SUPPORTIQ_MODEL_URL` | Variable | Link tải file zip chứa thư mục `distilbert-supportiq` (ví dụ asset của GitHub Release). Không có thì suite ML bị bỏ qua |
| `GEMINI_API_KEY` | Secret | Job live |
| `AUTOEVAL_ENFORCE` | Variable | `true` để gate `block` không đạt làm job đỏ. Để `false` cho tới khi các lỗi đã biết được sửa |

## Kết quả nền (commit 159f9e6, model `dc7af8cf…`, backend numpy)

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
Khi sửa một lỗi, chạy lại với `--compare`, rồi cập nhật file baseline trong cùng PR.

## Giới hạn

- Benchmark 156 câu có một số nhãn gây tranh cãi giữa các intent gần nghĩa của Bitext; nên rà lại.
- Bộ nhiễu và bộ ngoài phạm vi còn nhỏ, chỉ dùng để định hướng; mở rộng dần.
- Chỉ số grounding live là heuristic hoặc LLM-giám khảo, không thay được người chấm cho NFR-04.
- Không đo latency dịch vụ thật; NFR-08 cần load test riêng.
- Chưa so với baseline TF-IDF vì repo chưa có model baseline đã train.
