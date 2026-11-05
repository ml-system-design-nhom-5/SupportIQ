# Đặc tả thiết kế Evaluation — SupportIQ

**Ngày:** 03/11/2026. **Trạng thái:** Đề xuất thiết kế, chờ duyệt; chưa có code Evaluation trong thay đổi này.

**Căn cứ:** [CHỦ ĐỀ 1](<../../CHỦ ĐỀ 1.md>), đặc biệt mục 2–4 và 6; [đặc tả Training](2026-11-03-pipeline-training-design.md); [yêu cầu chất lượng dữ liệu](../../data-quality.md); giao diện `IntentModelBundle` và manifest Training hiện tại. Đặc tả này không sửa đề bài và không khẳng định hệ thống đã đạt các mục tiêu.

## 1. Mục tiêu, phạm vi và lựa chọn thiết kế

Evaluation cung cấp bằng chứng độc lập về chất lượng mô hình đã chốt và hành vi sản phẩm. Phân biệt hai phạm vi:

* **ML:** benchmark các bundle đã refit trên hold-out test 46 intent, phân tích 12 intent sản phẩm, robustness và hiệu năng suy luận CPU hiện tại.
* **System:** đánh giá retrieval, LLM grounding, fallback/escalation, human oversight, reliability, end-to-end latency/cost và giá trị với nhân viên. Phạm vi này cần bộ tình huống, kết quả chạy backend và chấm thủ công; bundle classifier đơn lẻ không đủ chứng minh.

Chỉ đánh giá ML sẽ phù hợp code hiện tại nhưng thiếu bằng chứng cho nhiều yêu cầu đề bài. Chỉ đánh giá end-to-end khó xác định thành phần gây lỗi. **Phương án đề xuất là hai phạm vi dùng chung phiên bản dữ liệu và hợp đồng báo cáo**, có thể chạy riêng. Chưa có lựa chọn phạm vi được người dùng duyệt; các quyết định cụ thể dưới đây là đề xuất để xem xét.

Không fit mô hình, tìm lại tham số, chia lại test, sửa nhãn tự động, calibration hoặc tối ưu ngưỡng trong lần đánh giá cuối. Không tự phát hành mô hình, gửi trả lời khách hàng hoặc thực hiện giao dịch thật. Evaluation nhận thêm một giải pháp ML khác qua cùng hợp đồng khi nhóm hoàn thiện yêu cầu ở mục 2.1 đề bài; ba baseline truyền thống không tự chứng minh yêu cầu đó đã được đáp ứng.

## 2. Hiện trạng và hợp đồng đầu vào

`pipeline/evaluation/` hiện chỉ có `.gitkeep`. Training đã có bundle API `predict(texts)`, `predict_proba(texts)` và `decision_function(texts)`; hai API score có thể ném `AttributeError` nếu classifier không hỗ trợ. Không dùng `hasattr(bundle, "predict_proba")` để kết luận SVM có probability vì phương thức wrapper luôn tồn tại. Kiểm tra capability của classifier hoặc bắt lỗi capability tường minh, không che lỗi suy luận khác.

### Đầu vào ML bắt buộc

| Nguồn | Kiểm tra trước chạy |
| --- | --- |
| Training `manifest.json` | `schema_version` được hỗ trợ, `status=completed`, thời gian, preparation lineage, input/output checksums và selection có đủ trường. Lấy thư mục chứa manifest làm run root để resolve đường dẫn output tương đối. |
| `selection.json`, `candidate_summary.csv` | Khớp hash trong manifest và bản selection nhúng trong manifest; mỗi model được đánh giá phải là best candidate đã chốt. Winner không được thay đổi bởi test. |
| `models/<model-id>/bundle.joblib` và model card | Kiểm tra hash trước khi load joblib từ nguồn tin cậy; model/candidate ID, 46 nhãn và phiên bản dữ liệu/split phải khớp. Tính lại trạng thái đạt CV theo metrics từng model, không sao chép trạng thái winner. Nếu card mâu thuẫn, dừng và yêu cầu sửa Training. |
| Preparation manifest, `cleaned.csv`, `split_assignments.csv`, `split_report.json` | Đối chiếu hash với cả Preparation và Training; join ID one-to-one, không dư/thiếu, không null ID/nhãn/text. Nhãn hợp lệ và đủ 46 lớp; partition/fold đúng hợp đồng Training. Không tin riêng cờ `leakage_detected=false`. |

Tính lại khóa `get_near_duplicate_key`: nhóm không được giao train/test hoặc các fold development; không được khác nhãn. Đây là kiểm tra theo heuristic hiện có, không chứng minh đã loại mọi paraphrase cùng nghĩa. Đọc test bằng `partition="test"`, không lấy ngẫu nhiên tập mới. Không dùng `tfidf.joblib` từ Preparation để thay transformer trong bundle.

Đường dẫn tương đối do CLI cung cấp resolve từ repository root xác định tường minh. Manifest Preparation hiện có đường dẫn tuyệt đối: nếu đổi máy, cung cấp bản ánh xạ đường dẫn có lưu provenance; không bỏ qua hash hoặc tự tìm file cùng tên.

## 3. Dữ liệu và giao thức đánh giá phải khóa trước chạy

Giữ nguyên hold-out test và development do Preparation tạo. CV đã được dùng chọn cấu hình nên nhập điểm CV từ Training, không chạy lại tìm kiếm trong Evaluation. So sánh ba best bundle trên cùng test là benchmark mô tả; winner vẫn lấy từ CV. Không dùng kết quả test để thay winner rồi tiếp tục gọi test đó là kiểm chứng độc lập.

Bộ robustness và bộ tình huống hệ thống là hai nguồn riêng, version hóa trước khi xem kết quả. Người soạn/rà soát phải ghi mẫu nào dùng phát triển, mẫu nào giữ riêng đánh giá. Phát hiện gần trùng với development theo heuristic phải được ghi lại; case độc lập bị nhiễm phải được chuyển sang bộ phát triển trước khi khóa. Biến thể cố ý của test được giữ nhưng gắn `source_sample_id`, không coi là quan sát độc lập.

| File dự kiến dưới `data/evaluation/<suite-version>/` | Nội dung bắt buộc |
| --- | --- |
| `suite_manifest.json` | Version, purpose, ngôn ngữ, người duyệt, ngày khóa, hash file, nguồn tạo, `as_of`, tách dev/final, số case theo slice, phiên bản chính sách và dữ liệu mô phỏng. |
| `robustness.jsonl` | `case_id`, `slice`, `instruction`, `source_sample_id` nếu có, `gold_intent` hoặc null, `expected_action`, lý do gán nhãn và người duyệt. |
| `system_cases.jsonl` | `case_id`, request giả lập, customer/order ID giả lập khi cần, thời điểm kịch bản, intent tham chiếu, `answerable`, `relevant_sources` dạng cặp doc ID/version, `must_escalate`, expected action/reason và các assertion bắt buộc. |

Slices robustness: lỗi chính tả, paraphrase, Unicode/khoảng trắng, mơ hồ, nhiều ý, ngoài 12 intent nhưng thuộc 46 lớp, và ngoài toàn bộ 46 lớp. Hai loại ngoài phạm vi cuối khác nhau: classifier vẫn cần dự đoán đúng nhãn đã biết ngoài 12; routing phải chuyển xử lý. Không ép một nhãn 46 lớp cho câu thật sự OOD/nhiều ý/mơ hồ.

Mức bao phủ **đề xuất**: ít nhất 10 câu single-intent độc lập cho mỗi intent sản phẩm; ít nhất 20 case cho mỗi slice khó; ít nhất 5 case cho mỗi nhóm lỗi hệ thống. Ghi số case thực tế và mọi thiếu hụt; đây không phải ngưỡng gốc đề bài hoặc bằng chứng đại diện production. Hai nhóm phải thống nhất suite và điều kiện chạy trước benchmark chung.

## 4. Benchmark ML

1. Xác minh đầu vào, config và run ID mới; ghi hash, seed, môi trường và winner đã khóa.
2. Load ba bundle đã chọn, kiểm tra `classes_` tương ứng classifier; lập thứ tự nhãn chuẩn để xuất báo cáo. Không giả định các bundle có cùng thứ tự score.
3. Dự đoán cùng test bằng batch size cấu hình; lưu nhãn và lỗi từng mẫu. Không gọi `fit`/`fit_transform`; không cập nhật vocabulary, IDF hay classifier.
4. Tính metrics 46 lớp và 12 intent, nhập điểm CV tương ứng để phân biệt development/test. Lưu bảng benchmark không gắn winner mới theo test.
5. Chạy robustness đã khóa; nếu policy abstention chưa được định nghĩa, chỉ báo cáo khả năng classifier và ghi routing là `not_evaluated`.
6. Đo hiệu năng suy luận với giao thức ở mục 7; xác minh input hashes không đổi, lưu reports và manifest.

### Metrics và cách tính

* **46 lớp:** Macro-F1, weighted-F1, accuracy, per-class precision/recall/F1/support và confusion matrix 46×46, hàng=true/cột=predicted. Dùng danh mục chuẩn và `zero_division=0`. Cùng test và cùng mẫu lỗi cho mọi model.
* **12 intent:** lấy precision/recall/F1 theo nhãn từ toàn bộ dự đoán 46 lớp, rồi macro trung bình đúng 12 nhãn. Không lọc bỏ các nhãn khác trước khi tính precision vì sẽ mất false positive. Có thể thêm accuracy trên mẫu có gold thuộc 12, nhưng đặt tên và mẫu số rõ ràng.
* **Robustness single-intent:** accuracy, per-class F1 khi đủ support, tỷ lệ giữ nguyên dự đoán so với câu gốc và tỷ lệ còn đúng khi câu gốc đúng. Báo cáo support từng slice, không lấy Macro-F1 46 lớp với nhiều lớp không có mẫu để so trực tiếp test đầy đủ.
* **Mơ hồ/nhiều ý/OOD:** đo hành động mong đợi ở policy/system; không coi một dự đoán nhãn 46 lớp là phát hiện OOD thành công. Classifier không có abstention thì báo `unsupported` cho capability đó.
* Nếu policy đã khóa: `coverage = số case được trả lời / tổng case`, selective accuracy trên single-intent in-domain được trả lời; thêm tỷ lệ từ chối nhầm in-domain và tỷ lệ chấp nhận nhầm OOD. Không tối ưu coverage bằng cách bỏ case khó khỏi mẫu số.

Mục tiêu Macro-F1 ≥ 0,85 của đề bài áp dụng **10-fold CV**; test F1 là kết quả kiểm chứng cần báo cáo, chưa có ngưỡng test riêng được duyệt. Không tự chuyển 0,85 thành điều kiện pass test. Không khẳng định chênh lệch nhỏ giữa baseline có ý nghĩa thống kê chỉ từ bảng điểm.

## 5. Đánh giá retrieval và LLM

Để tách lỗi, chạy retrieval với intent tham chiếu (kiểm tra riêng retriever) và với intent dự đoán của winner (kiểm tra tích hợp); gắn tên hai chế độ, không trộn kết quả. Mỗi câu truy vấn có tập tài liệu đáp ứng đã chấm theo doc ID/version và `as_of`; chỉ tính nguồn liên quan và còn hiệu lực.

**Recall@3 theo query** = số nguồn đáp ứng đúng, còn hiệu lực trong top 3 chia cho tổng nguồn đáp ứng trong gold. Loại trùng doc ID/version khi các chunk cùng tài liệu xuất hiện nhiều lần, nhưng không kéo thêm kết quả từ ngoài top 3 để bù. Chỉ lấy trung bình trên query `answerable=true` có gold không rỗng. Nếu một query có hơn 3 nguồn gold, chỉ số có trần thấp hơn 1; bộ gold cần phản ánh đơn vị bằng chứng đã thống nhất. Báo riêng Hit@3 (ít nhất một nguồn đúng) và không đổi tên Hit@3 thành Recall@3. Mục tiêu Recall@3 ≥ 0,80 theo đề bài; lựa chọn định nghĩa nhiều nguồn này cần hai nhóm thống nhất trước chạy.

Query không đáp ứng được không vào mẫu số Recall@3; đánh giá riêng hành vi abstain/escalate khi không có nguồn, nguồn hết hiệu lực, mâu thuẫn hoặc thiếu thông tin. `is_active=true` không thay thế bằng chứng phê duyệt và khoảng hiệu lực.

Chạy LLM với KB, chỉ mục, prompt, model/provider/version, tham số sinh và ngữ cảnh nghiệp vụ đã khóa. Không dùng `response` Bitext làm gold chính sách. Câu trả lời có thể khác văn phong nên không dùng exact-match làm thước đo chính.

**Grounding:** người chấm tách bản nháp thành các khẳng định thực tế/chính sách nguyên tử và gán `supported`, `unsupported`, `contradicted` hoặc `unverifiable` so với ngữ cảnh thực sự được truy xuất. Chỉ `supported` vào tử số; ba nhóm còn lại đều ở mẫu số. Tỷ lệ = tổng supported / tổng khẳng định được chấm, mục tiêu ≥ 90%. Trích dẫn phải truy được đúng ID/version và có đoạn hỗ trợ; nguồn không hợp lệ hoặc citation giả không được coi là supported.

Không có khẳng định thì grounding là `N/A`, không phải 100%. Báo thêm tỷ lệ có câu trả lời hữu ích trên case answerable, tỷ lệ abstain và lỗi bỏ sót thông tin bắt buộc để tránh hệ thống chỉ từ chối mà đạt grounding. Hai người chấm độc lập các bản nháp của bộ test theo rubric; lưu bất đồng và kết quả phân xử trước tính điểm. LLM-as-judge nếu có chỉ hỗ trợ, không thay yêu cầu chấm thủ công của đề bài. Tổng số claim, draft và tỷ lệ đã chấm phải xuất hiện trong báo cáo.

## 6. Safety, oversight và reliability

Case hệ thống cần bao phủ: intent thấp tin cậy; 34 intent ngoài phạm vi sản phẩm; `human_agent`; nhiều ý/OOD; không có tài liệu; tài liệu cũ/mâu thuẫn; thiếu mã đơn; lỗi ML; LLM/API timeout/failure; hoàn tiền, tranh chấp và ngoại lệ chính sách.

* Mỗi case có `expected_action` (`draft_for_review`, `clarify`, `escalate`, `manual_fallback`) và reason code. Nếu `must_escalate=true`, chỉ escalation có bằng chứng đúng lý do mới pass; không coi clarify là thay thế escalation bắt buộc.
* Case nghiệp vụ nhạy cảm có thể cung cấp thông tin nhưng phải giữ quyết định cho nhân viên có thẩm quyền. Kiểm tra không có write nghiệp vụ tự động, không chỉ tìm từ khóa trong câu trả lời.
* Mỗi lần gửi trả lời cần audit event phê duyệt trước đó, cùng request/draft ID và hash nội dung đã duyệt; edit làm thay đổi bản nháp phải được duyệt lại. Test gọi gửi khi chưa duyệt phải bị chặn. Không suy ra 100% oversight chỉ từ không có lượt gửi nào.
* Fault injection dùng backend/test doubles có kiểm soát; kiểm tra cả hành động fallback, lý do audit, không có khẳng định thiếu căn cứ và không thực hiện giao dịch. Mỗi case bắt buộc pass; không dùng điểm trung bình cao để che một vi phạm guardrail.
* Các ngưỡng score phải được chọn trên bộ phát triển riêng hoặc OOF phù hợp trước đánh giá cuối, kèm version và evidence. Probability LR/NB chưa calibration và margin SVM không tương đương; không dùng chung ngưỡng 0,8 cho ba loại score. Nếu chưa có policy đã khóa, đánh giá safety liên quan confidence là chưa hoàn tất.

## 7. Latency, cost và giá trị sử dụng

**Classifier:** mặc định CPU, một process, batch=1 cho latency phục vụ; 20 request warm-up không tính điểm, ít nhất 1.000 request đo tuần tự lấy từ test theo thứ tự đã cố định và ghi cách lặp. Đo `perf_counter` quanh `bundle.predict`, gồm normalization/TF-IDF và classifier, không gồm load bundle. Báo load time riêng; thêm throughput batch=256 trên cùng test như chỉ số khác. Ghi p50/p95, mean, request count, lỗi, CPU/RAM, OS, thread settings và môi trường thư viện. Không so CPU với GPU nếu khác giao thức hoặc âm thầm fallback.

**End-to-end:** từ backend nhận request đến có bản nháp/chuyển xử lý sẵn cho nhân viên; không gồm thời gian con người duyệt. Đo riêng theo loại kết quả và lỗi. Cấu hình đề xuất ban đầu là concurrency=1, 20 warm-up và ít nhất 100 request; hai nhóm phải chốt cùng workload, concurrency, cache state, hạ tầng và timeout trước benchmark chung. Báo warm/cold và request cache hit riêng khi có. p95 ≤ 12 giây là mục tiêu end-to-end của đề bài, không dùng độ trễ classifier để chứng minh đạt. Timeout/lỗi phải có thời gian và tỷ lệ riêng, không bỏ khỏi báo cáo để p95 đẹp hơn.

**Chi phí:** ghi input/output tokens, số lần gọi/retry và đơn giá/currency/ngày giá được cấu hình hoặc chi phí thực từ provider. Chi phí trung bình/request = tổng chi phí tính được, gồm retry, chia tổng request thử nghiệm. Đơn giá chưa cung cấp thì `N/A`, không ghi 0; chi phí API không đồng nghĩa toàn bộ chi phí hạ tầng. Không cần gọi dịch vụ trả phí khi chỉ hiện thực bộ chấm từ kết quả đã xuất.

**Giá trị sản phẩm:** thiết kế so sánh thủ công với Copilot trên cùng bộ yêu cầu nhưng phân công đối trọng giữa người tham gia để giảm hiệu ứng nhớ; khóa kịch bản, tiêu chí hoàn thành, độ đúng và mốc thời gian trước chạy. Ghi người dùng ẩn danh, case, chế độ, thứ tự, thời gian xử lý, correctness và approve/edit/reject/escalate. Báo mean/median thời gian, thay đổi theo cặp khi hợp lệ và tỷ lệ quyết định; không tuyên bố tiết kiệm thời gian nếu chất lượng giảm mà không báo rõ. Chưa có người tham gia/bằng chứng thì ghi `not_evaluated`.

## 8. Giao diện kết quả hệ thống và chấm thủ công

System mode chấm từ trace JSONL xuất bởi backend hoặc test harness, không hard-code endpoint chưa có hợp đồng. Mỗi trace có `case_id`, attempt ID, request/draft ID, timestamp, predicted intent/score kind, action/reason, top-3 retrieval có ID/version/rank, context thực đưa LLM, draft, citation, backend errors, start/end timestamps, usage/cost data, policy/KB/index/prompt/model versions và audit/side-effect evidence theo case. Đơn hàng thật và PII không được đưa vào trace; dùng dữ liệu giả lập đã xác minh.

Trace và bảng chấm claim có schema version và hash ràng buộc vào đúng suite/system run/draft. Không chấp nhận điểm chấm từ bản nháp cũ sau khi chạy lại LLM. Một case thiếu hoặc trace trùng không xác định attempt phải làm run lỗi; nếu có retry, giữ mọi attempt và chọn final attempt theo quy tắc harness đã khóa, tính đủ latency/cost. Không coi thiếu trace là case pass hoặc loại case âm thầm.

`claim_annotations.csv` dự kiến có `case_id,draft_hash,claim_id,claim_text,cited_sources,reviewer_id,judgement,reason,adjudicated_judgement`. Nếu bảng chấm chưa đầy đủ, lưu kết quả phần máy và `pending_manual_review`; không phát hành kết luận grounding cuối.

## 9. Code và artifacts dự kiến

```text
pipeline/evaluation/
├── __init__.py
├── run_evaluation.py     # CLI: mode ml/system, xác minh, điều phối, trạng thái
├── evaluate_intent.py    # Hold-out metrics, 12 intent, robustness classifier
├── evaluate_system.py    # Chấm trace retrieval, hành động và grounding đã duyệt
├── benchmark.py          # Inference timing và tổng hợp end-to-end/cost
├── reporting.py          # CSV/JSON/Markdown, manifest và kết luận theo yêu cầu
└── README.md
pipeline/configs/evaluation.json
tests/unit/test_evaluation.py
artifacts/evaluation/<evaluation-run-id>/
├── config.resolved.json
├── environment.json
├── intent/<model-id>/    # predictions.csv, metrics.json, per_class.csv,
│                        # confusion_matrix.csv, robustness.csv, latency.json
├── baseline_comparison.csv
├── system/              # retrieval.csv, actions.csv, grounding.json, timing_cost.json
├── requirements_matrix.csv
├── report.md
├── run_state.json
└── manifest.json
```

Các file ứng với mode không chạy được bỏ qua và ghi rõ `not_evaluated` trong requirements matrix. Suite/annotations là đầu vào có version riêng, không tạo đáp án bằng chính model được đánh giá. Module nội bộ có thể điều chỉnh khi lập kế hoạch, không thêm framework benchmark hoặc phụ thuộc GPU trong phạm vi này. Dùng bộ thư viện pipeline hiện có và JSON config; `.gitignore` đã bỏ qua `/artifacts/evaluation/`.

CLI minh họa sau khi hiện thực, hiện chưa phải lệnh chạy được:

```powershell
python -m pipeline.evaluation.run_evaluation --mode ml --training-manifest artifacts/training/03-11-2026-00/manifest.json --suite data/evaluation/v1/suite_manifest.json --config pipeline/configs/evaluation.json --run-id 03-11-2026-eval-01
python -m pipeline.evaluation.run_evaluation --mode system --suite data/evaluation/v1/suite_manifest.json --traces artifacts/system-test/v1/traces.jsonl --annotations data/evaluation/v1/claim_annotations.csv --config pipeline/configs/evaluation.json --run-id 03-11-2026-eval-02
```

Manifest lưu mode, status, timestamps UTC, training/preparation/suite/system versions và hashes, winner đã khóa nếu là ML, environment, code revision/dirty state, seed/config hash, artifact paths/hashes và giới hạn của lần chạy. Chỉ mode ML bắt buộc Training manifest; system trace vẫn phải ghi model version và checksum bundle hoặc định danh model được triển khai. Không sửa manifest/card của Training để chèn điểm test.

## 10. Ma trận yêu cầu và kết luận

| Yêu cầu đề bài | Bằng chứng | Điều kiện kết luận |
| --- | --- | --- |
| ML quality | Nhập CV per-model; benchmark test 46 lớp và 12 intent | CV ≥ 0,85; test metrics báo riêng, không tự đặt ngưỡng test. |
| ML robustness | Suite slices và outcome từng case | Báo kết quả/support; đề bài chưa đặt F1 robustness tối thiểu. Các case escalation bắt buộc vẫn phải pass. |
| Retrieval | Recall@3 và mẫu số answerable theo gold | ≥ 0,80; sai/missing gold làm bộ chấm không hợp lệ. |
| LLM grounding | Claim annotations đã phân xử, citation/source checks | ≥ 90% supported claims; nếu mẫu số=0 hoặc chưa chấm xong thì chưa đánh giá. |
| Oversight và safety | Audit, negative send tests, side-effect evidence | 100% luồng gửi được duyệt; không tự giao dịch; mọi case bắt buộc escalation đúng. |
| Reliability | Fault cases và trace fallback | Tất cả case bắt buộc có phản ứng đúng, không khẳng định thiếu căn cứ. |
| Latency/cost | Timing protocol, p50/p95, error rate, usage | End-to-end p95 ≤ 12 giây theo điều kiện chung; chi phí phải báo, chưa có ngân sách pass/fail gốc. |
| Product value | Thử nghiệm nhân viên thủ công/Copilot | Báo thời gian và tỷ lệ quyết định cùng chất lượng; chưa có mức giảm thời gian bắt buộc. |

Tách **trạng thái thực thi** (`completed`, `failed`, `pending_manual_review`) khỏi **trạng thái từng yêu cầu** (`pass`, `fail`, `reported`, `not_evaluated`, `unsupported`). Metrics không có ngưỡng chỉ được `reported`, không tự pass. Mode ML completed không có nghĩa toàn hệ thống đạt yêu cầu. Bất kỳ guardrail fail đều chặn đề xuất release; thiếu bằng chứng guardrail không được coi là pass. Evaluation chỉ đưa khuyến nghị và giới hạn, quyết định phát hành thuộc quy trình Deployment và người có thẩm quyền.

## 11. Lỗi, phiên bản và kiểm thử nghiệm thu

Từ chối run ID đã tồn tại, không hỗ trợ overwrite. Kiểm tra inputs trước load bundle; giữ input hashes và đối chiếu lại cuối run. Ghi file qua tệp tạm, manifest completed cuối cùng; run thất bại không được consumer coi như báo cáo chính thức. Giữ chẩn đoán lỗi, không tự xóa run cũ. Không im lặng bỏ mẫu dự đoán lỗi: ML mode fail để sửa lỗi thực thi; system faults chủ đích là outcome phải chấm, khác lỗi schema của harness.

Các kiểm thử TDD bắt buộc khi hiện thực:

1. Từ chối checksum sai, run Training failed, nhãn/bundle không khớp, ID split dư/thiếu/trùng, group leakage và selection/card mâu thuẫn.
2. Spy bảo đảm không gọi fit, fit_transform hoặc chọn lại tham số; dự đoán đúng test IDs và không thay đổi winner khi model khác đạt test tốt hơn.
3. Tính metrics đúng trên ví dụ biết trước; giữ false positive ngoài 12 intent; cố định hàng/cột confusion matrix và score class order. SVM không bị báo là có probability.
4. Phân biệt OOD/nhiều ý với nhãn ngoài 12 nhưng trong 46; thiếu policy thì không tự nhận phát hiện OOD hoặc escalation đạt.
5. Recall@3 khác Hit@3 trên query nhiều nguồn, xử lý chunk trùng, tài liệu cũ, gold không rỗng và query unanswerable đúng mẫu số.
6. Grounding tính đủ unsupported/contradicted/unverifiable, không có claim là N/A; thiếu annotation hoặc draft hash sai không hoàn tất chấm. Dữ liệu đầy đủ nhưng thiếu nguồn hỗ trợ là kết quả fail, không làm mất case.
7. Audit approval phải khớp nội dung/phiên bản; send chưa duyệt bị chặn; case hoàn tiền không có side effect trái phép; escalation đúng reason và case fault đúng fallback.
8. Timing dùng clock giả để kiểm tra warm-up, percentiles, lỗi/timeout và cost gồm retries; price thiếu là N/A. Không chạy API thật trong unit test.
9. Run trùng không ghi đè; input thay đổi giữa run bị phát hiện; lỗi không có completed manifest; ML-only report không ghi system pass.
10. Integration smoke test trên fixture nhỏ đủ điều kiện cấu hình test, sau đó chạy benchmark trên dataset/suite thật; lưu output, điều kiện chạy và các mục chưa đo. Unit tests không tự chứng minh metrics production.

## 12. Nội dung cần duyệt trước hiện thực

Phạm vi hai mode, định nghĩa Recall@3 theo nhiều nguồn, mức bao phủ suite, giao thức latency và yêu cầu chấm hai người là các quyết định đề xuất. Cần thống nhất với hai nhóm trước benchmark chung. Chưa có bộ robustness/system suite đã duyệt, trace backend, bảng chấm hay kết quả Evaluation trong thay đổi tài liệu này; tuyệt đối không điền số liệu giả để hoàn thiện báo cáo.
