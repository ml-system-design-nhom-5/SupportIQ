# SupportIQ Classifier Comparison Report: Transformers vs Baselines

- **Run ID:** `04-11-2026-06`
- **Mode:** `comparison`
- **Evaluation Date (UTC):** `2026-11-04T08:46:26.200796+00:00`
- **CPU Threads (Locked):** `4`
- **CV Winner (Locked):** `linear_svm__C=1.0` (Model: `linear_svm`)

## 1. Independent Hold-out Benchmark (Hold-out có bằng chứng độc lập)

Models in this section possess verified training split provenance demonstrating strict blind isolation from the SupportIQ test set.

| model_id | candidate_id | is_cv_winner | cv_macro_f1 | test_macro_f1 | test_accuracy | test_core_macro_f1 | latency_p50_ms | latency_p95_ms | throughput_items_sec |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| linear_svm | linear_svm__C=1.0 | True | 0.9902564545663207 | 0.9915905292073831 | 0.9914798206278027 | 0.9906310803323248 | 0.5079999991721706 | 0.8575699992434238 | 44715.37615191624 |
| logistic_regression | logistic_regression__C=10.0 | False | 0.9888739963081082 | 0.9901132733128755 | 0.9899850523168909 | 0.9884040440730343 | 0.5127000003994908 | 0.7312300014746141 | 44547.30540541067 |
| multinomial_nb | multinomial_nb__alpha=0.1 | False | 0.9836311537816853 | 0.9836454770072145 | 0.9835575485799701 | 0.9819786081041109 | 1.3280000002851011 | 1.445060000878584 | 38928.848402455136 |
| supportiq_distilbert | supportiq_distilbert | False | 0.9952684306823985 | 0.9954034527385439 | 0.9953662182361734 | 0.9942680469348778 | 16.303200000038487 | 19.44167999918136 | 101.36240977414971 |

## 2. Descriptive Results / Unverified Overlap Risk (Kết quả mô tả / Nguy cơ trùng dữ liệu)

> [!WARNING]
> **Unverified Training Split Overlap Risk:** The models below lack sample membership evidence proving hold-out independence from the Bitext test set. Their scores are purely descriptive and **must NOT be ranked or declared superior to independent baseline hold-out metrics**.

| model_id | origin | independence_status | test_macro_f1 | test_accuracy | test_core_macro_f1 | latency_p50_ms | latency_p95_ms | throughput_items_sec | training_samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| supportpilot_distilbert | external_finetuned | unverified | 0.9980852053871708 | 0.9980568011958146 | 0.997434368936578 | 16.14134999908856 | 18.605854998531868 | 99.18693447716329 | unknown |

## 3. Complete 5-Model Comparison Matrix (CPU)

| model_id | candidate_id | model_type | origin | independence_status | eligible_for_independent_ranking | is_cv_winner | cv_macro_f1 | test_macro_f1 | test_accuracy | test_weighted_f1 | test_core_macro_f1 | latency_p50_ms | latency_p95_ms | throughput_items_sec | training_samples | cv_protocol |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| linear_svm | linear_svm__C=1.0 | baseline | local_baseline_training | verified | True | True | 0.9902564545663207 | 0.9915905292073831 | 0.9914798206278027 | 0.9914859891443949 | 0.9906310803323248 | 0.5079999991721706 | 0.8575699992434238 | 44715.37615191624 | 37911 | 10-fold cross-validation |
| logistic_regression | logistic_regression__C=10.0 | baseline | local_baseline_training | verified | True | False | 0.9888739963081082 | 0.9901132733128755 | 0.9899850523168909 | 0.9899979457687228 | 0.9884040440730343 | 0.5127000003994908 | 0.7312300014746141 | 44547.30540541067 | 37911 | 10-fold cross-validation |
| multinomial_nb | multinomial_nb__alpha=0.1 | baseline | local_baseline_training | verified | True | False | 0.9836311537816853 | 0.9836454770072145 | 0.9835575485799701 | 0.9834965953031529 | 0.9819786081041109 | 1.3280000002851011 | 1.445060000878584 | 38928.848402455136 | 37911 | 10-fold cross-validation |
| supportiq_distilbert | supportiq_distilbert | transformer | local_finetuned | verified | True | False | 0.9952684306823985 | 0.9954034527385439 | 0.9953662182361734 | 0.9953641451558056 | 0.9942680469348778 | 16.303200000038487 | 19.44167999918136 | 101.36240977414971 | 37911 | 10-fold cross-validation |
| supportpilot_distilbert | supportpilot_distilbert | transformer | external_finetuned | unverified | False | False | nan | 0.9980852053871708 | 0.9980568011958146 | 0.9980565243608143 | 0.997434368936578 | 16.14134999908856 | 18.605854998531868 | 99.18693447716329 | unknown | none |

## 5. Invariants and Governance Rules

- **Winner Immutability:** The cross-validation winner (`linear_svm`) is permanently locked from 10-fold CV. Test set rankings do NOT override the CV selection.
- **Training Budget Parity:** Both baseline models and local Transformer (`supportiq_distilbert`) were evaluated using 10-fold CV on the full 37,911 development samples, establishing fair and directly comparable benchmarks.
- **Hardware Latency Parity:** All 5 models in the primary comparison matrix were benchmarked on the identical sequential CPU inference protocol (batch=1, locked thread count, tokenizer included, weights pre-loaded).
