# ml

`ml/runs/` holds the run records of the intent model that `ai-service` serves ([DATA-30](../docs/rules/data-and-ml.md#experiments-and-reproducibility)). The code that prepares the data and trains the model is the code of `main` in [`pipeline/`](../pipeline/README.md), kept at its path ([ADR-0028, Copies deleted from `build/join-main`](../docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#copies-deleted-from-buildjoin-main), statement 2). `ai-service` loads the model as a release asset and never trains ([DATA-37](../docs/rules/data-and-ml.md#models-and-artifacts)).

## Run records

DATA-30 requires every run to record its run ID, configuration, code commit, data manifest hashes, seed, environment lockfile, metrics, and the links to its large files in `ml/runs/<run_id>/`. Weights and large outputs are assets of GitHub Releases, never in git ([ADR-0018, Artifact store](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#artifact-store)).

| Run | Holds |
|---|---|
| [`runs/distilbert_cv/`](runs/distilbert_cv/README.md) | The training report and the 10-fold cross-validation of the DistilBERT model `v1.0.0`, which `ai-service` serves first, and the `artifact.json` of that model asset, which the model artifact of `ai-service` points to. Its weights, configuration, and tokenizer are assets of the releases `v1.0.0-model` and `v2.0.0-model`, checked against the checksums that `main` pinned |

The record was written from the files of `main`; no value comes from a new run ([ADR-0021, Large files and data](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 2). Its `fold_metrics.csv` is a byte copy of `artifacts/training/distilbert_cv/fold_metrics.csv`, kept on purpose as part of the frozen record (ADR-0028, Copies deleted, statement 5).

## Data

- The runs use the Bitext Retail E-commerce dataset: `instruction` as the text and `intent` as the label, 46 labels. Its `response` column is never policy, KB content, a few-shot example, or ground truth for drafts ([DATA-01](../docs/rules/data-and-ml.md#sources-and-acceptable-use)).
- The dataset is not committed. Its place is `data/raw/bitext/`, which `.gitignore` ignores ([DATA-06](../docs/rules/data-and-ml.md#data-layout), [DATA-07](../docs/rules/data-and-ml.md#data-layout)).
- `main`'s document `docs/data-quality.md` recorded on 2026-11-03 that the file is a hybrid synthetic dataset in English under the license `cdla-sharing-1.0`, with the SHA-256 `13A988266FED4E2B2C1FF947A89EF220CE09B5B13AC83C4A1496C0D7B81E8127` (`git show 19ece5d:docs/data-quality.md`). It recorded no revision and no download date ([Open questions](#open-questions)).
- Results on a synthetic dataset do not show how the model performs on real customer messages.

## Training code

- The data preparation and the training are in [`pipeline/preparation/`](../pipeline/preparation/README.md) and [`pipeline/training/`](../pipeline/training/README.md). They write their runs to `artifacts/`, not to `ml/runs/`, and they follow no engineering rule yet ([ADR-0031, Technical debt](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#technical-debt)). The placeholder normalization that [DATA-59](../docs/rules/data-and-ml.md#models-and-artifacts) requires is in [`pipeline/preparation/preprocessing.py`](../pipeline/preparation/preprocessing.py), and `ai-service` does not apply it yet ([ADR-0031, Technical debt](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#technical-debt), item 1).
- The data quality checks of `main` and its proposed requirements DQ-01 to DQ-08 are in [`docs/data-quality.md`](../docs/data-quality.md).
- The results measured on `main` are recorded in [ADR-0021, Evaluation evidence on `main`](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#evaluation-evidence-on-main). The 10-fold cross-validation of DistilBERT on Bitext gives a Macro-F1 between 0.993 and 0.997 per fold. The autoeval of `main` ran the real model on 156 written cases: a Macro-F1 of 0.611 and an expected calibration error of 0.106. The Macro-F1 of 0.9736 in several reports of `main`, `docs/AI_PIPELINE_METRIC_IMPROVEMENTS.md` among them, comes from a script that did not run the model, so it is not a result ([ADR-0028, A number in a kept document](../docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#a-number-in-a-kept-document)).

## Open questions

- Whether DQ-01 to DQ-08 and their thresholds become requirements, and who agrees them. `main`'s document recorded them as proposals to agree on before the experiments.
- Which revision of Bitext the SHA-256 that `main` recorded belongs to, and whether the file that a download script pins has that SHA-256 ([DATA-07](../docs/rules/data-and-ml.md#data-layout)). No Bitext file was checked here.
