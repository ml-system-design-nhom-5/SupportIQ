# Traditional Baseline Reproducibility & ML Comparison Report (`2026-11-13`)

> [!IMPORTANT]
> **New Reproducibility Run Disclosure (Not Reconstructed History):** Run `13-11-2026-00` (`TF-IDF + LogisticRegression`, `C=20.0`) is a **fresh CPU-only reproducibility run** executed via `pipeline/training/run_training.py` at commit `4a13ac28718263d72b23a785e070fa021adee089`. Historical `artifacts/training/03-11-2026-01/` already retains `21/24` root-verified SHA-256 reports (`manifest.json`, `fold_metrics.csv`, `oof_predictions.csv`, `per_class_metrics.csv`, `confusion_matrix.csv`, `top_confusions.csv`, `core_intent_metrics.json`, `model_card.json`), while its 3 `.joblib` bundles were absent on disk (`.gitignore:79` ignores `/artifacts/**/*.joblib`). No historical weights were fabricated, no serving weights or frozen gold were modified, and `0` GPU / `0` LLM provider calls were executed.

## 1. Provenance & Serialized Bundle Inventory (`13-11-2026-00`)

| Item | Value / Path | SHA-256 / Verification |
| :--- | :--- | :--- |
| **Dataset (`cleaned_csv`)** | Frozen Bitext `03-11-2026-02` (`44,601` rows, `46` intents: `37,911` train/dev + `6,690` test; sourced from sibling `supportiq-final-routing/data/datasets/processed/03-11-2026-02/cleaned.csv`) | `8BC10CFA056371BDECB3394BFD4C75EEE7E10022ACE5071833ECD140B2D75846` (matches `03-11-2026-01/manifest.json`) |
| **Split (`split_assignments`)** | Frozen Bitext `03-11-2026-02` (`10` near-duplicate-grouped dev folds + test `-1`) | `1D366E898F6BA68BE46C5CA0F9059E9862FAD1D7BAFE350D9CDD310DD3E0A04C` (matches `03-11-2026-01/manifest.json`) |
| **Split Report (`split_report`)** | `artifacts/preparation/03-11-2026-02/split_report.json` | `BDAEF5C2699384A2A76AA5BC4C98C32D7423FF1AF425AA90E630512437448C56` |
| **Config (`config.json`)** | `artifacts/evaluation/traditional_baseline_repro_20261113/config.json` (`seed=42`, `n_folds=10`, TF-IDF `(1,2)`, `max_features=10000`, `min_df=2`, `sublinear_tf=True`, `LogisticRegression(C=20.0, solver='lbfgs', max_iter=2000)`) | File: `7A4911C397B9904D0054A5AB7B82BD95D74031EADF13CB1185B8FF313AF1C167` / Normalized `config_hash`: `7955C9B0BBCB422E6AD309D7B5194C763B49E5B5BC3AD593E66FDD575AC1C661` |
| **Runtime & Commit** | Python `3.12.14`, `scikit-learn 1.9.1`, `pandas 3.1.0`, `numpy 2.5.4`, `scipy 1.18.1`, `joblib 1.6.0`, CPU (`CUDA_VISIBLE_DEVICES=""`) | Git base: `4a13ac28718263d72b23a785e070fa021adee089` |
| **Run Manifest** | `artifacts/evaluation/traditional_baseline_repro_20261113/run/13-11-2026-00/manifest.json` | **`12/13` outputs present & SHA-256 verified** (11 committed + local `bundle.joblib`); `oof_predictions.csv` (`991A1C85...`) verified `13/13` pre-commit, then deleted before `a7e9cfe` (**absent on disk**) |
| **Serialized Bundle (Local / Gitignored)** | `artifacts/evaluation/traditional_baseline_repro_20261113/run/13-11-2026-00/models/logistic_regression/bundle.joblib` (`3,815,518` B; excluded from git per `.gitignore:79`) | `6147AE24DE380B62CA6843063E2809BDE54FBB9F65681288035D4AA2BF31757D` |
| **OOF Alignment vs `03-11-2026-01`** | `run/13-11-2026-00/oof_predictions.csv` (`3,667,533` B, `991A1C85...`, deleted pre-commit; not byte-identical to 3-model `03-11-2026-01/oof_predictions.csv`, manifest `1A09AD4B...` / worktree CRLF-LF `8211E2DC...`) | Verified pre-deletion that `sample_id`, `fold`, and `y_pred` matched `03-11-2026-01` `logistic_regression` **37,911 / 37,911 (`True` / `True` / `True`)** |

## 2. 10-Fold Cross-Validation & Hold-Out Comparison vs Chosen ML (`distilbert-supportiq`)

All OOF metrics below are computed on the **exact same `37,911` aligned samples and identical `10` folds** (`0..9`):

| Model | Provenance Status | 10-Fold Mean Macro-F1 | Fold Std (ddof=0 / ddof=1) | Global OOF Macro-F1 | OOF Accuracy | Core-12 OOF Macro-F1 | OOF Errors (/37,911) | Hold-Out `6,690` Test Macro-F1 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **`logistic_regression__C=20.0` (`13-11-2026-00`)** | **New repro run (`bundle.joblib` SHA verified)** | **0.989220** | 0.001437 / 0.001515 | **0.989221** | **0.989106** | **0.986016** | **413** | **0.990252** (`acc=0.990135`, `core12=0.988119`, `0.0805s` CPU) |
| `linear_svm__C=1.5` (`03-11-2026-01`) | Historical reports `ROOT_OK` (`bundle.joblib` absent) | 0.990258 | 0.000883 / — | 0.990257 | 0.990161 | — | — | `0.991591` (`C=1.0`, historical `04-11-2026-06`) |
| `multinomial_nb__alpha=0.03` (`03-11-2026-01`) | Historical reports `ROOT_OK` (`bundle.joblib` absent) | 0.984203 | 0.001232 / — | 0.984204 | 0.984094 | — | — | `0.983645` (`alpha=0.1`, historical `04-11-2026-06`) |
| **`distilbert-supportiq` (`distilbert_cv`, Chosen ML)** | Cached OOF (`training_report.json` + `oof_predictions.csv`; per-fold checkpoints absent) | **0.995268** | 0.000999 / 0.001053 | **0.995271** | **0.995226** | **0.993887** | **181** | `0.995403` (`acc=0.995366`, `core12=0.994268`, historical `04-11-2026-06`) |

- **Bitext 10-Fold Gate (`>= 0.85`):** Both traditional `TF-IDF + LogisticRegression` (`0.989220`) and chosen ML `distilbert-supportiq` (`0.995268`) pass `>= 0.85`; `distilbert-supportiq` reduces OOF errors by **56.2%** (`413 -> 181`, `+0.006048` fold-mean Macro-F1, `+0.007871` Core-12 F1). Note that real application coverage remains bounded by domain shift (`ml_noise` clean `0.7858`, live/offline answerable drafting `4/12`), separate from Bitext CV.

## 3. Per-Class F1 & Confusion Matrix Comparison (46 Intents)

Full 46-class table: [`per_class_comparison_46.csv`](per_class_comparison_46.csv); full 46x46 LR confusion matrix: [`confusion_matrix.csv`](run/13-11-2026-00/reports/logistic_regression/confusion_matrix.csv) (`SHA256: C93C2C7E...`, identical to `03-11-2026-01`).

### Core-12 In-Scope Product Intents (37,911-Row 10-Fold OOF)

| Intent | Support | LR (`13-11-2026-00`) F1 | DistilBERT (`distilbert_cv`) F1 | Delta (DB - LR) |
| :--- | ---: | ---: | ---: | ---: |
| `track_order` | 836 | 0.948986 | 0.963737 | +0.014751 |
| `return_policy` | 838 | 0.970357 | 0.981314 | +0.010957 |
| `return_product` | 842 | 0.973964 | 0.992899 | +0.018935 |
| `refund_status` | 847 | 0.981689 | 0.998230 | +0.016541 |
| `refund_policy` | 842 | 0.988180 | 0.998220 | +0.010040 |
| `cancel_order` | 839 | 0.990453 | 0.998215 | +0.007762 |
| `delivery_time` | 781 | 0.993582 | 0.999359 | +0.005778 |
| `human_agent` | 842 | 0.995851 | 0.999406 | +0.003555 |
| `shipping_costs` | 824 | 0.996355 | 0.999393 | +0.003038 |
| `request_refund` | 808 | 0.996912 | 1.000000 | +0.003088 |
| `delivery_issue` | 846 | 0.997633 | 0.997050 | -0.000583 |
| `payment_issue` | 846 | 0.998230 | 0.998817 | +0.000586 |

- **Lowest 5 F1 Intents (All 46 Classes):** `track_order` (`0.948986` LR vs `0.963737` DB), `track_delivery` (`0.955620` vs `0.969382`), `submit_product_feedback` (`0.968546` vs `0.992303`), `return_policy` (`0.970357` vs `0.981314`), `return_product` (`0.973964` vs `0.992899`).

### Top-10 Confusion Pairs (`y_true -> y_pred`, OOF N=37,911)

| Rank | LR Repro (`13-11-2026-00`, Total=413 errors) | Count | DistilBERT (`distilbert_cv`, Total=181 errors) | Count |
|---:|---|---:|---|---:|
| 1 | `track_order -> track_delivery` | 52 | `track_order -> track_delivery` | 48 |
| 2 | `close_account -> change_account` | 18 | `return_policy -> return_product_online` | 15 |
| 3 | `damaged_delivery -> wrong_item` | 17 | `damaged_delivery -> wrong_item` | 14 |
| 4 | `submit_product_feedback -> submit_feedback` | 17 | `change_account -> close_account` | 11 |
| 5 | `return_product_online -> return_product` | 15 | `wrong_item -> damaged_delivery` | 9 |
| 6 | `change_account -> close_account` | 14 | `close_account -> change_account` | 8 |
| 7 | `submit_product_idea -> submit_product_feedback` | 13 | `return_policy -> return_product_in_store` | 6 |
| 8 | `wrong_item -> damaged_delivery` | 12 | `track_delivery -> track_order` | 4 |
| 9 | `return_policy -> refund_policy` | 12 | `return_product_online -> return_product` | 4 |
| 10 | `refund_status -> track_delivery` | 11 | `return_product_in_store -> return_policy` | 4 |

## 4. Reproducibility & Portability Closure Note

- **Retained Preparation Manifest (Byte-Exact Copy):** [`prep_manifest_03_11_2026_02.json`](prep_manifest_03_11_2026_02.json) (`631` bytes, SHA-256 `BBC17872A8618C73505F545F46F435FF987892AF529C14F6603F6DC7075CCEAF`) is a byte-identical copy of the runtime `preparation.manifest_path` (`C:\Users\PC\.gemini\antigravity-cli\brain\05bc2d2c-9473-4c1e-bb3f-d319d727c241\scratch\prep_manifest_03_11_2026_02.json`), preserved unmodified before scratch cleanup so `run/13-11-2026-00/manifest.json` (`inputs.preparation_manifest`) remains verifiable without rewriting run hashes.
- **Immutable External Path Mapping:** The retained manifest records the exact external paths read during `13-11-2026-00`, pinned by SHA-256 in both `run/13-11-2026-00/manifest.json` and `artifacts/training/03-11-2026-01/manifest.json`:
  - `cleaned_csv`: `C:/Users/PC/orca/workspaces/SupportIQ/supportiq-final-routing/data/datasets/processed/03-11-2026-02/cleaned.csv` -> `8BC10CFA056371BDECB3394BFD4C75EEE7E10022ACE5071833ECD140B2D75846`
  - `split_assignments`: `C:/Users/PC/orca/workspaces/SupportIQ/supportiq-final-routing/data/datasets/splits/03-11-2026-02/split_assignments.csv` -> `1D366E898F6BA68BE46C5CA0F9059E9862FAD1D7BAFE350D9CDD310DD3E0A04C`
  - `split_report`: `F:/Năm 3/SD/project/SupportIQ/artifacts/preparation/03-11-2026-02/split_report.json` -> `BDAEF5C2699384A2A76AA5BC4C98C32D7423FF1AF425AA90E630512437448C56`
- **Truthful `git_dirty=true`, Source Code vs. Config:** `run/13-11-2026-00/{manifest.json,environment.json}` retain `git_revision: "4a13ac28718263d72b23a785e070fa021adee089"` and `git_dirty: true` because `pipeline/training/run_training.py:299-306` (`git status --porcelain`) saw the untracked `artifacts/evaluation/traditional_baseline_repro_20261113/config.json` and run directory at execution time. Zero source, pipeline, test, or dataset files were modified relative to `4a13ac28718263d72b23a785e070fa021adee089`; the only input difference vs `03-11-2026-01` is scoping [`config.json`](config.json) to the single winning `logistic_regression` (`C=20.0`) candidate rather than the multi-model sweep (`multinomial_nb`, `logistic_regression` grid, `linear_svm`).
- **Truthful Current Output Accounting (`12/13` Present & Verified, `1/13` Absent):** `11` committed metadata/report outputs (`candidate_summary.csv`, `config.resolved.json`, `environment.json`, `fold_metrics.csv`, `models/logistic_regression/model_card.json`, `reports/logistic_regression/{confusion_matrix.csv,core_intent_metrics.json,per_class_metrics.csv,top_confusions.csv}`, `run_state.json`, `selection.json`) plus `1` local gitignored bundle (`models/logistic_regression/bundle.joblib`, `6147AE24...`) are present and match `run/13-11-2026-00/manifest.json` SHA-256 hashes. The remaining `1/13` output, `run/13-11-2026-00/oof_predictions.csv` (`991A1C8576F671483EADDB5A90A5DFA349A03022AC0D760E2C3460A4D3653F06`), was deleted prior to `a7e9cfe` and is absent on disk; `03-11-2026-01/oof_predictions.csv` is 3-model (`1A09AD4B...` / `8211E2DC...`) and therefore not a byte-identical substitute, and no retraining was run to reconstruct the deleted CSV.

## 5. Authorized Reproducibility Closure Run (`13-11-2026-01`)

To replace the deleted `13-11-2026-00/oof_predictions.csv` without reconstructing or altering historical/prior records, one authorized CPU-only `TF-IDF + LogisticRegression(C=20.0)` run was executed from commit `f8fd58a42e5c7288ee12d68cb13306d0cdf22b39` (`git_dirty: true` solely from creating the untracked `run/13-11-2026-01/` directory; zero source, pipeline, or data changes) using the repo-committed [`prep_manifest_03_11_2026_02.json`](prep_manifest_03_11_2026_02.json) and [`config.json`](config.json):

- **Manifest & Retention (`13/13` Complete & Preserved):** [`run/13-11-2026-01/manifest.json`](run/13-11-2026-01/manifest.json) verifies **`13/13` outputs** via `load_completed_manifest(...)` both before and after commit. All `12/13` trackable outputs — including [`run/13-11-2026-01/oof_predictions.csv`](run/13-11-2026-01/oof_predictions.csv) (`3,667,533` B, `37,911` rows, `10` folds `0..9`, SHA-256 `991A1C8576F671483EADDB5A90A5DFA349A03022AC0D760E2C3460A4D3653F06`) — are committed in git; `models/logistic_regression/bundle.joblib` (`3,815,518` B, SHA-256 `5A58BD7870BD5C6E91DEF98099EBF6334E1C0F990C80B779BE71FFC49CC53B06`) stays preserved locally on disk (excluded from git by `.gitignore:79`).
- **Locked Metrics & Parity:** Fold Macro-F1 mean `0.989220` (`std ddof=0`: `0.001437`), Global OOF Macro-F1 `0.989221`, OOF Accuracy `0.989106`, `413` OOF errors (`oof_predictions.csv` SHA-256 `991A1C85...` is byte-identical to pre-deletion `13-11-2026-00`), and frozen `6,690`-row hold-out test `acc=0.990135`, `macro_f1=0.990252`.
- **Pinned Inputs Verified in `run/13-11-2026-01/manifest.json`:** `preparation_manifest` = `BBC17872A8618C73505F545F46F435FF987892AF529C14F6603F6DC7075CCEAF`, `cleaned_csv` = `8BC10CFA056371BDECB3394BFD4C75EEE7E10022ACE5071833ECD140B2D75846`, `split_assignments` = `1D366E898F6BA68BE46C5CA0F9059E9862FAD1D7BAFE350D9CDD310DD3E0A04C`, `split_report` = `BDAEF5C2699384A2A76AA5BC4C98C32D7423FF1AF425AA90E630512437448C56`, `config` = `7A4911C397B9904D0054A5AB7B82BD95D74031EADF13CB1185B8FF313AF1C167`.
