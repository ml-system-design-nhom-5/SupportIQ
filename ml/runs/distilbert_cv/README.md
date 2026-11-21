# Run `distilbert_cv`: the intent model `v1.0.0`

The first run record of `ml/runs/`, the evidence of the real model that ADR-0021 keeps from `main`: the training report and the 10-fold cross-validation of the DistilBERT model that `ai-service` serves first ([ADR-0021, Large files and data](../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 2; [DATA-30](../../../docs/rules/data-and-ml.md#experiments-and-reproducibility)). The join wrote the record from the files of `main` at commit `19ece5d81fbd74c00602eb1b34bb53ead06c9668`; no value comes from a new run.

## Run ID

The training report of `main` has no run ID field. `main` named the run by the folder of its outputs, `artifacts/training/distilbert_cv/`, as its other runs are named by their folders, so the run ID is `distilbert_cv`. It fits the pattern of the run ID of the model artifact (`ai-service/README.md`, Asset formats).

## Files

| File | Holds |
|---|---|
| [`run.json`](run.json) | The configuration, the data hashes, the metrics, the fields that the run did not record, and the assets with their checksums |
| [`fold_metrics.csv`](fold_metrics.csv) | The metrics of each of the 10 folds, byte for byte as `artifacts/training/distilbert_cv/fold_metrics.csv` at `19ece5d` (SHA-256 `1aaba403fc66e010d9c96f0d352e5db753ef3036e8151b1fcf306d5bcb3d1894`) |
| [`model-artifact.json`](model-artifact.json) | The `artifact.json` of the model asset of a release, in `supportiq-model-artifact/interim-1`, which the release command copies with the files of the model |

The training report, `training_report.json`, stays an asset of the GitHub Release, inside `distilbert-supportiq.zip` ([ADR-0018, Artifact store](../../../docs/decisions/0018-hosting-of-ai-service-on-modal.md#artifact-store)): its bytes have CRLF line ends and no final newline, which the hooks of this repository would change. `run.json` holds its values. The out-of-fold predictions, `artifacts/training/distilbert_cv/oof_predictions.csv` (1 810 025 bytes), stay in the history at `19ece5d`, because the hook that refuses files above 500 KB applies.

## Sources

Every value of `run.json` and `model-artifact.json` comes from one of these files of `main` at `19ece5d`, or from an asset of the GitHub Releases of the organization repository.

| Value | Source |
|---|---|
| Configuration, metrics, durations, `created_at`, and the membership evidence | `training_report.json` in `distilbert-supportiq.zip` (SHA-256 `9609b6604c0c137365db927f0eb149bdd4af54fdf3ca22aa1adb235bf22a3972`), written by `pipeline/training/train_distilbert_cv.py`, lines 453 to 481 |
| `base_model` `distilbert/distilbert-base-uncased` | `artifacts/evaluation/04-11-2026-06/config.resolved.json`, lines 29 to 40; the training report names only its local folder |
| The checksums of `config.json`, `model.safetensors`, `tokenizer.json`, `tokenizer_config.json`, `training_report.json`, and `train_sample_ids.json` | `artifacts/evaluation/04-11-2026-06/manifest.json`, `inputs`, the run of `main` that pinned the model `v1.0.0`; `apps/ml_inference/app.py`, lines 18 to 23, names it as the source of its pinned checksums |
| `model_version` `v1.0.0` | `apps/ml_inference/app.py`, line 20 |
| `preprocessing`: `max_length` 64, `padding` `max_length`, `truncation` `true` | `apps/ml_inference/app.py`, lines 633 to 637, the tokenization of each message at serving, which the model artifact describes |
| `cleaned_csv_sha256`, `split_assignments_sha256`, `split_report_sha256`, and `preparation_manifest_sha256` | `artifacts/evaluation/04-11-2026-06/manifest.json`, `inputs` |
| `raw_dataset_sha256`, `preparation_run_id`, and `train_samples` | `artifacts/preparation/03-11-2026-02/manifest.json`, `input_files` and `metadata` |

## Checks of the join

- The six files of `distilbert-supportiq.zip` (release `v2.0.0-model`, SHA-256 `1f32feaa04c49c71add7481115b9a238710a42d0c3888960bf35231e2a93cad7`) have the checksums that the manifest of `04-11-2026-06` pins. Its `model.safetensors` is the asset `model.safetensors` of the release `v1.0.0-model`, with the same SHA-256 `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`.
- `config.json` pins the order of the outputs: its `id2label` names each of the 46 labels of `contracts/schemas/IntentLabel.yaml` once, for the outputs 0 to 45 in alphabetical order, and its `label2id` is the inverse. That manifest pins this `config.json` together with the weights, so the order is the one the weights were trained with.
- `training_data_manifest_sha256` is the SHA-256 of `artifacts/preparation/03-11-2026-02/manifest.json` with CRLF line ends, `924f455583caecf22100edd5667ead711f3f940fab5b7258738f6631133398a2`, which is the value that `main` recorded as `preparation_manifest`. The same file in git, with LF line ends, has the SHA-256 `30377c64f3b45f1c3c288ebfe68cffb752c6c033d1a20cbbdd01f2eb31a02768`.
- The 10 rows of `fold_metrics.csv` equal the `fold_metrics` of the training report.

## Known limits

- The run did not record its seed, the `max_length` of its training, the commit of its code, or a lockfile of its environment (`not_recorded` in `run.json`). The script defaults are a seed of 42 and a `max_length` of 64 (`pipeline/training/train_distilbert_cv.py`, lines 241 and 244), but nothing records that the run used them.
- Training padded each batch to its longest message (`padding=True`, lines 303 to 312 and 404 to 406), while serving pads each message to 64 tokens. The attention mask hides the padding, but the scores at serving were never compared with those of training.
- The model has no calibration: `calibration` is `null`, as the interim format requires ([`ai-service/README.md`, Known limits](../../../ai-service/README.md#known-limits)).
- The metrics are those of the cross-validation on the 37 911 training samples of the preparation run `03-11-2026-02`. No hold-out metric is recorded here: ADR-0021 keeps only the training report and the cross-validation, and the data is synthetic ([`ml/README.md`, Data](../../README.md#data)).
