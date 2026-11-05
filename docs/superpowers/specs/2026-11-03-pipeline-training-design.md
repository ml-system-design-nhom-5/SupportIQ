# Đặc tả thiết kế Training — SupportIQ

**Ngày:** 03/11/2026. **Trạng thái:** Bản thiết kế chờ duyệt; chưa hiện thực Training.

**Căn cứ:** [Đề bài](<../../CHỦ ĐỀ 1.md>), [yêu cầu dữ liệu](../../data-quality.md), [thiết kế Preparation](2026-11-03-pipeline-preparation-design.md), Chương 11 và 15 trong `ai-for-production.zip`, cùng code Preparation hiện tại.

## 1. Mục tiêu và phạm vi

Huấn luyện và so sánh ba baseline ML truyền thống cho bài toán single-label intent classification: đầu vào là câu hỏi `instruction` tiếng Anh, đầu ra là một trong 46 `intent`. Cùng dữ liệu, đặc trưng và fold được dùng để so sánh công bằng; phân tích riêng 12 intent thuộc phạm vi sản phẩm.

Training tạo mô hình ứng viên và bằng chứng lựa chọn bằng cross-validation (CV). Evaluation độc lập đánh giá cuối trên hold-out test và bộ tình huống robustness. Training không sửa dữ liệu nguồn, chia lại fold, truy xuất KB, gọi LLM, triển khai dịch vụ hoặc tự phê duyệt release.

Mục tiêu đề bài là Macro-F1 ≥ 0,85 trên 10-fold CV. Kết quả dưới mục tiêu vẫn phải được lưu trung thực; không điều chỉnh test để đạt chỉ tiêu. Ba baseline này không tự chứng minh đã hoàn thành yêu cầu về một giải pháp ML bổ sung của đề bài; nhóm cần xác nhận phạm vi giải pháp đó riêng.

## 2. Phương án đã chọn

* **Tham số cố định:** chi phí thấp, nhưng kết quả phụ thuộc một lựa chọn tham số ban đầu.
* **Tìm kiếm tham số nhỏ — đã thống nhất:** ba giá trị cho mỗi thuật toán, cùng 10 fold. Chi phí dự kiến 90 lượt fit classifier cho CV và 3 lượt refit sau lựa chọn.
* Tìm kiếm rộng hoặc nested CV chưa nằm trong phạm vi prototype. CV dùng chọn cấu hình có thể lạc quan; test giữ riêng là kiểm chứng cuối cho lựa chọn đã khóa.

### Thuật toán và cấu hình

| ID | Estimator | Giá trị tìm kiếm | Cấu hình cố định đề xuất |
| --- | --- | --- | --- |
| `multinomial_nb` | `MultinomialNB` | `alpha: [0.1, 0.5, 1.0]` | `fit_prior=True` |
| `logistic_regression` | `LogisticRegression` | `C: [0.1, 1.0, 10.0]` | `solver="lbfgs"`, `max_iter=2000`, `tol=1e-4`, `class_weight=None` |
| `linear_svm` | `LinearSVC` | `C: [0.1, 1.0, 10.0]` | `dual="auto"`, `max_iter=5000`, `tol=1e-4`, `class_weight=None`, `random_state=42` |

Các cấu hình cố định là quyết định thiết kế đề xuất, chưa phải kết quả thực nghiệm. Ghi chính xác phiên bản scikit-learn thực chạy và các tham số đã resolve; không dựa vào default thay đổi giữa phiên bản.

TF-IDF giữ cùng cấu hình Preparation: word n-gram `(1, 2)`, `max_features=10000`, `min_df=2`, `sublinear_tf=True`, `lowercase=True`, `token_pattern` lấy từ `IntentFeaturePipeline`. Chuẩn hóa Unicode NFKC và khoảng trắng bằng tiện ích hiện có. Không bỏ dấu câu trong văn bản đặc trưng chỉ vì khóa near-duplicate bỏ dấu câu; hai phép biến đổi có mục đích khác nhau. Không tìm kiếm cấu hình TF-IDF trong vòng thí nghiệm này.

## 3. Hiện trạng tích hợp

Preparation đã sinh `cleaned.csv`, `split_assignments.csv`, `split_report.json`, `manifest.json` và `tfidf.joblib`. Các cột assignments hiện tại là `sample_id,partition,fold`; `partition="train"` thực chất là **development**, test có `partition="test", fold=-1`. Development dùng fold `0..9` cho cấu hình 10 fold.

Manifest Preparation `03-11-2026-02` ghi 44.601 mẫu sạch, 37.911 development và 6.690 test. Đây là ví dụ đầu vào đang có, không hard-code số mẫu hoặc ID phiên bản vào thuật toán Training.

**Không dùng TF-IDF đã fit từ Preparation để đánh giá CV.** Artifact đó đã học vocabulary và IDF trên toàn development, bao gồm các fold validation. Training tạo transformer mới cho từng fold. Sau lựa chọn, transformer cuối được fit lại trên toàn development và lưu cùng classifier; không ghi đè artifact Preparation.

`IntentFeaturePipeline` hiện chưa kế thừa `BaseEstimator`/`TransformerMixin`; các phương thức fit cũng chưa nhận `y`. Thiết kế chọn vòng lặp CV tường minh và khởi tạo mới transformer/estimator, không giả định có thể đưa ngay đối tượng này vào `GridSearchCV` hoặc sklearn Pipeline.

## 4. Hợp đồng đầu vào và kiểm tra trước chạy

CLI dự kiến nhận `--preparation-manifest`, `--config`, `--run-id` và `--output-root`. Đường dẫn tương đối của CLI được tính từ gốc repository xác định tường minh, không phụ thuộc vị trí thư mục script. Đường dẫn tuyệt đối hiện có trong manifest được hỗ trợ; khi chuyển workspace phải cung cấp manifest đã ánh xạ đúng vị trí và kiểm tra checksum.

| Đầu vào | Yêu cầu |
| --- | --- |
| Manifest Preparation | Có `run_id`, `metadata.dataset_version`, `metadata.split_version` và đường dẫn artifacts cần dùng. |
| `cleaned.csv` | Có `sample_id`, `instruction`, `intent`, `category`; ID duy nhất, trường bắt buộc không rỗng, nhãn thuộc taxonomy chuẩn và có đủ 46 intent. |
| `split_assignments.csv` | ID duy nhất, bao phủ chính xác ID dữ liệu sạch, không dư/thiếu; partition chỉ là train/test. Join one-to-one, không dùng inner join âm thầm loại mẫu. |
| `split_report.json` | Có `cleaned_sha256`, `splits_sha256`; tính lại cả hai và đối chiếu trước huấn luyện. Metadata và số lượng phải khớp dữ liệu thực tế. |
| Cấu hình | Đúng schema, tên model được hỗ trợ, grid không rỗng, `alpha/C > 0`, tham số và kiểu giá trị hợp lệ. |

Tính lại khóa nhóm bằng `get_near_duplicate_key`; dừng nếu một nhóm khác nhãn hoặc nằm ở nhiều partition/fold. Kiểm tra test có fold -1, development có đúng 10 fold không rỗng `0..9`, đủ 46 nhãn trong phần train và validation của từng fold và trong test. Không tự giảm số fold, bỏ lớp, sửa nhãn hoặc chia lại khi không đạt; trả lỗi để xử lý tại Preparation.

Training được đọc test ở bước xác minh ID, nhãn, nhóm và checksum; không fit/transform đặc trưng test, dự đoán test, tính test metrics hay sử dụng phân bố test để chọn tham số. Chưa có bằng chứng kiểm tra ngữ nghĩa toàn bộ dữ liệu chỉ từ schema hợp lệ hoặc nhóm không giao nhau.

## 5. Luồng huấn luyện và lựa chọn

1. Xác minh đầu vào và cấu hình; cấp run ID mới, từ chối nếu thư mục run đã tồn tại. Chụp cấu hình resolved, checksum, nguồn code và môi trường.
2. Với mỗi fold `k=0..9`, lấy development `fold != k` làm train và `fold == k` làm validation. Không dùng hold-out test.
3. Tạo `IntentFeaturePipeline` mới; `fit_transform` trên instruction train và `transform` trên instruction validation. Có thể dùng lại hai ma trận sparse cho 9 cấu hình trong cùng fold; không dùng cache từ fold khác. Không chuyển ma trận sang dense.
4. Khởi tạo classifier mới cho từng cấu hình, fit trên nhãn train, dự đoán validation. Ghi metrics, cảnh báo hội tụ và thời gian fit/transform/predict theo từng fold. Không tái sử dụng classifier đã fit ở lượt khác.
5. Tổng hợp 10 fold cho mỗi cấu hình. Lưu mean và standard deviation (`ddof=0`) của Macro-F1, accuracy, weighted-F1; Macro-F1 dùng danh mục 46 nhãn cố định với `zero_division=0`.
6. Chọn cấu hình tốt nhất cho từng thuật toán theo mean Macro-F1; sau đó chọn winner giữa ba cấu hình tốt nhất. So sánh điểm làm tròn 6 chữ số; nếu bằng nhau, ưu tiên std nhỏ hơn, rồi thứ tự cấu hình cố định trong config. Ghi đầy đủ quy tắc và tie-break; thời gian chạy là chỉ số tham khảo, không làm lựa chọn thay đổi giữa các máy.
7. Tạo báo cáo OOF cho cấu hình tốt nhất của từng thuật toán. Mỗi mẫu development có đúng một dự đoán từ mô hình chưa thấy mẫu/nhóm đó khi fit. Tính per-class precision/recall/F1/support, confusion matrix 46×46, phân tích 12 intent và các cặp dễ nhầm.
8. Fit một TF-IDF mới trên toàn development, sau đó refit ba cấu hình tốt nhất trên cùng ma trận development. Lưu ba bundle để Evaluation có thể so sánh công khai; winner đã được khóa bằng CV, không đổi theo test.
9. Load lại từng bundle để smoke test preprocessing và dự đoán. Xác minh checksum đầu vào chưa đổi trong lúc chạy, ghi checksum đầu ra và hoàn tất manifest với `status="completed"`.

Macro-F1 trung bình theo fold là chỉ số chọn mô hình. Macro-F1 gộp từ OOF là thống kê riêng, không thay thế chỉ số đó. Với 12 intent, ghi precision/recall/F1 theo nhãn và macro trung bình của đúng 12 nhãn trên OOF **46 lớp**; không bỏ mẫu ngoài 12 intent trước khi tính precision, tránh mất false positive từ các lớp khác.

SVM cung cấp `decision_function`, không có `predict_proba`. LR/NB có xác suất đầu ra nhưng chưa được coi là confidence đã hiệu chuẩn. Thiết kế này chưa chọn ngưỡng abstention, chưa calibration và chưa đánh giá phát hiện ngoài phạm vi. Các bước đó cần giao thức validation riêng, tuyệt đối không tối ưu trên hold-out test.

## 6. Cấu trúc code và cấu hình dự kiến

```text
pipeline/
├── training/
│   ├── __init__.py
│   ├── run_training.py    # CLI, xác minh dữ liệu, điều phối và manifest
│   ├── models.py          # Factory cho ba classifier và grid hợp lệ
│   ├── cross_validate.py  # Vòng lặp fold, metrics, lựa chọn và OOF
│   ├── artifacts.py       # Bundle inference, lưu/load và checksum
│   └── README.md          # Cách chạy, hợp đồng đầu vào và đầu ra
└── configs/
    └── training.json      # TF-IDF, grids, 10 fold, seed 42, mục tiêu 0.85
tests/unit/test_training.py
```

Sử dụng pandas/numpy/scikit-learn/joblib hiện có; cấu hình JSON để không cần thêm thư viện YAML. Chi tiết tách hàm nội bộ do người hiện thực quyết định; không thêm framework orchestration hoặc experiment server trong phạm vi này.

CLI minh họa sau khi hiện thực (hiện chưa chạy được):

```powershell
python -m pipeline.training.run_training --preparation-manifest artifacts/preparation/03-11-2026-02/manifest.json --config pipeline/configs/training.json --run-id 03-11-2026-training-01
```

Chạy tuần tự mặc định để hạn chế bộ nhớ; không đặt song song không giới hạn. Nếu tối ưu sau, phải giữ nguyên fold và lựa chọn, đồng thời ghi mức song song và phần cứng vào manifest.

## 7. Artifacts và giao diện suy luận

```text
artifacts/training/<training-run-id>/
├── config.resolved.json
├── environment.json
├── fold_metrics.csv
├── candidate_summary.csv
├── selection.json
├── oof_predictions.csv
├── reports/<model-id>/
│   ├── per_class_metrics.csv
│   ├── confusion_matrix.csv
│   └── core_intent_metrics.json
├── models/<model-id>/
│   ├── bundle.joblib
│   └── model_card.json
└── manifest.json
```

* `fold_metrics.csv`: candidate/model ID, tham số, fold, số mẫu train/validation, metrics, thời gian, trạng thái và cảnh báo. Mỗi cấu hình hợp lệ có đủ 10 hàng fold.
* `candidate_summary.csv`: đủ 9 cấu hình, mean/std metrics và eligibility; không loại im lặng kết quả thấp.
* `selection.json`: best candidate từng thuật toán, winner, quy tắc tie-break, CV metrics, mục tiêu và `meets_cv_target`. Không gắn nhãn production-ready chỉ từ CV.
* `oof_predictions.csv`: `sample_id,fold,y_true,y_pred,model_id,candidate_id`; chỉ giữ cấu hình tốt nhất mỗi thuật toán. Không cần sao chép văn bản hoặc response.
* `bundle.joblib`: một đối tượng có API ổn định chứa feature transformer đã fit, classifier đã refit, danh mục `classes_` và thông tin phiên bản. `predict(texts)` nhận chuỗi câu hỏi dạng batch và trả nhãn; `decision_function`/`predict_proba` chỉ cung cấp khi classifier hỗ trợ. Mapping điểm số theo thứ tự `classes_`, không theo thứ tự set taxonomy.
* Bundle phải xử lý NFKC/khoảng trắng ở đường suy luận qua transformer dùng chung. Không yêu cầu caller chuẩn hóa trước. Chỉ load joblib từ nguồn artifact tin cậy.
* `model_card.json`: model/candidate, phạm vi tiếng Anh, 46 nhãn, dữ liệu và phiên bản split, metrics CV, giới hạn dữ liệu tổng hợp, trạng thái calibration và yêu cầu Evaluation trước release.
* `manifest.json`: `schema_version`, run ID, thời gian UTC, status, preparation run ID, dataset/split version, seed, config hash, hash từng đầu vào/đầu ra, Git revision và trạng thái dirty, Python/thư viện, phần cứng và selection. `environment.json` ghi phiên bản thư viện thực tế; không chỉ chép các ràng buộc `>=` trong requirements.

Mọi artifact Training nằm dưới run ID riêng, không dùng chung `artifacts/models/<preparation-run-id>/`. Khi hiện thực cần thêm `/artifacts/training/` vào `.gitignore`; không commit mô hình hoặc báo cáo sinh từ dữ liệu. Hash và phiên bản môi trường hỗ trợ tái lập; không cam kết byte-identical giữa máy hoặc phiên bản thư viện khác nhau.

## 8. Xử lý lỗi và bảo toàn phiên bản

* Không có `--overwrite` cho Training. Run ID đã tồn tại phải bị từ chối trước khi ghi; rerun dùng ID mới. Không sửa artifact Preparation.
* Lỗi đầu vào, lỗi fit, vocabulary rỗng, fold thiếu lớp, NaN metrics hoặc `ConvergenceWarning` chưa xử lý làm run failed; không âm thầm bỏ fold/cấu hình để chọn winner. Ghi thông tin lỗi khi có thể và không tạo manifest completed hoặc model được phép bàn giao.
* Ghi trạng thái running/failed/completed rõ ràng. Tệp đầu ra ghi qua tệp tạm rồi thay thế trong thư mục run; manifest completed được ghi cuối. Consumer chỉ nhận run completed có checksum hợp lệ. Thư mục run lỗi được giữ để chẩn đoán, không tái dùng ID đó.
* Dưới mục tiêu 0,85 là run hoàn tất nhưng `meets_cv_target=false`, được lưu để phân tích, chưa đủ điều kiện đề xuất release. Cần phân biệt thất bại thực thi với không đạt mục tiêu chất lượng.

## 9. Kế hoạch kiểm thử và tiêu chí nghiệm thu

Hiện thực theo TDD với dữ liệu nhỏ tổng hợp; smoke test không thay thế thí nghiệm trên 46 intent thực tế.

| Nhóm kiểm thử | Bằng chứng cần có |
| --- | --- |
| Hợp đồng dữ liệu | Từ chối ID trùng/dư/thiếu, checksum sai, partition/fold sai, thiếu lớp hoặc giao nhóm giữa tập/fold. Dùng cấu hình lớp/fold nhỏ cho unit test, cấu hình thật vẫn yêu cầu 46 lớp/10 fold. |
| Chống rò rỉ đặc trưng | Từ chỉ có trong validation không vào vocabulary của fold đó; transformer không fit trên test; cùng nhóm gần trùng khác dấu câu không vượt ranh giới. |
| Tìm kiếm và metrics | Đủ 9×10 lượt classifier, mean/std đúng, tie-break ổn định, OOF bao phủ đúng một lần/mẫu/model, confusion matrix đúng thứ tự nhãn. |
| Khóa test | Thay đổi riêng nội dung test, giữ nguyên development và cập nhật checksum tương ứng trong fixture, không làm đổi CV scores hoặc selection; không gọi predict/transform test. |
| Refit và serialization | Mô hình cuối fit toàn development; load lại dự đoán giống trước lưu; văn bản fullwidth và dạng thường cho đặc trưng tương đương; score order khớp classes và SVM không giả lập probability. |
| Phiên bản và lỗi | Từ chối run trùng không làm đổi file cũ; lỗi hội tụ/fit không tạo completed manifest; artifact lỗi checksum không được consumer chấp nhận. |
| Chạy thực tế | Báo cáo đủ 46 lớp/10 fold, ba cấu hình tốt nhất được refit, test chưa được dùng cho lựa chọn; lưu thời gian/bộ nhớ quan sát thay vì đặt SLA chưa đo. |

Nghiệm thu Training khi hợp đồng đầu vào, chống leakage, lựa chọn, refit, serialization và manifest được kiểm thử; không đòi metrics giả định đạt trước khi chạy. Evaluation tiếp nhận ba bundle, selection đã khóa, hash dữ liệu/split và báo cáo CV để đánh giá test/robustness. Mọi quyết định tiếp tục tuning sau khi xem test phải được công khai; test đó không còn là kiểm chứng độc lập cho vòng điều chỉnh mới.

## 10. Các quyết định cần duyệt

Đã thống nhất ba baseline và tìm kiếm nhỏ 3 giá trị/thuật toán. Bản thiết kế đề xuất thêm: JSON config, vòng lặp CV tường minh, dừng run khi lỗi hội tụ, lưu cả ba mô hình refit, tie-break xác định và run ID không được ghi đè. Phê duyệt tài liệu là bước trước khi lập kế hoạch hiện thực; chưa có thay đổi code Training trong công việc này.

## Tài liệu tham khảo thuật toán

* [MultinomialNB](https://scikit-learn.org/stable/modules/generated/sklearn.naive_bayes.MultinomialNB.html): baseline Naive Bayes cho đặc trưng không âm; tài liệu nêu TF-IDF cũng có thể dùng.
* [LogisticRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html): phân loại tuyến tính hỗ trợ đầu vào sparse và dự đoán xác suất.
* [LinearSVC](https://scikit-learn.org/stable/modules/generated/sklearn.svm.LinearSVC.html): SVM tuyến tính cho phân loại nhiều lớp; cần phân biệt decision score với probability.
