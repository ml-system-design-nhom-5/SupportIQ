# ml

`ml/` holds the data preparation, the training, the baseline, and the cross-validation of the intent model ([ADR-0021, Target layout](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#target-layout), [ARCH-08](../docs/rules/architecture.md#component-boundaries)). ADR-0021 also places the calibration of the intent model and the run records of `ml/runs/<run_id>/` here ([DATA-30](../docs/rules/data-and-ml.md#experiments-and-reproducibility)): one record exists, of the model that `ai-service` serves first, and no calibration yet ([Run records](#run-records), [Known limits](#known-limits)). `ai-service` loads the model that `ml/` trains, as a release asset, and never trains ([DATA-37](../docs/rules/data-and-ml.md#models-and-artifacts)). `ml/` reaches `ai-service` only through the format of the model artifact (ADR-0021, Where the code of `main` goes, statement 1).

The code came from `pipeline/preparation/` and `pipeline/training/` on `main`. The join moved it as it was, with only the format fixes that the root hooks need ([ADR-0021, CI](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 5), so it cannot run yet ([State after the join](#state-after-the-join)). This README describes what the code does, so the first PR after the join can make it run without guessing.

## State after the join

- The modules that import each other still name `pipeline.preparation` or `pipeline.training`, and `pipeline/` no longer holds the code, so they do not import. The tests import the same names. The package of the code is now `supportiq_ml`, under `ml/src/`.
- `training/run_training.py` resolves its relative paths against `Path(__file__).resolve().parents[2]`, which is now `ml/src/`, not the repository root.
- `ml/` has no `pyproject.toml`, no `uv.lock`, and no CI workflow. `requirements.txt` and `requirements-transformers.txt` set minimum versions (`>=`), not exact ones ([WF-28](../docs/rules/workflow.md#dependencies)). `scipy` is imported but not listed, and `cloudpickle` is listed but not imported.
- `tests/unit/test_training.py` takes `ml/` as its root (`parents[2]`). It reads `ml/pipeline/configs/training.json`, which does not exist, because the configuration is now `ml/configs/training.json`. It also expects the line `/artifacts/training/` in `ml/.gitignore`, which does not exist; the root `.gitignore` has no such line either.

The first PR after the join brings `ml.yml`, the project files, and the interim rule level ([ADR-0021, CI](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statements 8 and 9), and its `tech-debt` issue, [#33](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/33), tracks this work. The commands below are those of `main`, with the module paths of `main`: they run only after that PR.

## Layout

| Path | Holds |
|---|---|
| `src/supportiq_ml/preparation/utils.py` | The 13 categories, the 46 intents, and the 12 in-scope intents; run IDs of the form `DD-MM-YYYY-nn`; SHA-256 checksums in uppercase; JSON helpers; NFKC normalization; the near-duplicate key |
| `src/supportiq_ml/preparation/inspect_data.py` | Exploratory data analysis: length statistics, the distribution of the 46 intents, and figures |
| `src/supportiq_ml/preparation/validate_data.py` | The checks of the raw file, as a report |
| `src/supportiq_ml/preparation/clean_data.py` | Cleaning and quarantine |
| `src/supportiq_ml/preparation/split_data.py` | The hold-out test set and the 10 folds, by group, with the leakage check |
| `src/supportiq_ml/preparation/features.py` | `IntentFeaturePipeline`, TF-IDF fitted on training rows only |
| `src/supportiq_ml/preparation/run_preparation.py` | Runs every step of preparation and writes its manifest |
| `src/supportiq_ml/training/models.py` | The training configuration, its candidates, and the estimators |
| `src/supportiq_ml/training/cross_validate.py` | The loop over the folds and the out-of-fold predictions |
| `src/supportiq_ml/training/artifacts.py` | The inference bundle, the model card, and atomic writes |
| `src/supportiq_ml/training/run_training.py` | Runs training: checks its inputs, selects the winner, refits, and writes the manifest |
| `src/supportiq_ml/training/train_distilbert.py` | Fine-tunes DistilBERT on a sample of the development rows |
| `src/supportiq_ml/training/train_distilbert_cv.py` | 10-fold cross-validation of DistilBERT, then a refit on all development rows |
| `configs/training.json` | Seed 42, 10 folds, a target Macro-F1 of 0.85 in cross-validation, TF-IDF of 1-grams and 2-grams (10 000 features, `min_df` 2), and 3 values of the grid for each of the 3 baselines |
| `configs/training_1000_fits.json` | The same settings with 100 candidates, so 1 000 fits over the 10 folds |
| `tests/unit/` | Tests of preparation, of training, and of the cross-validation of DistilBERT, and a CUDA smoke test marked `cuda` |

## Data

- The input is the Bitext Retail E-commerce dataset: `instruction` as the text and `intent` as the label, 46 labels. `category` and `tags` serve only to analyze slices. Its `response` column is never policy, KB content, a few-shot example, or ground truth for drafts ([DATA-01](../docs/rules/data-and-ml.md#sources-and-acceptable-use)).
- No code of `ml/` downloads it: the commands take the raw file with `--input`. Its place is `data/raw/bitext/`, which `.gitignore` ignores ([DATA-06](../docs/rules/data-and-ml.md#data-layout), [DATA-07](../docs/rules/data-and-ml.md#data-layout)).
- The code still writes to the folders of `main`. Datasets and splits go under `data/datasets/`, which `.gitignore` ignores until the first PR after the join moves them. Preparation runs, training runs, and models go under `artifacts/preparation/`, `artifacts/training/`, and `artifacts/models/`, which `.gitignore` does not ignore, apart from the weight files `*.safetensors` and `*.pt`. ADR-0021 (Target layout) leaves no `artifacts/` in the tree.
- `main`'s document `docs/data-quality.md` recorded on 2026-11-03 that the file is a hybrid synthetic dataset in English under the license `cdla-sharing-1.0`, with the SHA-256 `13A988266FED4E2B2C1FF947A89EF220CE09B5B13AC83C4A1496C0D7B81E8127` (`git show 19ece5d:docs/data-quality.md`). It recorded no revision and no download date ([Open questions](#open-questions)).
- Results on a synthetic dataset do not show how the model performs on real customer messages.

## Data quality

The code performs these checks ([DATA-11](../docs/rules/data-and-ml.md#validation-at-every-boundary)):

| Step | Checks | On failure |
|---|---|---|
| `validate_data` | The columns `instruction`, `intent`, and `category`; missing values; intents and categories outside the taxonomy; exact duplicates and near-duplicate groups with conflicting labels | A missing column stops the run. Everything else goes to `validation_report.json` and `review_candidates.csv`, and the run continues |
| `clean_data` | NFKC normalization of the text, with the Bitext slot markers `{{...}}` kept as they are | Rows are quarantined in `quarantined.csv` with a `quarantine_reason`: `missing_required_fields`, `invalid_intent_label`, `invalid_category_label`, or `conflicting_labels_across_duplicates`, which quarantines the whole near-duplicate group. Exact duplicates are then removed |
| `run_preparation` (`verify_cleaned_integrity`) | The cleaned file exists and is not empty, has the required columns, no empty value, only labels of the taxonomy, and no conflicting near-duplicate group | The run stops before the split |
| `split_data` | No near-duplicate group crosses the test set or two folds | The run stops |

`main` also proposed eight data quality requirements for the prototype, DQ-01 to DQ-08. Its document recorded their thresholds as proposals to agree on before the experiments, not as measured values (`git show 19ece5d:docs/data-quality.md`, [Open questions](#open-questions)):

| ID | Requirement | Proposed measure |
|---|---|---|
| DQ-01 Accuracy | Instructions carry the right intent | Two people review at least 10 rows of each intent; at most 5% wrong labels in the reviewed rows, reported by intent |
| DQ-02 Completeness | Every row has an instruction and a valid intent, and all 46 intents appear | 0 rows without a required field; 46 of 46 intents in the training set, the test set, and each fold |
| DQ-03 Uniqueness | No duplicate inflates a class or leaks across sets | 0 exact duplicates after normalization; 0 near-duplicate groups across sets or folds |
| DQ-04 Consistency | One taxonomy of 46 intents, and one mapping of the 12 in-scope intents for the model, retrieval, and tests | 100% of labels in the taxonomy |
| DQ-05 Currentness | One pinned version of Bitext | The revision is recorded; a newer file is not assumed to be better |
| DQ-06 Traceability | Each dataset version names its source, checksum, date, processing, and split | A manifest for each version ([DATA-09](../docs/rules/data-and-ml.md#data-layout)) |
| DQ-07 Fit for scope | The evaluation covers the 46 intents and the 12 in-scope intents, and the limits of synthetic data | Counts by label and by set; no claim about production without real data |
| DQ-08 Privacy | No real personal or transaction data | 0 confirmed real values in the data in use ([SEC-01](../docs/rules/security-and-privacy.md#data-classification)) |

`main`'s document also covered the KB and the simulated orders. KB ingestion in [`eval/release/`](../eval/release/README.md#kb-ingestion) checks the KB. The simulated orders, `mock_orders.json`, are frozen test data next to the suites of `eval/`: the manifests of the suites pin their SHA-256, no code validates their fields, and the code that checks the pins does not run yet ([`eval/README.md`, State after the join](../eval/README.md#state-after-the-join)).

## Split and cross-validation

`split_data` makes one hold-out test set and 10 folds of the development rows. The defaults are seed 42, a test fraction of 0.15, and 10 folds. `clean_data`, `split_data`, and `run_preparation` refuse to write a dataset or split version that already exists, unless `--overwrite` is given. That flag lets a version be regenerated, which [DATA-23](../docs/rules/data-and-ml.md#splits-and-evaluation-protocol) forbids after its results have been seen.

1. After cleaning, exact duplicates (the lowercase instruction with its intent) are removed, keeping the first, and each row gets the ID `sample_000000`, `sample_000001`, and so on, in file order.
2. Each row belongs to a group: the MD5 of its near-duplicate key, which is the instruction after NFKC, lowercase, punctuation removed outside `{{...}}`, and collapsed spaces.
3. For each intent, its groups are shuffled with the seed, and whole groups go to the test set until it holds the test fraction of the rows of that intent. An intent with a single group stays in development.
4. The development rows are split by `StratifiedGroupKFold` with the seed, stratified by intent and grouped by group. Test rows get fold `-1`.
5. A group in both the test set and development, or in two folds, stops the run.

`split_assignments.csv` lists `sample_id`, `partition` (`train` or `test`), and `fold`. `split_report.json` records the checksums of the cleaned file and of the assignments, the settings, the counts, the class distribution of each fold, and `leakage_detected`.

Training checks these files again before it starts: the checksums, folds exactly `0` to `n-1` and `-1` for the test set, no group across partitions or folds, and every intent in the test set and in each fold. Training never fits, transforms, or predicts on the test set, and each fold fits its own TF-IDF on its training rows.

## Training

- **Baselines.** `run_training` runs 10-fold cross-validation over MultinomialNB, LogisticRegression, and LinearSVC with the grids of `configs/training.json`, and selects the winner by the highest mean Macro-F1, then the lowest standard deviation, then the order of the configuration. It refits the winner on all development rows and writes an inference bundle and a model card. A `ConvergenceWarning` or a metric that is not a number stops the run, and a run below the target of 0.85 is kept but marked as not ready for a release. The baseline is always trained and reported ([DATA-33](../docs/rules/data-and-ml.md#models-and-artifacts)).
- **The bundle.** `predict` normalizes the text like training. `predict_proba` exists only when the estimator has it, so LinearSVC never reports a made-up probability. Load a `bundle.joblib` only from a trusted run folder, because loading it runs code.
- **DistilBERT.** `train_distilbert` fine-tunes on up to 250 training rows and up to 50 validation rows of each class, sampled with seed 42. `train_distilbert_cv` runs 10-fold cross-validation on the development rows (it requires exactly 37 911 of them) and refits on all of them.

## Results recorded on `main`

These numbers were measured on `main` and are recorded in [ADR-0021, Evaluation evidence on `main`](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#evaluation-evidence-on-main). They were not measured again here.

- The 10-fold cross-validation of DistilBERT on Bitext gives a Macro-F1 between 0.993 and 0.997 per fold.
- The autoeval of `main` ran the real model on 156 written cases: a Macro-F1 of 0.611 and an expected calibration error of 0.106.
- The Macro-F1 of 0.9736 in several reports of `main` comes from a script that did not run the model, so it is not a result.

## Run records

[DATA-30](../docs/rules/data-and-ml.md#experiments-and-reproducibility) requires every run to record its run ID, configuration, code commit, data manifest hashes, seed, environment lockfile, metrics, and the links to its large files in `ml/runs/<run_id>/`. Weights and large outputs are assets of GitHub Releases, never in git ([ADR-0018, Artifact store](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#artifact-store)).

The code of `ml/` still writes its training runs to `artifacts/training/`, not to `ml/runs/`. The one record comes from `main`: [`runs/distilbert_cv/`](runs/distilbert_cv/README.md) holds the training report and the 10-fold cross-validation of the DistilBERT model `v1.0.0`, which `ai-service` serves first, and the `artifact.json` of that model asset ([ADR-0021, Large files and data](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 2). Its weights, configuration, and tokenizer are assets of the releases `v1.0.0-model` and `v2.0.0-model`, checked against the checksums that `main` pinned.

## Known limits

- The code does not run until its imports, its root path, and its project files are fixed ([State after the join](#state-after-the-join)). Until then, only the root hooks that apply to every file check `ml/`, such as the checks of whitespace, JSON, file size, and secrets (gitleaks). No hook checks its Python.
- No script downloads Bitext from a pinned revision ([DATA-07](../docs/rules/data-and-ml.md#data-layout)).
- The manifest of a preparation run records the SHA-256 of the raw file, the row counts of the raw, cleaned, quarantined, training, and test data, and its creation time. No dataset file has a manifest of its own, and no manifest names the source, the revision, or the producing script ([DATA-09](../docs/rules/data-and-ml.md#data-layout)).
- The loading checks take the 46 labels from the constant `STANDARD_INTENTS` in `utils.py`, not from a versioned label file. They do not compare the row count with a manifest, and they do not count identifier-like values or text in the placeholder syntax ([DATA-11](../docs/rules/data-and-ml.md#validation-at-every-boundary)).
- Row IDs come from the order of the cleaned file, not from a hash of the normalized instruction and its label, and the splits are written to an ignored folder instead of being committed as ID lists with a manifest hash ([DATA-21, DATA-22](../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)).
- The model artifact holds no calibration: `main` declared a temperature but served raw softmax scores ([ADR-0021, What `main` holds](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#what-main-holds)), and the model card of `run_training` states `not_calibrated`. A calibration fitted on validation data, with its expected calibration error and a reliability diagram, waits for the next training ([DATA-34](../docs/rules/data-and-ml.md#models-and-artifacts)).
- Placeholders are not mapped to their type before training; the project lead deferred [DATA-59](../docs/rules/data-and-ml.md#models-and-artifacts) to the next training on 2026-11-15.
- The interim rule level, once it exists, falls short of the Python rules ([ADR-0021, CI](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 9).

## Open questions

- Whether DQ-01 to DQ-08 and their thresholds become requirements of `ml/`, and who agrees them. `main`'s document recorded them as proposals to agree on before the experiments.
- Which revision of Bitext the SHA-256 that `main` recorded belongs to, and whether the file that a download script pins has that SHA-256 ([DATA-07](../docs/rules/data-and-ml.md#data-layout)). No Bitext file was checked here.
