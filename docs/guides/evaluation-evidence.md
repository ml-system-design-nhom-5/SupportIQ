# Hướng dẫn Bằng chứng Đánh giá và Hợp đồng Báo cáo (Evaluation Evidence & Report Contracts)

Tài liệu này đặc tả cơ chế kiểm soát bằng chứng nghiệm thu, tính truy vết (provenance), hợp đồng báo cáo và phát hiện tụt lùi (regression detection) của SupportIQ theo yêu cầu **Chủ đề 1** và các đặc tả **IMP-10**, **IMP-11**.

---

## 1. Mục đích và Nguyên tắc Cốt lõi

Hệ thống đánh giá SupportIQ được thiết kế theo các nguyên tắc nghiêm ngặt về độ trung thực của bằng chứng:
1. **Chỉ số thiếu không thể thành 0 hay PASS**: Không bao giờ gán mặc định `0.0` cho các chỉ số thiếu. Với các chỉ số giới hạn trên (upper-bound metrics như tỷ lệ ảo giác hallucination rate $\le 0.02$, ECE $\le 0.10$), giá trị thiếu phải ở trạng thái `NOT_EVALUATED` hoặc `INSUFFICIENT_EVIDENCE` và **không được phép PASS**.
2. **Mock hoặc Heuristic không thể chứng nhận Live Acceptance**: Chạy thử ở chế độ mô phỏng (`simulated`/`mock`) hoặc model heuristic fallback không được cấp trạng thái `certified_live_acceptance`; phải bị từ chối rõ ràng bằng `simulated_mock_rejected` hoặc `unverified_heuristic_rejected`.
3. **Bằng chứng hỗn tạp (mixed evidence) bị từ chối**: Nếu một lượt chạy khai báo `evidence_kind: live` nhưng chứa thành phần mock hoặc heuristic, hệ thống sẽ từ chối nghiệm thu (`mixed_evidence_rejected`).
4. **Báo cáo từ bộ nhớ đệm (cached metrics) không đại diện cho suy luận mới**: Báo cáo tổng hợp từ dữ liệu cũ phải ghi rõ `execution_mode: cached_only`, `new_execution: false` và hiển thị cảnh báo `Cached Report`.
5. **Phân biệt điều kiện so sánh hồi quy (regression comparability)**: Hai lần chạy khác nhau về `kb_hash`, `split_hash`, hoặc `model_hash` không được coi là hồi quy trong cùng điều kiện; hệ thống cảnh báo `incompatible_configuration` và không báo động giả.
6. **Mọi chỉ số phải truy vết được về raw evidence**: Mỗi chỉ số trong manifest liên kết trực tiếp với trường dữ liệu gốc qua `evidence_ref`.
7. **Bảo toàn hiện trạng artifacts cũ**: Kết quả đánh giá mới luôn ghi vào thư mục độc lập (`artifacts/evaluation/regression/runs/regression_<timestamp>_<uuid>/`), tuyệt đối không ghi đè các artifacts lịch sử.

---

## 2. Hợp đồng Chỉ số và Bằng chứng (IMP-10)

### 2.1. Phân loại Chỉ số và Xử lý Khi Thiếu Dữ liệu

| Nhóm | Tên chỉ số | Mục tiêu | Xử lý khi thiếu dữ liệu |
|---|---|:---:|---|
| **Intent (Phân loại ý định)** | `intent_accuracy` | $\ge 0.85$ | `status = NOT_EVALUATED`, value = None |
| | `intent_macro_f1` | $\ge 0.85$ | `status = NOT_EVALUATED`, value = None |
| | `intent_ece` (Giới hạn trên) | $\le 0.10$ | `status = NOT_EVALUATED`, **KHÔNG PASS** |
| | `intent_brier` (Giới hạn trên) | $\le 0.15$ | `status = NOT_EVALUATED`, **KHÔNG PASS** |
| | `intent_ood_detection` | $\ge 0.90$ | `status = NOT_EVALUATED`, value = None |
| | `intent_far` (Giới hạn trên) | $\le 0.05$ | `status = NOT_EVALUATED`, **KHÔNG PASS** |
| | `intent_frr` (Giới hạn trên) | $\le 0.05$ | `status = NOT_EVALUATED`, **KHÔNG PASS** |
| **Retrieval (Truy xuất)** | `rag_recall_at_1` | $\ge 0.70$ | `status = NOT_EVALUATED`, value = None |
| | `rag_recall_at_3` | $\ge 0.80$ | `status = NOT_EVALUATED`, value = None |
| | `rag_recall_at_5` | $\ge 0.85$ | `status = NOT_EVALUATED`, value = None |
| | `rag_precision_at_3` | $\ge 0.30$ | `status = NOT_EVALUATED`, value = None |
| | `rag_mrr` | $\ge 0.75$ | `status = NOT_EVALUATED`, value = None |
| | `rag_ndcg_at_3` | $\ge 0.80$ | `status = NOT_EVALUATED`, value = None |
| **Grounding (Căn cứ & Bản nháp)**| `grounding_claim_grounding_rate` | $\ge 0.90$ | `status = NOT_EVALUATED`, value = None |
| | `grounding_citation_correctness` | $\ge 1.00$ | `status = NOT_EVALUATED`, value = None |
| | `grounding_hallucination_rate` | $\le 0.02$ | `status = NOT_EVALUATED`, **KHÔNG PASS** |
| | `grounding_abstention_rate` | $\ge 0.95$ | `status = NOT_EVALUATED`, value = None |

### 2.2. Trạng thái Chứng nhận (Certification Status)

Khi kết xuất báo cáo hệ thống (`report.md`), trạng thái chứng nhận tuân thủ bảng quyết định sau:

- `certified_live_acceptance`: Mọi gate bắt buộc đạt với bằng chứng `live` thực tế từ model và benchmark được phê duyệt.
- `simulated_mock_rejected`: Chạy bằng mock/simulated data; không được dùng làm bằng chứng production.
- `unverified_heuristic_rejected`: Chạy bằng fallback heuristic hoặc model chưa được hash/verify.
- `mixed_evidence_rejected`: Pha trộn bằng chứng giả lập hoặc heuristic vào lượt chạy live.
- `cached_report_no_new_execution`: Tổng hợp từ file benchmark có sẵn; không có suy luận mới.
- `pending_human_acceptance`: Các thành phần tự động đạt nhưng thiếu chấm claims thủ công từ con người.
- `failed_acceptance_criteria`: Một hoặc nhiều tiêu chí chất lượng bắt buộc không đạt ngưỡng.

---

## 3. Chỉ dẫn của Điều phối viên: Phân định AI Grading và Agent Simulation

Để đảm bảo tính khách quan và không tạo danh tính con người giả mạo:
1. **Chấm luận điểm bằng AI (`evaluator_type="ai"`)**:
   - Khi Coordinator hoặc LLM-as-judge thực hiện chấm claim theo rubric, kết quả được gắn nhãn minh bạch `evaluator_type: "ai"` cùng model và rubric version.
   - **Tuyệt đối không dùng AI grading để thỏa mãn gate `grounded_claims`** (yêu cầu con người chấm). Gate này giữ nguyên trạng thái `not_evaluated` hoặc `insufficient_evidence`.
   - Kết quả chấm AI được trình bày độc lập tại mục riêng: `AI-Graded Claims (Evaluator: AI)` với chỉ số `ai_grounded_claims`.
2. **Thực nghiệm đo thời gian bằng Agent (`study_type="agent_simulation"`)**:
   - Các kịch bản đo thời gian chạy tự động bởi Agent được gắn nhãn `study_type: "agent_simulation"`.
   - Gate giá trị sản phẩm (`product_value` / `user_study`) giữ nguyên `not_evaluated` để thể hiện trung thực rằng chưa có người dùng tham gia thực nghiệm đối chứng (counterbalance study).
   - Thời gian xử lý của agent được ghi nhận riêng dưới dạng `agent_simulation_timing`.

---

## 4. Kiểm toán Lệnh Benchmark Hiện hành (Benchmark Audit)

Qua rà soát mã nguồn `scripts/run_benchmarks.py`, phát hiện:
1. **Mô phỏng Phân loại Intent (`evaluate_intent_classification`)**:
   - Dùng biểu thức chính quy (regex) để khớp từ khóa cơ bản.
   - Khi không khớp từ khóa (dòng 156–173), mã nguồn gán `matched_intent = true_intent` (sao chép nhãn đúng) và gán độ tự tin cố định `raw_conf = 0.965`. Đây là suy luận giả lập (synthetic lookup), không phản ánh năng lực thực tế của model ML huấn luyện.
2. **Mô phỏng Đánh giá Grounding (`evaluate_grounding`)**:
   - Tại dòng 506–535, với mỗi ca hỗ trợ, mã nguồn gán danh sách claims tĩnh:
     ```python
     claims = [
         "Customer may return products within the specified policy window in original packaging.",
         "Refunds are processed after verification by authorized staff.",
     ]
     ```
   - Tự động cộng `grounded_claims += len(claims)` và gán `hallucination_rate = 0.0`. Không thực hiện sinh draft qua LLM và không có đối chiếu claim thực tế.

**Biện pháp kiểm soát:**
- Module `pipeline.evaluation.system_contracts` cung cấp hàm `audit_synthetic_benchmark(summary)` để phát hiện các dấu hiệu gán số liệu tĩnh này.
- `scripts/evaluate_regression.py` tự động kích hoạt audit: nếu phát hiện số liệu synthetic trong lượt chạy live, hệ thống sẽ cảnh báo `[AUDIT WARNING]` và hạ cấp `evidence_kind` xuống `simulated`, ngăn chặn việc cấp chứng nhận giả mạo.

---

## 5. Cấu trúc Manifest Chuẩn (IMP-11)

Mỗi lần chạy tạo một file `manifest.json` tuân thủ schema `EvaluationManifest`:

```json
{
  "schema_version": "v1.1",
  "run_id": "regression_20261112_063408Z_b5bed0e3",
  "created_at": "2026-11-12T06:34:08.634164+00:00",
  "git_commit": "5e0cda5cb24a79ff2d6892ab7abf611c3da054d5",
  "evidence_kind": "cached",
  "model_mode": "trained",
  "evaluator_type": "none",
  "study_type": "none",
  "execution_mode": "cached_only",
  "hashes": {
    "kb_hash": "AAA924C4B48DCD53A14269045B278B66F6E5E8AE9D1B614CD59B757102B78594",
    "split_hash": "C54C7EFCD2D363317A87344CD12C76791DB35EC17CA83A2E02B8FCB43F23150B",
    "model_hash": null
  },
  "counts": {
    "total_evaluated_metrics": 17
  },
  "metrics": {
    "grounding_hallucination_rate": {
      "metric": "grounding_hallucination_rate",
      "value": 0.01,
      "status": "PASS",
      "evidence_ref": "summary#grounding.hallucination_rate",
      "evidence_kind": "cached",
      "model_mode": "trained",
      "target": 0.02,
      "operator": "<="
    }
  },
  "all_mandatory_passed": true
}
```

---

## 6. Hướng dẫn Chạy Kiểm tra Hồi quy

### 6.1. Đánh giá từ file tóm tắt có sẵn (Chế độ Cached)
```bash
python scripts/evaluate_regression.py --current artifacts/evaluation/live-benchmarks/benchmark_summary.json --cached-only
```

### 6.2. So sánh hồi quy giữa 2 lần chạy
```bash
python scripts/evaluate_regression.py --current artifacts/evaluation/regression/runs/run_current/evaluation_result.json --baseline artifacts/evaluation/regression/runs/run_baseline/evaluation_result.json
```
*(Nếu hai lần chạy khác `kb_hash` hoặc `split_hash`, hệ thống sẽ gắn nhãn `comparable: false` và in cảnh báo cấu hình không tương thích thay vì báo cáo tụt lùi sai sự thật).*

### 6.3. Chạy đánh giá có AI Grading
```bash
python scripts/evaluate_regression.py --evaluator-type ai --study-type agent_simulation --cached-only
```
