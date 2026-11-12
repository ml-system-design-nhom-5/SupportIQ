# autoeval v1 – bộ dữ liệu cố định

| File | Nội dung | Nguồn |
|---|---|---|
| `ml_noise.jsonl` | 84 câu supported/answerable × (gốc, văn nói, 3 biến thể lỗi chính tả) = 420 câu | sinh từ `data/benchmarks/system/v1/cases.jsonl`, seed 42 |
| `ml_oos.jsonl` | 80 câu ngoài phạm vi / mơ hồ / nhiều ý, kỳ vọng được gắn cờ hoặc chuyển xử lý | viết tay |
| `llm_cases.jsonl` | 66 case cho LLM: answerable, unanswerable, tra cứu đơn, chèn lệnh; kèm tài liệu nguồn | sinh từ benchmark + KB v2 |
| `manifest.json` | SHA-256 của các file trên và benchmark/KB/mock orders | `build-data` |

Không sửa tay `ml_noise.jsonl` / `llm_cases.jsonl`. Sau khi đổi `ml_oos.jsonl`, benchmark, KB hoặc
mock orders, chạy `python -m pipeline.evaluation.autoeval build-data` và commit cả manifest.
Xem `docs/autoeval.md`.
