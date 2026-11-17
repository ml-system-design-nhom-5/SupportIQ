# Data and ML rules

> **Status:** Active · **Owner:** ai-service · **Last reviewed:** 2026-11-12

Rules for datasets, the knowledge base (KB), splits, training, prompts, and evaluation. They follow the [requirements](../product/requirements.md) and the course lectures on architecture (Lecture 3) and data quality engineering (Lecture 4). Every reported number must be reproducible from the repository.

## Sources and acceptable use

**DATA-01.** Bitext Retail E-commerce is used only to train and evaluate the intent classifier. Its `response` column MUST NOT be used as policy, KB content, few-shot examples, or ground truth for drafts.

**DATA-02.** The KB comes only from the approved shared source. Its files, version, and checksums are recorded in `contracts/kb-contract.md`.

**DATA-03.** Development data that does not come from an approved source is labeled `synthetic-dev-only` in its file name or metadata. It is never treated as policy and never used in evaluation reports.

**DATA-04.** Simulated business data (orders, shipments, refunds) is owned by `backend` and produced by a versioned, deterministic seed script.

**DATA-05.** Real personal or transaction data is never used.

## Data layout

```text
data/
├── raw/          # immutable originals exactly as received
├── interim/      # intermediate transformation outputs (git-ignored)
├── processed/    # validated, versioned inputs for training and evaluation
└── splits/       # committed split and fold manifests
```

**DATA-06.** Files in `data/raw/` are never edited. Every transformation is a script in the repository that reads its inputs and writes new files.

**DATA-07.** Bitext is downloaded by a script from a pinned dataset revision and verified against a recorded checksum. The raw file is git-ignored; the script, revision, and checksum are committed.

**DATA-08.** KB files are committed unchanged under `data/raw/kb/<kb_version>/` with a checksum manifest, because they are small and required for reproducibility.

**DATA-09.** Every dataset file has a manifest: source, version or revision, checksum, row count, producing script, and creation date.

## Validation at every boundary

**DATA-10.** Automated validation runs at every data boundary: ingestion, transformation, training input, serving input, and feedback export. Cleaning a dataset once is not enough.

**DATA-11.** Loading Bitext checks: the expected columns, exactly the 46 expected intent labels (from a versioned label file), no empty instructions, a row count that matches the manifest, and a report of exact and near-duplicate instructions. The report also counts instructions that contain identifier-like values (emails, phone numbers, order numbers) or text in the placeholder syntax ([ADR-0010](../decisions/0010-pseudonymization-and-egress-control.md#placeholder-syntax)).

**DATA-12.** KB ingestion checks against the KB data contract: required fields, unique (document ID, version) pairs, valid dates with `effective_start_at` before `effective_end_at`, a policy key on every document, matching checksums, and a report of overlapping effective periods with different content for the same policy key.

**DATA-13.** Invalid records are quarantined with a report. They are never silently dropped or fixed. A run with quarantined records fails until an issue reviews and accepts the quarantine.

**DATA-14.** Automatic repair is allowed only for frequent, well-understood problems (such as trailing whitespace), is documented in the transformation script, and keeps the original.

**DATA-15.** Missing is not zero. A missing value stays missing, with its reason when known.

## Knowledge base

**DATA-16.** The KB data contract defines, for each document version: document ID, version, title, body, policy key (the topic used to detect conflicts), `effective_start_at`, `effective_end_at` (absent means open-ended), source, owner, checksum, and `last_reviewed_at` when the source provides it. It also states freshness rules and who acts when a rule is violated.

**DATA-17.** A KB version is immutable. A change produces a new `kb_version`. Earlier versions stay available so old suggestions can be reproduced.

**DATA-18.** The document-to-intent mapping is a separate versioned file. KB documents are not edited to add it ([ADR-0005](../decisions/0005-intent-independent-retrieval.md)).

**DATA-19.** Validity is evaluated at `as_of`. Two valid versions with the same policy key and different content are a conflict, which is surfaced to staff and never resolved silently.

## Splits and evaluation protocol

**DATA-20.** The evaluation protocol is defined in a design doc before the first experiment, and matches the procedure shared with Group 2 (CST-02). It follows the split in the [requirements](../product/requirements.md#31-intent-classification): a hold-out test set fixed with a seed before any experiment, and 10-fold cross-validation on the train and validation part (NFR-01). It also defines the tolerances of the offline evaluation gate (DATA-57).

**DATA-21.** Each Bitext row has a stable ID: a hash of its normalized instruction text and its intent label. Rows with the same normalized instruction always fall in the same split, so duplicates cannot leak across splits.

**DATA-22.** Splits and folds are stratified by intent, use a fixed seed, and are committed as ID lists with a manifest hash.

**DATA-23.** Splits, folds, and test sets are never regenerated or edited after results have been seen. A necessary change requires an ADR and invalidates earlier results.

**DATA-24.** Every result reports the near-duplicate rate between training and test data.

## Leakage

**DATA-25.** Test data never enters training, feature fitting (for example the TF-IDF vocabulary), calibration, threshold tuning, rerank-weight tuning, few-shot examples, or prompts.

**DATA-26.** Preprocessing is fitted inside each cross-validation fold on that fold's training part only, through a single pipeline object.

**DATA-27.** Offline evaluation uses only information available at prediction time, evaluated at `as_of`.

**DATA-28.** The scenario test sets (robustness, escalation, retrieval, groundedness) are never used for tuning.

## Experiments and reproducibility

**DATA-29.** Every experiment runs from a committed configuration file through a script. Notebooks are for exploration only; any reported result comes from a script run.

**DATA-30.** Every run records its run ID, configuration, code commit, data manifest hashes, seed, environment lockfile, metrics, and artifact references in `ml/runs/<run_id>/`.

**DATA-31.** The same configuration, data, and code produce the same metrics. Known sources of nondeterminism are documented with the run.

**DATA-32.** Every reported model metric appears next to the baseline, measured with the same protocol.

## Models and artifacts

**DATA-33.** The baseline (TF-IDF with logistic regression or a linear SVM) is always trained and reported. The second model is chosen in an ADR based on measured trade-offs: accuracy, robustness, calibration, latency, size, and cost.

**DATA-34.** The classifier outputs calibrated probabilities over all 46 intents. Calibration is fitted on validation data and reported with the expected calibration error and a reliability diagram.

**DATA-35.** An artifact bundles preprocessing, model, label mapping, calibration, its version, the training data manifest hash, and a metrics summary. `ai-service` refuses to load an artifact that lacks any of these ([ERR-17](errors-and-reliability.md#startup-and-health)). Routing thresholds are not part of the artifact; they live in the routing configuration (DATA-58).

**DATA-36.** Artifact versions are unique and immutable. Where artifacts are stored is decided in an ADR before the first artifact is shared.

**DATA-37.** `ai-service` loads artifacts and never trains.

**DATA-56.** `ai-service` serves exactly one release manifest at a time, loaded at startup. A release manifest has a unique, immutable `release_id` and names, with the checksum of each: the model artifact version, the KB version, the document-to-intent mapping version, the prompt versions, the routing configuration version, and the retrieval index version. It also links the offline evaluation run that passed the gate (DATA-57). `ai-service` refuses to start with a manifest that is incomplete, whose checksums do not match, or whose routing configuration was tuned for a different model artifact version than the one the manifest names (DATA-58, [ERR-17](errors-and-reliability.md#startup-and-health)). Every suggestion reports its `release_id` ([ARCH-39](architecture.md#versioned-assets)).

**DATA-57.** The offline evaluation gate decides whether a candidate release manifest may be published. The gate runs exactly that manifest on the frozen hold-out test set and the scenario sets. It passes only when:

1. every guardrail test ([TEST-26](testing.md#guardrail-tests)) and every mandatory escalation case passes;
2. no quality target of the [requirements](../product/requirements.md#5-quality-requirements) is worse than in the current release by more than the tolerance in the evaluation protocol (DATA-20).

If the gate fails, the current release stays in service. Missed targets are reported as they are (DATA-48). The gate never tunes anything on test data (DATA-25).

**DATA-58.** The routing configuration is a versioned file that holds τ (the minimum top-1 probability), δ (the minimum gap between the top two probabilities), the rerank weight λ, the list of sensitive intents, and the sensitive-term list (ESC-01, ESC-03). τ, δ, and λ are tuned on validation data for one model artifact version, and the file records that version. Each entry of the sensitive-term list states its category (legal claim, suspected fraud) and is reviewed by the policy owner and the RAG engineer. Any change produces a new version ([ARCH-40](architecture.md#versioned-assets)) and a new evaluation.

**DATA-59.** The classifier, the retrieval index, and the evaluation sets see the same kind of text that `ai-service` receives in service: pseudonymized text. Preprocessing maps every placeholder to its type alone (for example `[ORDER_ID_1]` to `[ORDER_ID]`) in training, evaluation, and serving, inside the same pipeline object (DATA-26). The scenario sets include messages with placeholders and messages that name third persons, and robustness results report them as separate slices.

## Prompts and LLM output

**DATA-38.** Prompt templates are versioned files in `ai-service`, reviewed like code. Every suggestion reports its `prompt_version`.

**DATA-39.** Prompts contain no test data, no Bitext responses, and no real data.

**DATA-40.** LLM output is requested in a structured format and validated against a schema. Invalid output is an LLM failure ([ERR-08](errors-and-reliability.md#required-behavior-per-failure)).

**DATA-41.** Settings that change LLM output (model name, temperature, maximum tokens) are part of the recorded configuration of every suggestion.

## Evaluation and reporting

**DATA-42.** Classification: Macro-F1 from 10-fold cross-validation, per-class F1, the confusion matrix, and calibration, with the baseline.

**DATA-43.** Robustness: separate results for typos, unusual phrasing, ambiguous, multi-intent, and out-of-scope messages, plus results per Bitext `tags` slice (`Z`, `Q`, `C`, `K`, `E`, `W`).

**DATA-44.** Routing: accuracy of in-scope versus out-of-scope routing and of mandatory escalation.

**DATA-45.** Retrieval: Recall@3 on questions with a supporting valid document, the ablation with and without reranking ([ADR-0005](../decisions/0005-intent-independent-retrieval.md)), and results on expired and conflicting document cases.

**DATA-46.** Drafting: groundedness on the manually graded set, using a written grading rubric, and abstention correctness on insufficient-evidence cases. Every sample is graded independently by at least two graders (NFR-04). Agreement is reported, and each disagreement is resolved by discussion and recorded with the sample.

**DATA-47.** Latency and cost: p50 and p95 end to end and per step, error rate, and cost per request, under the shared test conditions recorded with the run.

**DATA-48.** A change that can move a metric is re-measured before merge. Results that miss a target are reported as they are; "seems better" is never a result.

## Feedback

**DATA-49.** Staff feedback is not ground truth. An approval does not prove that a draft was correct.

**DATA-50.** Staff decisions MUST NOT flow directly into training data, prompts, or rules. Improvements go through review and versioned changes ([ADR-0006](../decisions/0006-staff-feedback-and-reason-codes.md)). A manager and the ML engineer review exported feedback in a curation step. An accepted improvement becomes a new version of an asset, and then a candidate release that must pass the offline evaluation gate (DATA-57).

**DATA-51.** Feedback data never mixes with evaluation sets.

## Drift

**DATA-52.** Monitoring distinguishes covariate shift, label-prior shift, concept shift, schema drift, and out-of-distribution input.

**DATA-53.** A drift alert does not prove the model is broken. Investigate the data path first, use a safe mode for the affected slice, and do not rush a retrain.

**DATA-54.** Drift alerts are actionable: they name the slice, the threshold, the affected decision, the owner, and the first action ([LOG-32](logging-and-observability.md#alerts-and-retention)).

## Choosing models

**DATA-55.** Accuracy is never the only criterion. Every model choice weighs inference time, model size, training cost, data needs, robustness, calibration, interpretability, and reproducibility, and is recorded in an ADR.
